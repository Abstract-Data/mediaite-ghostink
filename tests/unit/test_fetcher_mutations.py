"""Unit tests for :func:`_persist_and_log` branch behavior."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from forensics.config.settings import ScrapingConfig
from forensics.models.article import Article
from forensics.scraper.fetcher import (
    ArticleHtmlFetchContext,
    RateLimiter,
    _apply_http_failed_mutation,
    _apply_off_domain_mutation,
    _persist_and_log,
)
from forensics.storage.repository import Repository, UnfetchedArticle


def _make_article(
    *,
    clean_text: str = "",
    url: str = "https://www.mediaite.com/p/",
    raw_html_path: str = "",
    word_count: int | None = None,
    content_hash: str = "",
) -> Article:
    """Build a minimal Article suitable for the persist-and-log branches."""
    return Article(
        id="article-test-1",
        author_id="author-test-1",
        url=url,
        title="T",
        published_date=datetime(2024, 1, 2, tzinfo=UTC),
        clean_text=clean_text,
        word_count=word_count
        if word_count is not None
        else (0 if not clean_text else len(clean_text.split())),
        content_hash=content_hash,
        raw_html_path=raw_html_path,
    )


def _make_row(article: Article, *, author_name: str = "Author A") -> UnfetchedArticle:
    return UnfetchedArticle(
        article.id,
        str(article.url),
        author_name,
        article.published_date,
    )


def _make_ctx(
    tmp_path: Path,
    repo: Repository | MagicMock,
    *,
    total: int = 1,
    done_count: list[int] | None = None,
) -> ArticleHtmlFetchContext:
    scraping = ScrapingConfig(
        rate_limit_seconds=0.0,
        rate_limit_jitter=0.0,
        max_concurrent=1,
        max_retries=0,
        retry_backoff_seconds=0.0,
    )
    return ArticleHtmlFetchContext(
        repo=repo,  # type: ignore[arg-type]
        root=tmp_path,
        scraping=scraping,
        limiter=RateLimiter(0.0, 0.0),
        errors=tmp_path / "e.jsonl",
        coauth=tmp_path / "c.jsonl",
        warns=tmp_path / "w.jsonl",
        sem=asyncio.Semaphore(1),
        db_lock=asyncio.Lock(),
        done_lock=asyncio.Lock(),
        done_count=done_count if done_count is not None else [0],
        total=total,
    )


@pytest.mark.asyncio
async def test_persist_and_log_http_fail_branch(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """HTTP-failure branch: mutate in place, upsert, increment counter, log 'http NNN'."""
    fresh = _make_article()
    repo = MagicMock(spec=Repository)
    repo.get_article_by_id.return_value = fresh
    repo.upsert_article.return_value = None

    ctx = _make_ctx(tmp_path, repo, total=5)
    row = _make_row(fresh)
    response = httpx.Response(503, request=httpx.Request("GET", str(fresh.url)))
    scraped_at = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)

    with caplog.at_level(logging.INFO, logger="forensics.scraper.fetcher"):
        persisted = await _persist_and_log(
            ctx,
            row,
            mutate=lambda a: _apply_http_failed_mutation(a, scraped_at, response),
            log_suffix=" (http 503)",
        )

    assert persisted is True
    repo.get_article_by_id.assert_called_once_with(fresh.id)
    repo.upsert_article.assert_called_once()
    persisted_article = repo.upsert_article.call_args.args[0]
    assert persisted_article.clean_text == "[HTTP_ERROR:503]"
    assert persisted_article.word_count == 0
    assert persisted_article.scraped_at == scraped_at
    assert ctx.done_count == [1]
    assert any("(http 503)" in rec.getMessage() for rec in caplog.records)
    assert any("1/5" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_persist_and_log_off_domain_branch(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Off-domain redirect branch: set REDIRECT marker, clear raw path, log 'off-domain host'."""
    fresh = _make_article()
    repo = MagicMock(spec=Repository)
    repo.get_article_by_id.return_value = fresh
    repo.upsert_article.return_value = None

    ctx = _make_ctx(tmp_path, repo, total=2)
    row = _make_row(fresh)
    scraped_at = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
    final_host = "off-domain.example"

    with caplog.at_level(logging.INFO, logger="forensics.scraper.fetcher"):
        persisted = await _persist_and_log(
            ctx,
            row,
            mutate=lambda a: _apply_off_domain_mutation(a, scraped_at, final_host),
            log_suffix=f" (off-domain {final_host})",
        )

    assert persisted is True
    repo.upsert_article.assert_called_once()
    persisted_article = repo.upsert_article.call_args.args[0]
    assert persisted_article.clean_text == f"[REDIRECT:{final_host}]"
    assert persisted_article.raw_html_path == ""
    assert persisted_article.word_count == 0
    assert ctx.done_count == [1]
    assert any(f"(off-domain {final_host})" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_persist_and_log_success_branch_with_prebuilt_article(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Success branch: caller supplies a pre-mutated Article; helper upserts that object."""
    # Latest DB row still unfilled (body empty) — the successful fetch is a race winner.
    latest_empty = _make_article()
    pre_built = _make_article(
        clean_text="the parsed body text here",
        raw_html_path="raw/2024/article-test-1.html",
        word_count=5,
        content_hash="abc123",
    )

    repo = MagicMock(spec=Repository)
    repo.get_article_by_id.return_value = latest_empty
    repo.upsert_article.return_value = None

    ctx = _make_ctx(tmp_path, repo, total=3)
    row = _make_row(pre_built, author_name="Author B")

    with caplog.at_level(logging.INFO, logger="forensics.scraper.fetcher"):
        persisted = await _persist_and_log(
            ctx,
            row,
            mutate=None,
            article=pre_built,
            log_suffix="",
        )

    assert persisted is True
    # The pre-built article (not the freshly-read empty row) is what gets written.
    repo.upsert_article.assert_called_once()
    persisted_article = repo.upsert_article.call_args.args[0]
    assert persisted_article is pre_built
    assert persisted_article.clean_text == "the parsed body text here"
    assert ctx.done_count == [1]
    assert any("1/3 articles for Author B" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_persist_and_log_skips_when_already_fetched(tmp_path: Path) -> None:
    """If the DB row is already populated, helper returns False and does not upsert or log."""
    already = _make_article(clean_text="this was already fetched earlier")
    repo = MagicMock(spec=Repository)
    repo.get_article_by_id.return_value = already
    repo.upsert_article.return_value = None

    ctx = _make_ctx(tmp_path, repo, total=1)
    row = _make_row(already)

    mutate = MagicMock()

    persisted = await _persist_and_log(
        ctx,
        row,
        mutate=mutate,
        log_suffix=" (http 503)",
    )

    assert persisted is False
    mutate.assert_not_called()
    repo.upsert_article.assert_not_called()
    assert ctx.done_count == [0]


@pytest.mark.asyncio
async def test_persist_and_log_skips_when_row_missing(tmp_path: Path) -> None:
    """If the DB row is gone (missing), helper treats it as 'skip' and does not write."""
    repo = MagicMock(spec=Repository)
    repo.get_article_by_id.return_value = None
    repo.upsert_article.return_value = None

    dummy = _make_article()
    ctx = _make_ctx(tmp_path, repo, total=1)
    row = _make_row(dummy)

    persisted = await _persist_and_log(
        ctx,
        row,
        mutate=lambda a: a,
        log_suffix=" (http 404)",
    )

    assert persisted is False
    repo.upsert_article.assert_not_called()
    assert ctx.done_count == [0]


@pytest.mark.asyncio
async def test_persist_and_log_counter_is_shared_across_branches(tmp_path: Path) -> None:
    """Each successful branch bumps the shared ``done_count[0]``; race-lost writes do not."""
    shared_counter = [4]
    ctx_repo = MagicMock(spec=Repository)
    # First call returns unfilled row (write proceeds); second returns already-filled (skip).
    fresh = _make_article()
    filled = _make_article(clean_text="already done")
    ctx_repo.get_article_by_id.side_effect = [fresh, filled]
    ctx_repo.upsert_article.return_value = None

    ctx = _make_ctx(tmp_path, ctx_repo, total=10, done_count=shared_counter)
    row = _make_row(fresh)

    first = await _persist_and_log(
        ctx, row, mutate=lambda a: a.with_updates(clean_text="x"), log_suffix=""
    )
    second = await _persist_and_log(
        ctx, row, mutate=lambda a: setattr(a, "clean_text", "y"), log_suffix=""
    )

    assert first is True
    assert second is False
    assert shared_counter == [5]


@pytest.mark.asyncio
async def test_persist_and_log_acquires_locks_in_order(tmp_path: Path) -> None:
    """Helper must enter ``db_lock`` before ``done_lock`` (ordering invariant)."""
    order: list[str] = []

    class TracingLock:
        def __init__(self, label: str) -> None:
            self._label = label
            self._inner = asyncio.Lock()

        async def __aenter__(self) -> object:
            order.append(f"enter:{self._label}")
            await self._inner.acquire()
            return self

        async def __aexit__(self, *exc: object) -> None:
            self._inner.release()
            order.append(f"exit:{self._label}")

    fresh = _make_article()
    repo = MagicMock(spec=Repository)
    repo.get_article_by_id.return_value = fresh
    repo.upsert_article.return_value = None

    ctx = _make_ctx(tmp_path, repo, total=1)
    ctx_patched = ArticleHtmlFetchContext(
        repo=ctx.repo,
        root=ctx.root,
        scraping=ctx.scraping,
        limiter=ctx.limiter,
        errors=ctx.errors,
        coauth=ctx.coauth,
        warns=ctx.warns,
        sem=ctx.sem,
        db_lock=TracingLock("db"),  # type: ignore[arg-type]
        done_lock=TracingLock("done"),  # type: ignore[arg-type]
        done_count=ctx.done_count,
        total=ctx.total,
    )
    row = _make_row(fresh)

    await _persist_and_log(
        ctx_patched,
        row,
        mutate=lambda a: a.with_updates(clean_text="x"),
        log_suffix="",
    )

    # db_lock must be fully entered/exited before done_lock is taken.
    assert order == [
        "enter:db",
        "exit:db",
        "enter:done",
        "exit:done",
    ]


@pytest.mark.asyncio
async def test_persist_and_log_dispatches_via_asyncio_to_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repository calls are offloaded to a worker thread to avoid blocking the loop."""
    to_thread_mock = AsyncMock()
    fresh = _make_article()
    to_thread_mock.side_effect = [fresh, None]

    import forensics.scraper.fetcher as fetcher_mod

    monkeypatch.setattr(fetcher_mod.asyncio, "to_thread", to_thread_mock)

    repo = MagicMock(spec=Repository)
    ctx = _make_ctx(tmp_path, repo, total=1)
    row = _make_row(fresh)

    persisted = await _persist_and_log(
        ctx,
        row,
        mutate=lambda a: a.with_updates(clean_text="x"),
        log_suffix="",
    )

    assert persisted is True
    assert to_thread_mock.await_count == 2
    assert to_thread_mock.await_args_list[0].args[0] is repo.get_article_by_id
    assert to_thread_mock.await_args_list[1].args[0] is repo.upsert_article
