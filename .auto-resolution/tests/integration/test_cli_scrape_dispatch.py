"""Exercise ``forensics.cli`` scrape flag dispatch (no live HTTP)."""

from __future__ import annotations

import logging
from argparse import Namespace
from pathlib import Path

import pytest

from forensics import cli as cli_mod
from forensics.config import get_settings


def _ns(**kwargs: bool) -> Namespace:
    defaults = dict(
        discover=False,
        metadata=False,
        fetch=False,
        dedup=False,
        archive=False,
        dry_run=False,
        force_refresh=False,
    )
    defaults.update(kwargs)
    return Namespace(**defaults)


@pytest.mark.asyncio
async def test_scrape_dry_run_requires_fetch(
    tmp_path: Path, forensics_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_mod, "get_project_root", lambda: tmp_path)
    args = _ns(dry_run=True, fetch=False)
    assert await cli_mod._async_scrape(args) == 1


@pytest.mark.asyncio
async def test_scrape_archive_only(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fake_archive(root: Path, db_path: Path) -> int:
        assert db_path == tmp_path / "data/articles.db"
        return 2

    monkeypatch.setattr(cli_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_mod, "archive_raw_year_dirs", fake_archive)
    args = _ns(archive=True)
    with caplog.at_level(logging.INFO, logger="forensics.cli"):
        assert await cli_mod._async_scrape(args) == 0
    assert "archive: compressed 2" in caplog.text


@pytest.mark.asyncio
async def test_scrape_dedup_only(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(cli_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_mod, "deduplicate_articles", lambda db: ["a", "b"])
    args = _ns(dedup=True)
    with caplog.at_level(logging.INFO, logger="forensics.cli"):
        assert await cli_mod._async_scrape(args) == 0
    assert "dedup: marked 2" in caplog.text


@pytest.mark.asyncio
async def test_scrape_fetch_only_dry_run(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_fetch(db_path, settings, *, dry_run: bool = False, **kw):
        assert dry_run is True
        return 5

    monkeypatch.setattr(cli_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_mod, "fetch_articles", fake_fetch)
    args = _ns(fetch=True, dry_run=True)
    with caplog.at_level(logging.INFO, logger="forensics.cli"):
        assert await cli_mod._async_scrape(args) == 0
    assert "would fetch 5" in caplog.text


@pytest.mark.asyncio
async def test_scrape_unsupported_flags(
    tmp_path: Path, forensics_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_mod, "get_project_root", lambda: tmp_path)
    args = _ns(discover=True, fetch=True)
    assert await cli_mod._async_scrape(args) == 1


@pytest.mark.asyncio
async def test_scrape_discover_only_zero_authors(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_discover(
        settings,
        *,
        force_refresh: bool = False,
        manifest_path=None,
        errors_path=None,
    ):
        return 0

    monkeypatch.setattr(cli_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_mod, "discover_authors", fake_discover)
    args = _ns(discover=True)
    with caplog.at_level(logging.INFO, logger="forensics.cli"):
        assert await cli_mod._async_scrape(args) == 0
    assert "discover: skipped" in caplog.text


@pytest.mark.asyncio
async def test_scrape_metadata_only_missing_manifest(
    tmp_path: Path, forensics_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_mod, "get_project_root", lambda: tmp_path)
    args = _ns(metadata=True)
    assert await cli_mod._async_scrape(args) == 1


PLACEHOLDER_TOML = """
[[authors]]
name = "Placeholder Target"
slug = "placeholder-target"
outlet = "mediaite.com"
role = "target"
archive_url = "https://www.mediaite.com/author/placeholder-target/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[scraping]
"""


@pytest.mark.asyncio
async def test_scrape_rejects_placeholder_template_authors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cfg = tmp_path / "bad.toml"
    cfg.write_text(PLACEHOLDER_TOML.strip() + "\n", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg))
    get_settings.cache_clear()
    monkeypatch.setattr(cli_mod, "get_project_root", lambda: tmp_path)
    args = _ns(discover=True)
    with caplog.at_level(logging.ERROR, logger="forensics.cli"):
        assert await cli_mod._async_scrape(args) == 1
    assert "placeholder" in caplog.text.lower()
    get_settings.cache_clear()
