"""Async scrape paths with mocked HTTP (P2-TEST-2)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from forensics.config import get_settings
from forensics.scraper import crawler as crawler_mod
from forensics.scraper.client import client_headers


@pytest.mark.asyncio
async def test_discover_authors_writes_manifest_with_mock_http(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "authors_manifest.jsonl"
    errors = tmp_path / "scrape_errors.jsonl"

    def handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "/wp/v2/users" in u:
            return httpx.Response(
                200,
                json=[{"id": 1, "name": "Fixture Author", "slug": "fixture-author"}],
                headers={"X-WP-TotalPages": "1"},
            )
        if "/wp/v2/posts" in u and "author=1" in u:
            return httpx.Response(200, json=[], headers={"X-WP-Total": "7"})
        return httpx.Response(404, json={"error": "unmocked"})

    def fake_client(scraping):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers=client_headers(scraping),
            timeout=30.0,
            follow_redirects=True,
        )

    monkeypatch.setattr(crawler_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(crawler_mod, "create_scraping_client", fake_client)

    settings = get_settings()
    n = await crawler_mod.discover_authors(
        settings,
        force_refresh=True,
        manifest_path=manifest,
        errors_path=errors,
    )
    assert n == 1
    text = manifest.read_text(encoding="utf-8")
    assert "fixture-author" in text
    assert "Fixture Author" in text
