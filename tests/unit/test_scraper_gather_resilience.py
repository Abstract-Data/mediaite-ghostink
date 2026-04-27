"""Resilience of parallel metadata ingest (``collect_article_metadata`` gather path)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from forensics.config import get_settings
from forensics.models import Author
from forensics.models.author import AuthorManifest
from forensics.scraper import crawler as crawler_mod
from forensics.scraper.crawler import collect_article_metadata
from forensics.storage.repository import Repository, init_db
from forensics.survey.shared_byline import is_shared_byline


def _write_manifest(path: Path, slugs: tuple[str, ...]) -> None:
    discovered = datetime(2024, 1, 1, tzinfo=UTC)
    lines = []
    for i, slug in enumerate(slugs):
        m = AuthorManifest(
            wp_id=1000 + i,
            name=f"Author {slug}",
            slug=slug,
            total_posts=1,
            discovered_at=discovered,
        )
        lines.append(m.model_dump_json())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_minimal_config(path: Path, slugs: tuple[str, ...]) -> None:
    blocks = []
    for slug in slugs:
        role = "target" if slug == slugs[0] else "control"
        blocks.append(
            f'[[authors]]\nname = "N {slug}"\nslug = "{slug}"\noutlet = "mediaite.com"\n'
            f'role = "{role}"\narchive_url = "https://www.mediaite.com/author/{slug}/"\n'
            "baseline_start = 2020-01-01\nbaseline_end = 2024-12-31\n"
        )
    body = (
        "\n".join(blocks)
        + "\n[scraping]\nrate_limit_seconds = 0.01\n\n[analysis]\n\n[features]\n\n[report]\n"
    )
    path.write_text(body, encoding="utf-8")


@pytest.mark.asyncio
async def test_collect_article_metadata_survives_per_author_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One ``_ingest_author_posts`` failure must log + continue; siblings still persist."""
    root = tmp_path / "proj"
    data = root / "data"
    data.mkdir(parents=True)
    manifest = data / "authors_manifest.jsonl"
    errors = data / "scrape_errors.jsonl"
    cfg = root / "config.toml"
    slugs = ("ok-a", "boom", "ok-b")
    _write_manifest(manifest, slugs)
    _write_minimal_config(cfg, slugs)

    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg))
    get_settings.cache_clear()

    db_path = data / "articles.db"
    init_db(db_path)
    settings = get_settings()

    async def _ingest_stub(
        client,
        limiter,
        scraping,
        repo,
        cfg,
        by_slug,
        errors_path,
        db_lock,
        *,
        posts_query_suffix: str = "",
    ):
        del client, limiter, scraping, posts_query_suffix
        if cfg.slug == "boom":
            msg = "simulated author ingest failure"
            raise RuntimeError(msg)
        manifest_row = by_slug[cfg.slug]
        author = Author(
            id=crawler_mod._stable_author_id(cfg.slug),
            name=manifest_row.name,
            slug=cfg.slug,
            outlet=cfg.outlet,
            role=cfg.role,
            baseline_start=cfg.baseline_start,
            baseline_end=cfg.baseline_end,
            archive_url=cfg.archive_url,
            is_shared_byline=is_shared_byline(cfg.slug, manifest_row.name, cfg.outlet),
        )
        async with db_lock:
            await asyncio.to_thread(repo.upsert_author, author)
        return 1

    monkeypatch.setattr(crawler_mod, "_ingest_author_posts", _ingest_stub)
    monkeypatch.setattr(crawler_mod, "get_project_root", lambda: root)

    inserted = await collect_article_metadata(
        db_path,
        settings,
        manifest_path=manifest,
        errors_path=errors,
    )
    assert inserted == 2

    err_text = errors.read_text(encoding="utf-8")
    assert "boom" in err_text

    with Repository(db_path) as repo:
        repo.ensure_schema()
        assert repo.get_author_by_slug("ok-a") is not None
        assert repo.get_author_by_slug("ok-b") is not None
        assert repo.get_author_by_slug("boom") is None
