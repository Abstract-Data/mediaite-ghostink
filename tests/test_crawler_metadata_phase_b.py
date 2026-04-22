"""Phase B: parallel author metadata ingestion (bounded gather, shared limiter)."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from forensics.config.settings import ForensicsSettings, ScrapingConfig
from forensics.models.author import AuthorManifest
from forensics.scraper import crawler as crawler_mod
from forensics.scraper.client import client_headers
from forensics.scraper.crawler import _author_config_from_manifest, collect_article_metadata
from forensics.storage.repository import Repository, init_db


def _write_manifest(path: Path, manifests: list[AuthorManifest]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for m in manifests:
            fh.write(m.model_dump_json() + "\n")


def _posts_handler() -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/wp/v2/posts" not in u:
            return httpx.Response(404, json={"error": "unmocked"})
        qs = parse_qs(urlparse(u).query)
        author_wp = int(qs["author"][0])
        page = int(qs.get("page", ["1"])[0])
        posts = [
            {
                "id": author_wp * 1000 + page * 10 + i,
                "link": f"https://www.mediaite.com/2024/a{author_wp}/p{page}/x{i}/",
                "title": {"rendered": f"T-{author_wp}-{page}-{i}"},
                "date": "2024-01-01T12:00:00",
                "modified": None,
                "meta": {},
            }
            for i in range(2)
        ]
        return httpx.Response(200, json=posts, headers={"X-WP-TotalPages": "3"})

    return handler


@pytest.mark.asyncio
async def test_collect_article_metadata_parallel_authors_http_overlaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Several authors in flight: metadata HTTP work overlaps; shared limiter is one instance."""
    discovered = datetime(2026, 1, 1, tzinfo=UTC)
    manifests = [
        AuthorManifest(
            wp_id=i,
            name=f"Author {i}",
            slug=f"author-{i}",
            total_posts=50,
            discovered_at=discovered,
        )
        for i in range(1, 6)
    ]
    manifest_path = tmp_path / "authors_manifest.jsonl"
    _write_manifest(manifest_path, manifests)

    author_cfgs = [_author_config_from_manifest(m) for m in manifests]
    settings = ForensicsSettings(
        authors=author_cfgs,
        scraping=ScrapingConfig(
            max_concurrent=4,
            max_retries=2,
            rate_limit_seconds=0.0,
            rate_limit_jitter=0.0,
            retry_backoff_seconds=0.01,
        ),
    )

    db_path = tmp_path / "articles.db"
    init_db(db_path)
    errors_path = tmp_path / "scrape_errors.jsonl"

    def fake_client(scraping: ScrapingConfig):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(_posts_handler()),
            headers=client_headers(scraping),
            timeout=30.0,
            follow_redirects=True,
        )

    in_flight = {"n": 0, "max": 0}
    orig_request = crawler_mod.request_with_retry

    async def counting_request(*args: object, **kwargs: object) -> httpx.Response:
        phase = kwargs.get("phase", "")
        if phase == "metadata":
            in_flight["n"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["n"])
            await asyncio.sleep(0.04)
            try:
                return await orig_request(*args, **kwargs)  # type: ignore[misc]
            finally:
                in_flight["n"] -= 1
        return await orig_request(*args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr(crawler_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(crawler_mod, "create_scraping_client", fake_client)
    monkeypatch.setattr(crawler_mod, "request_with_retry", counting_request)

    inserted = await collect_article_metadata(
        db_path,
        settings,
        manifest_path=manifest_path,
        errors_path=errors_path,
    )
    # 5 authors × 3 pages × 2 posts/page
    assert inserted == 30
    assert in_flight["max"] >= 2, "expected overlapping metadata HTTP across authors"

    with Repository(db_path) as repo:
        all_rows = repo.get_all_articles()
    assert len(all_rows) == 30


@pytest.mark.asyncio
async def test_collect_article_metadata_request_error_isolated_per_author(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One author's metadata fetch raises after retries; others still complete."""
    discovered = datetime(2026, 2, 1, tzinfo=UTC)
    manifests = [
        AuthorManifest(
            wp_id=i,
            name=f"Author {i}",
            slug=f"author-{i}",
            total_posts=50,
            discovered_at=discovered,
        )
        for i in range(1, 6)
    ]
    manifest_path = tmp_path / "authors_manifest.jsonl"
    _write_manifest(manifest_path, manifests)
    author_cfgs = [_author_config_from_manifest(m) for m in manifests]
    settings = ForensicsSettings(
        authors=author_cfgs,
        scraping=ScrapingConfig(
            max_concurrent=4,
            max_retries=0,
            rate_limit_seconds=0.0,
            rate_limit_jitter=0.0,
            retry_backoff_seconds=0.01,
        ),
    )

    db_path = tmp_path / "articles.db"
    init_db(db_path)
    errors_path = tmp_path / "scrape_errors.jsonl"

    def fake_client(scraping: ScrapingConfig):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(_posts_handler()),
            headers=client_headers(scraping),
            timeout=30.0,
            follow_redirects=True,
        )

    boom_once = {"fired": False}
    orig_request = crawler_mod.request_with_retry

    async def flaky_request(*args: object, **kwargs: object) -> httpx.Response:
        phase = kwargs.get("phase", "")
        if phase != "metadata":
            return await orig_request(*args, **kwargs)  # type: ignore[misc]
        url = str(args[4]) if len(args) > 4 else ""
        qs = parse_qs(urlparse(url).query)
        if qs.get("author") == ["3"] and not boom_once["fired"]:
            boom_once["fired"] = True
            raise httpx.RequestError(
                "simulated transport failure",
                request=httpx.Request("GET", url),
            )
        return await orig_request(*args, **kwargs)  # type: ignore[misc]

    monkeypatch.setattr(crawler_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(crawler_mod, "create_scraping_client", fake_client)
    monkeypatch.setattr(crawler_mod, "request_with_retry", flaky_request)

    inserted = await collect_article_metadata(
        db_path,
        settings,
        manifest_path=manifest_path,
        errors_path=errors_path,
    )
    assert inserted == 24  # 4 authors × 6 posts

    with Repository(db_path) as repo:
        assert len(repo.get_all_articles()) == 24

    err_text = errors_path.read_text(encoding="utf-8")
    assert "metadata_author" in err_text
    assert re.search(r"author-3", err_text)
    assert any(
        json.loads(line).get("phase") == "metadata_author" for line in err_text.strip().splitlines()
    )
