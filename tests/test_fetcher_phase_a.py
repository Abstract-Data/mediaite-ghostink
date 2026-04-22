"""Phase A scraper concurrency: fetcher lock scope, discovery fan-out, JSONL async."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
import httpx
import pytest

from forensics.config.settings import AuthorConfig, ForensicsSettings, ScrapingConfig
from forensics.models.article import Article
from forensics.models.author import Author
from forensics.scraper import crawler as crawler_mod
from forensics.scraper import fetcher as fetcher_mod
from forensics.scraper.client import client_headers
from forensics.scraper.crawler import stable_article_id
from forensics.scraper.fetcher import _fetch_one_article_html, fetch_articles
from forensics.storage.export import append_jsonl_async
from forensics.storage.repository import Repository, UnfetchedArticle


@pytest.mark.asyncio
async def test_append_jsonl_async_writes_line(tmp_path: Path) -> None:
    path = tmp_path / "side.jsonl"
    await append_jsonl_async(path, {"k": 1})
    await append_jsonl_async(path, {"k": 2})
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert '"k": 1' in lines[0]


@pytest.mark.asyncio
async def test_discover_authors_post_count_calls_overlap(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under max_concurrent > 1, multiple discover_count requests overlap in time."""
    manifest = tmp_path / "authors_manifest.jsonl"
    errors = tmp_path / "scrape_errors.jsonl"

    users_json = [
        {"id": 1, "name": "A", "slug": "a"},
        {"id": 2, "name": "B", "slug": "b"},
        {"id": 3, "name": "C", "slug": "c"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/wp/v2/users" in u:
            return httpx.Response(
                200,
                json=users_json,
                headers={"X-WP-TotalPages": "1"},
            )
        if "/wp/v2/posts" in u and "author=" in u:
            return httpx.Response(200, json=[], headers={"X-WP-Total": "3"})
        return httpx.Response(404, json={"error": "unmocked"})

    in_flight = {"n": 0, "max": 0}

    orig_request = crawler_mod.request_with_retry

    async def counting_request(*args: object, **kwargs: object) -> httpx.Response:
        phase = kwargs.get("phase", "")
        if phase == "discover_count":
            in_flight["n"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["n"])
            await asyncio.sleep(0.05)
            try:
                return await orig_request(*args, **kwargs)  # type: ignore[misc]
            finally:
                in_flight["n"] -= 1
        return await orig_request(*args, **kwargs)  # type: ignore[misc]

    def fake_client(scraping: ScrapingConfig):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers=client_headers(scraping),
            timeout=30.0,
            follow_redirects=True,
        )

    monkeypatch.setattr(crawler_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(crawler_mod, "create_scraping_client", fake_client)
    monkeypatch.setattr(crawler_mod, "request_with_retry", counting_request)

    settings = ForensicsSettings(
        authors=[
            AuthorConfig(
                name="N",
                slug="n",
                outlet="mediaite.com",
                role="target",
                archive_url="https://www.mediaite.com/author/n/",
                baseline_start=date(2020, 1, 1),
                baseline_end=date(2023, 1, 1),
            )
        ],
        scraping=ScrapingConfig(
            max_concurrent=4,
            rate_limit_seconds=0.0,
            rate_limit_jitter=0.0,
        ),
    )
    n = await crawler_mod.discover_authors(
        settings,
        force_refresh=True,
        manifest_path=manifest,
        errors_path=errors,
    )
    assert n == 3
    assert in_flight["max"] >= 2, "expected overlapping discover_count HTTP calls"
    text = manifest.read_text(encoding="utf-8")
    for slug in ("a", "b", "c"):
        assert slug in text


def _minimal_html(body: str = "word " * 30) -> str:
    return f"""<!doctype html><html><head><title>T</title></head><body><article>{body}</article></body></html>"""


@pytest.mark.asyncio
async def test_fetch_http_error_persists_placeholder(
    tmp_path: Path,
    sample_author: Author,
    sample_article: Article,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "articles.db"
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(sample_article)

    row = UnfetchedArticle(
        sample_article.id,
        str(sample_article.url),
        "X",
        sample_article.published_date,
    )

    async def fake_request(
        client: object,
        limiter: object,
        scraping: object,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        return httpx.Response(503, text="no", request=httpx.Request(method, url))

    monkeypatch.setattr(fetcher_mod, "request_with_retry", fake_request)

    scraping = ScrapingConfig(
        rate_limit_seconds=0.0,
        rate_limit_jitter=0.0,
        max_concurrent=2,
        max_retries=0,
        retry_backoff_seconds=0.01,
    )
    sem = asyncio.Semaphore(2)
    db_lock = asyncio.Lock()
    done_lock = asyncio.Lock()
    done_count = [0]

    with Repository(db_path) as repo:
        async with httpx.AsyncClient() as client:
            await _fetch_one_article_html(
                client,
                row,
                repo=repo,
                root=tmp_path,
                scraping=scraping,
                limiter=fetcher_mod.RateLimiter(0.0, 0.0),
                errors=tmp_path / "e.jsonl",
                coauth=tmp_path / "c.jsonl",
                warns=tmp_path / "w.jsonl",
                sem=sem,
                db_lock=db_lock,
                done_lock=done_lock,
                done_count=done_count,
                total=1,
            )

    with Repository(db_path) as repo:
        art = repo.get_article_by_id(sample_article.id)
    assert art is not None
    assert "[HTTP_ERROR:503]" in art.clean_text
    assert done_count[0] == 1


@pytest.mark.asyncio
async def test_fetch_off_domain_persists_redirect_marker(
    tmp_path: Path,
    sample_author: Author,
    sample_article: Article,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "articles.db"
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(sample_article)

    row = UnfetchedArticle(
        sample_article.id,
        str(sample_article.url),
        "X",
        sample_article.published_date,
    )

    off_req = httpx.Request("GET", "https://off-domain.example/story/")

    async def fake_request(
        client: object,
        limiter: object,
        scraping: object,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        return httpx.Response(200, request=off_req, text="<html></html>")

    monkeypatch.setattr(fetcher_mod, "request_with_retry", fake_request)

    scraping = ScrapingConfig(
        rate_limit_seconds=0.0,
        rate_limit_jitter=0.0,
        max_concurrent=2,
        max_retries=0,
        retry_backoff_seconds=0.01,
    )
    sem = asyncio.Semaphore(2)
    db_lock = asyncio.Lock()
    done_lock = asyncio.Lock()
    done_count = [0]
    errors = tmp_path / "e.jsonl"

    with Repository(db_path) as repo:
        async with httpx.AsyncClient() as client:
            await _fetch_one_article_html(
                client,
                row,
                repo=repo,
                root=tmp_path,
                scraping=scraping,
                limiter=fetcher_mod.RateLimiter(0.0, 0.0),
                errors=errors,
                coauth=tmp_path / "c.jsonl",
                warns=tmp_path / "w.jsonl",
                sem=sem,
                db_lock=db_lock,
                done_lock=done_lock,
                done_count=done_count,
                total=1,
            )

    with Repository(db_path) as repo:
        art = repo.get_article_by_id(sample_article.id)
    assert art is not None
    assert "[REDIRECT:" in art.clean_text
    assert done_count[0] == 1


@pytest.mark.asyncio
async def test_fetch_resume_skip_when_already_fetched(
    tmp_path: Path,
    sample_author: Author,
    sample_article: Article,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "articles.db"
    filled = sample_article.model_copy(
        update={
            "clean_text": "already here " * 10,
            "word_count": 20,
            "content_hash": "x",
        }
    )
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(filled)

    row = UnfetchedArticle(
        sample_article.id,
        str(sample_article.url),
        "X",
        sample_article.published_date,
    )

    called = {"n": 0}

    async def fake_request(
        client: object,
        limiter: object,
        scraping: object,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, text=_minimal_html(), request=httpx.Request(method, url))

    monkeypatch.setattr(fetcher_mod, "request_with_retry", fake_request)

    scraping = ScrapingConfig(
        rate_limit_seconds=0.0,
        rate_limit_jitter=0.0,
        max_concurrent=2,
        max_retries=0,
        retry_backoff_seconds=0.01,
    )
    sem = asyncio.Semaphore(2)
    db_lock = asyncio.Lock()
    done_lock = asyncio.Lock()
    done_count = [0]

    with Repository(db_path) as repo:
        async with httpx.AsyncClient() as client:
            await _fetch_one_article_html(
                client,
                row,
                repo=repo,
                root=tmp_path,
                scraping=scraping,
                limiter=fetcher_mod.RateLimiter(0.0, 0.0),
                errors=tmp_path / "e.jsonl",
                coauth=tmp_path / "c.jsonl",
                warns=tmp_path / "w.jsonl",
                sem=sem,
                db_lock=db_lock,
                done_lock=done_lock,
                done_count=done_count,
                total=1,
            )

    assert called["n"] == 1
    assert done_count[0] == 0
    with Repository(db_path) as repo:
        art = repo.get_article_by_id(sample_article.id)
    assert art is not None
    assert art.clean_text == filled.clean_text


@pytest.mark.asyncio
async def test_fetch_success_persists_body_and_raw_path(
    tmp_path: Path,
    sample_author: Author,
    sample_article: Article,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "articles.db"
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(sample_article)

    row = UnfetchedArticle(
        sample_article.id,
        str(sample_article.url),
        "X",
        sample_article.published_date,
    )

    async def fake_request_success(
        client: object,
        limiter: object,
        scraping: object,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        return httpx.Response(200, text=_minimal_html(), request=httpx.Request(method, url))

    monkeypatch.setattr(fetcher_mod, "request_with_retry", fake_request_success)

    scraping = ScrapingConfig(
        rate_limit_seconds=0.0,
        rate_limit_jitter=0.0,
        max_concurrent=2,
        max_retries=0,
        retry_backoff_seconds=0.01,
    )
    sem = asyncio.Semaphore(2)
    db_lock = asyncio.Lock()
    done_lock = asyncio.Lock()
    done_count = [0]

    with Repository(db_path) as repo:
        async with httpx.AsyncClient() as client:
            await _fetch_one_article_html(
                client,
                row,
                repo=repo,
                root=tmp_path,
                scraping=scraping,
                limiter=fetcher_mod.RateLimiter(0.0, 0.0),
                errors=tmp_path / "e.jsonl",
                coauth=tmp_path / "c.jsonl",
                warns=tmp_path / "w.jsonl",
                sem=sem,
                db_lock=db_lock,
                done_lock=done_lock,
                done_count=done_count,
                total=1,
            )

    with Repository(db_path) as repo:
        art = repo.get_article_by_id(sample_article.id)
    assert art is not None
    assert "word" in art.clean_text
    assert art.raw_html_path.startswith("raw/2024/")
    assert done_count[0] == 1


@pytest.mark.asyncio
async def test_parallel_fetches_complete_all_tasks(
    tmp_path: Path,
    sample_author: Author,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With max_concurrent=4, all unfetched rows are processed (gather + shared repo)."""
    db_path = tmp_path / "articles.db"

    async def fake_request_parallel(
        client: object,
        limiter: object,
        scraping: object,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        return httpx.Response(200, text=_minimal_html("x"), request=httpx.Request(method, url))

    monkeypatch.setattr(fetcher_mod, "request_with_retry", fake_request_parallel)

    articles: list[Article] = []
    for i in range(4):
        u = f"https://www.mediaite.com/2024/01/{i + 1:02d}/post/"
        articles.append(
            Article(
                id=stable_article_id(u),
                author_id=sample_author.id,  # type: ignore[attr-defined]
                url=u,
                title=f"P{i}",
                published_date=datetime(2024, 1, i + 1, tzinfo=UTC),
                clean_text="",
                word_count=0,
                content_hash="",
            )
        )

    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)
        for a in articles:
            repo.upsert_article(a)

    settings = ForensicsSettings(
        authors=[
            AuthorConfig(
                name=sample_author.name,
                slug=sample_author.slug,
                outlet=sample_author.outlet,
                role=sample_author.role,
                archive_url=sample_author.archive_url,
                baseline_start=sample_author.baseline_start,
                baseline_end=sample_author.baseline_end,
            )
        ],
        scraping=ScrapingConfig(
            max_concurrent=4,
            rate_limit_seconds=0.0,
            rate_limit_jitter=0.0,
            max_retries=0,
            retry_backoff_seconds=0.01,
        ),
    )

    def fake_client(scraping: ScrapingConfig):
        return httpx.AsyncClient(
            headers=client_headers(scraping),
            timeout=30.0,
            follow_redirects=True,
        )

    monkeypatch.setattr(fetcher_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(fetcher_mod, "create_scraping_client", fake_client)

    n = await fetch_articles(db_path, settings, dry_run=False, errors_path=tmp_path / "e.jsonl")

    assert n == 4

    with Repository(db_path) as repo:
        for a in articles:
            art = repo.get_article_by_id(a.id)
            assert art is not None
            assert art.clean_text.strip()
            assert art.word_count > 0
