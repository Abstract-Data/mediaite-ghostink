"""Unit tests for the three ``_handle_*`` branches in ``_fetch_one_article_html``.

The F3 refactor split the 80-line dispatch function into three async handlers
plus a thin driver. The existing ``test_fetcher_mutations.py`` exercises
``_persist_and_log`` directly; these tests pin the handler contracts so a
regression in any branch shows up immediately rather than being masked by the
driver.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from forensics.config.settings import ScrapingConfig
from forensics.models.article import Article
from forensics.scraper.fetcher import (
    ArticleHtmlFetchContext,
    RateLimiter,
    _handle_http_failure,
    _handle_off_domain,
    _handle_success,
)
from forensics.storage.repository import Repository, UnfetchedArticle


def _article(
    *,
    clean_text: str = "",
    url: str = "https://www.mediaite.com/p/sample/",
) -> Article:
    return Article(
        id="article-handler-1",
        author_id="author-handler-1",
        url=url,
        title="T",
        published_date=datetime(2026, 1, 2, tzinfo=UTC),
        clean_text=clean_text,
        word_count=0 if not clean_text else len(clean_text.split()),
        content_hash="",
    )


def _row(article: Article, *, author: str = "Author H") -> UnfetchedArticle:
    return UnfetchedArticle(
        article.id,
        str(article.url),
        author,
        article.published_date,
    )


def _ctx(tmp_path: Path, repo: Repository | MagicMock) -> ArticleHtmlFetchContext:
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
        errors=tmp_path / "errors.jsonl",
        coauth=tmp_path / "coauth.jsonl",
        warns=tmp_path / "warns.jsonl",
        sem=asyncio.Semaphore(1),
        db_lock=asyncio.Lock(),
        done_lock=asyncio.Lock(),
        done_count=[0],
        total=3,
    )


@pytest.mark.asyncio
async def test_handle_http_failure_writes_marker_and_logs(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fresh = _article()
    repo = MagicMock(spec=Repository)
    repo.get_article_by_id.return_value = fresh
    repo.upsert_article.return_value = None

    ctx = _ctx(tmp_path, repo)
    row = _row(fresh, author="Author HF")
    response = httpx.Response(502, request=httpx.Request("GET", str(fresh.url)))
    scraped_at = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)

    with caplog.at_level(logging.INFO, logger="forensics.scraper.fetcher"):
        await _handle_http_failure(ctx, row, response=response, scraped_at=scraped_at)

    repo.upsert_article.assert_called_once()
    written = repo.upsert_article.call_args.args[0]
    assert written.clean_text == "[HTTP_ERROR:502]"
    assert written.word_count == 0
    assert written.scraped_at == scraped_at
    assert ctx.done_count == [1]
    assert any("(http 502)" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_handle_off_domain_logs_error_and_clears_raw_path(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fresh = _article()
    repo = MagicMock(spec=Repository)
    repo.get_article_by_id.return_value = fresh
    repo.upsert_article.return_value = None

    ctx = _ctx(tmp_path, repo)
    row = _row(fresh, author="Author OD")
    response = httpx.Response(200, request=httpx.Request("GET", str(fresh.url)))
    scraped_at = datetime(2026, 4, 22, 12, 5, tzinfo=UTC)
    final_host = "other.example"

    with caplog.at_level(logging.INFO, logger="forensics.scraper.fetcher"):
        await _handle_off_domain(
            ctx,
            row,
            response=response,
            scraped_at=scraped_at,
            final_host=final_host,
        )

    # Off-domain handler appends a structured error record to the errors JSONL.
    assert ctx.errors.is_file()
    error_body = ctx.errors.read_text(encoding="utf-8")
    assert "redirect_off_domain:other.example" in error_body

    repo.upsert_article.assert_called_once()
    written = repo.upsert_article.call_args.args[0]
    assert written.clean_text == f"[REDIRECT:{final_host}]"
    assert written.raw_html_path == ""
    assert written.word_count == 0
    assert ctx.done_count == [1]
    assert any(f"(off-domain {final_host})" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_handle_success_writes_parsed_body_and_bumps_counter(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fresh = _article()
    repo = MagicMock(spec=Repository)
    # Both db_lock lookups see the unfetched row.
    repo.get_article_by_id.side_effect = [fresh, fresh]
    repo.upsert_article.return_value = None

    ctx = _ctx(tmp_path, repo)
    row = _row(fresh, author="Author OK")
    body_text = " ".join(["body"] * 80)
    html = (
        "<html><head><title>Hello</title></head>"
        f"<body><article><p>{body_text}</p></article></body></html>"
    )
    response = httpx.Response(200, request=httpx.Request("GET", str(fresh.url)), text=html)
    scraped_at = datetime(2026, 4, 22, 12, 30, tzinfo=UTC)

    with caplog.at_level(logging.INFO, logger="forensics.scraper.fetcher"):
        await _handle_success(
            ctx,
            row,
            response=response,
            scraped_at=scraped_at,
            year=2026,
        )

    repo.upsert_article.assert_called_once()
    written = repo.upsert_article.call_args.args[0]
    assert written.scraped_at == scraped_at
    assert written.word_count > 0
    # Raw HTML is persisted under data/raw/{year}/{id}.html relative to ctx.root.
    raw_file = tmp_path / "data" / "raw" / "2026" / f"{fresh.id}.html"
    assert raw_file.is_file()
    assert written.raw_html_path == f"raw/2026/{fresh.id}.html"
    assert ctx.done_count == [1]
    assert any(
        f"1/{ctx.total} articles for Author OK" in rec.getMessage() for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_handle_success_skips_when_row_filled_before_parse(
    tmp_path: Path,
) -> None:
    """If a concurrent worker filled the row first, the handler returns without upsert."""
    already_filled = _article(clean_text="someone else got here first")
    repo = MagicMock(spec=Repository)
    # First db_lock check sees the filled row and short-circuits.
    repo.get_article_by_id.return_value = already_filled
    repo.upsert_article.return_value = None

    ctx = _ctx(tmp_path, repo)
    row = _row(already_filled)
    response = httpx.Response(
        200, request=httpx.Request("GET", str(already_filled.url)), text="<html/>"
    )

    await _handle_success(
        ctx,
        row,
        response=response,
        scraped_at=datetime(2026, 4, 22, 12, 30, tzinfo=UTC),
        year=2026,
    )

    repo.upsert_article.assert_not_called()
    assert ctx.done_count == [0]


@pytest.mark.asyncio
async def test_handle_success_skips_between_parse_and_persist(
    tmp_path: Path,
) -> None:
    """If the row fills between the first and second db_lock check, persist is skipped."""
    fresh = _article()
    filled = _article(clean_text="raced after parse")
    repo = MagicMock(spec=Repository)
    repo.get_article_by_id.side_effect = [fresh, filled]
    repo.upsert_article.return_value = None

    ctx = _ctx(tmp_path, repo)
    row = _row(fresh)
    response = httpx.Response(
        200,
        request=httpx.Request("GET", str(fresh.url)),
        text="<html><body><article><p>hi there</p></article></body></html>",
    )

    await _handle_success(
        ctx,
        row,
        response=response,
        scraped_at=datetime(2026, 4, 22, 12, 30, tzinfo=UTC),
        year=2026,
    )

    repo.upsert_article.assert_not_called()
    assert ctx.done_count == [0]
