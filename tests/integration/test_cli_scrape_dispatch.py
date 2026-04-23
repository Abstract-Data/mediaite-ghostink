"""Exercise Typer scrape flag dispatch (no live HTTP)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import typer

from forensics.cli import scrape as scrape_mod
from forensics.config import get_settings


@pytest.mark.asyncio
async def test_scrape_dry_run_requires_fetch(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    rc = await scrape_mod.dispatch_scrape(
        discover=False,
        metadata=False,
        fetch=False,
        dedup=False,
        archive=False,
        dry_run=True,
        force_refresh=False,
    )
    assert rc == 1


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

    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scrape_mod, "archive_raw_year_dirs", fake_archive)

    with caplog.at_level(logging.INFO, logger="forensics.cli.scrape"):
        rc = await scrape_mod.dispatch_scrape(
            discover=False,
            metadata=False,
            fetch=False,
            dedup=False,
            archive=True,
            dry_run=False,
            force_refresh=False,
        )
    assert rc == 0
    assert "archive: compressed 2" in caplog.text


@pytest.mark.asyncio
async def test_scrape_dedup_only(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        scrape_mod,
        "deduplicate_articles",
        lambda db, *, hamming_threshold=3: ["a", "b"],
    )

    with caplog.at_level(logging.INFO, logger="forensics.cli.scrape"):
        rc = await scrape_mod.dispatch_scrape(
            discover=False,
            metadata=False,
            fetch=False,
            dedup=True,
            archive=False,
            dry_run=False,
            force_refresh=False,
        )
    assert rc == 0
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

    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scrape_mod, "fetch_articles", fake_fetch)

    with caplog.at_level(logging.INFO, logger="forensics.cli.scrape"):
        rc = await scrape_mod.dispatch_scrape(
            discover=False,
            metadata=False,
            fetch=True,
            dedup=False,
            archive=False,
            dry_run=True,
            force_refresh=False,
        )
    assert rc == 0
    assert "would fetch 5" in caplog.text


@pytest.mark.asyncio
async def test_scrape_unsupported_flags(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    rc = await scrape_mod.dispatch_scrape(
        discover=True,
        metadata=False,
        fetch=True,
        dedup=False,
        archive=False,
        dry_run=False,
        force_refresh=False,
    )
    assert rc == 1


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

    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scrape_mod, "discover_authors", fake_discover)

    with caplog.at_level(logging.INFO, logger="forensics.cli.scrape"):
        rc = await scrape_mod.dispatch_scrape(
            discover=True,
            metadata=False,
            fetch=False,
            dedup=False,
            archive=False,
            dry_run=False,
            force_refresh=False,
        )
    assert rc == 0
    assert "discover: skipped" in caplog.text


@pytest.mark.asyncio
async def test_scrape_metadata_only_missing_manifest(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    rc = await scrape_mod.dispatch_scrape(
        discover=False,
        metadata=True,
        fetch=False,
        dedup=False,
        archive=False,
        dry_run=False,
        force_refresh=False,
    )
    assert rc == 1


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
async def test_scrape_discover_placeholder_ok_with_all_authors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = tmp_path / "bad.toml"
    cfg.write_text(PLACEHOLDER_TOML.strip() + "\n", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg))
    get_settings.cache_clear()
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)

    async def fake_discover(
        settings,
        *,
        force_refresh: bool = False,
        manifest_path=None,
        errors_path=None,
    ):
        return 0

    monkeypatch.setattr(scrape_mod, "discover_authors", fake_discover)

    rc = await scrape_mod.dispatch_scrape(
        discover=True,
        metadata=False,
        fetch=False,
        dedup=False,
        archive=False,
        dry_run=False,
        force_refresh=False,
        all_authors=True,
    )
    assert rc == 0
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_scrape_rejects_placeholder_template_authors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = tmp_path / "bad.toml"
    cfg.write_text(PLACEHOLDER_TOML.strip() + "\n", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg))
    get_settings.cache_clear()
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    with pytest.raises(typer.BadParameter, match="(?i)placeholder"):
        await scrape_mod.dispatch_scrape(
            discover=True,
            metadata=False,
            fetch=False,
            dedup=False,
            archive=False,
            dry_run=False,
            force_refresh=False,
        )
    get_settings.cache_clear()
