"""Scrape subcommand — WordPress discovery, metadata collection, HTML fetch."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer

from forensics.cli._helpers import config_fingerprint, guard_placeholder_authors
from forensics.config import get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.scraper.crawler import collect_article_metadata, discover_authors
from forensics.scraper.dedup import deduplicate_articles
from forensics.scraper.fetcher import archive_raw_year_dirs, fetch_articles
from forensics.storage.export import export_articles_jsonl
from forensics.storage.repository import insert_analysis_run

logger = logging.getLogger(__name__)

scrape_app = typer.Typer(
    help="Crawl and fetch articles for configured authors",
    invoke_without_command=True,
)


def _export_jsonl(db_path: Path, root: Path) -> int:
    out = root / "data/articles.jsonl"
    return export_articles_jsonl(db_path, out)


async def _discover_only(
    settings: ForensicsSettings, manifest_path: Path, *, force_refresh: bool
) -> int:
    n = await discover_authors(settings, force_refresh=force_refresh)
    if n:
        logger.info("discover: wrote %d author(s) to %s", n, manifest_path)
    else:
        logger.info(
            "discover: skipped (manifest exists). Use --force-refresh to overwrite. path=%s",
            manifest_path,
        )
    return 0


async def _metadata_only(
    db_path: Path, settings: ForensicsSettings, manifest_path: Path
) -> int:
    if not manifest_path.is_file():
        logger.error(
            "author manifest not found: %s (run `forensics scrape --discover` first)",
            manifest_path,
        )
        return 1
    inserted = await collect_article_metadata(db_path, settings)
    logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
    return 0


async def _fetch_only(db_path: Path, settings: ForensicsSettings, *, dry_run: bool) -> int:
    n = await fetch_articles(db_path, settings, dry_run=dry_run)
    suffix = " (dry-run)" if dry_run else ""
    logger.info(
        "fetch: %s %d article(s)%s",
        "would fetch" if dry_run else "processed",
        n,
        suffix,
    )
    return 0


async def _fetch_dedup_export(
    db_path: Path, root: Path, settings: ForensicsSettings, *, dry_run: bool
) -> int:
    n = await fetch_articles(db_path, settings, dry_run=dry_run)
    logger.info("fetch: processed %d article(s)%s", n, " (dry-run)" if dry_run else "")
    if not dry_run:
        dup_ids = deduplicate_articles(db_path)
        logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
        ex = _export_jsonl(db_path, root)
        logger.info("export: wrote %d article(s) to data/articles.jsonl", ex)
    return 0


async def _discover_and_metadata(
    db_path: Path,
    settings: ForensicsSettings,
    manifest_path: Path,
    *,
    force_refresh: bool,
) -> int:
    n_authors = await discover_authors(settings, force_refresh=force_refresh)
    if n_authors:
        logger.info("discover: wrote %d author(s) to %s", n_authors, manifest_path)
    else:
        logger.info("discover: skipped or unchanged (%s)", manifest_path)
    if not manifest_path.is_file():
        logger.error("author manifest missing after discover: %s", manifest_path)
        return 1
    inserted = await collect_article_metadata(db_path, settings)
    logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
    return 0


async def _full_pipeline(
    db_path: Path,
    root: Path,
    settings: ForensicsSettings,
    manifest_path: Path,
    *,
    force_refresh: bool,
) -> int:
    n_authors = await discover_authors(settings, force_refresh=force_refresh)
    if n_authors:
        logger.info("discover: wrote %d author(s) to %s", n_authors, manifest_path)
    else:
        logger.info("discover: skipped or unchanged (%s)", manifest_path)
    if not manifest_path.is_file():
        logger.error("author manifest missing after discover: %s", manifest_path)
        return 1
    inserted = await collect_article_metadata(db_path, settings)
    logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
    fetched = await fetch_articles(db_path, settings, dry_run=False)
    logger.info("fetch: processed %d article(s)", fetched)
    dup_ids = deduplicate_articles(db_path)
    logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
    ex = _export_jsonl(db_path, root)
    logger.info("export: wrote %d article(s) to data/articles.jsonl", ex)
    return 0


async def _dispatch(
    *,
    discover: bool,
    metadata: bool,
    fetch: bool,
    dedup: bool,
    archive: bool,
    dry_run: bool,
    force_refresh: bool,
) -> int:
    """Route flag combinations to the appropriate pipeline function.

    This is the testable core — integration tests call this directly.
    """
    settings = get_settings()
    root = get_project_root()
    manifest_path = root / "data/authors_manifest.jsonl"
    db_path = root / "data/articles.db"

    if dry_run and not fetch:
        logger.error("--dry-run is only valid with --fetch")
        return 1

    if discover or metadata or fetch or not (discover or metadata or fetch or dedup or archive):
        guard_placeholder_authors(settings)

    try:
        insert_analysis_run(
            db_path,
            config_hash=config_fingerprint(),
            description="forensics scrape",
        )
    except OSError as exc:
        logger.warning("Could not record analysis_runs row: %s", exc)

    d, m, f, dd, ar = discover, metadata, fetch, dedup, archive

    if ar and not d and not m and not f and not dd:
        n = archive_raw_year_dirs(root, db_path)
        logger.info("archive: compressed %d year directory(ies) under data/raw/", n)
        return 0
    if dd and not d and not m and not f and not ar:
        dup_ids = deduplicate_articles(db_path)
        logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
        return 0
    if f and not d and not m and not dd and not ar:
        return await _fetch_only(db_path, settings, dry_run=dry_run)
    if f and dd and not d and not m and not ar:
        return await _fetch_dedup_export(db_path, root, settings, dry_run=dry_run)
    if d and not m and not f and not dd and not ar:
        return await _discover_only(settings, manifest_path, force_refresh=force_refresh)
    if m and not d and not f and not dd and not ar:
        return await _metadata_only(db_path, settings, manifest_path)
    if d and m and not f and not dd and not ar:
        return await _discover_and_metadata(
            db_path, settings, manifest_path, force_refresh=force_refresh
        )
    if not (d or m or f or dd or ar):
        return await _full_pipeline(
            db_path, root, settings, manifest_path, force_refresh=force_refresh
        )

    logger.error(
        "unsupported flag combination for scrape "
        "(try individual --discover, --metadata, --fetch, --dedup, --archive)"
    )
    return 1


@scrape_app.callback()
def scrape(
    discover: Annotated[
        bool,
        typer.Option("--discover", help="Run WordPress author discovery only"),
    ] = False,
    metadata: Annotated[
        bool,
        typer.Option("--metadata", help="Collect article metadata only"),
    ] = False,
    fetch: Annotated[
        bool,
        typer.Option("--fetch", help="Fetch HTML and extract article text only"),
    ] = False,
    dedup: Annotated[
        bool,
        typer.Option("--dedup", help="Run near-duplicate detection only"),
    ] = False,
    archive: Annotated[
        bool,
        typer.Option("--archive", help="Compress data/raw/{year}/ to tar.gz"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="With --fetch: report count without HTTP"),
    ] = False,
    force_refresh: Annotated[
        bool,
        typer.Option("--force-refresh", help="With --discover: overwrite manifest"),
    ] = False,
) -> None:
    """Crawl and fetch articles for configured authors."""
    rc = asyncio.run(
        _dispatch(
            discover=discover,
            metadata=metadata,
            fetch=fetch,
            dedup=dedup,
            archive=archive,
            dry_run=dry_run,
            force_refresh=force_refresh,
        )
    )
    raise typer.Exit(code=rc)
