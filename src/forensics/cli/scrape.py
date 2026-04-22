"""Scrape subcommand — WordPress discovery, metadata collection, HTML fetch."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from pathlib import Path
from typing import Annotated, assert_never

import typer

from forensics.cli._helpers import guard_placeholder_authors
from forensics.config import DEFAULT_DB_RELATIVE, get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.pipeline_context import PipelineContext
from forensics.scraper.crawler import collect_article_metadata, discover_authors
from forensics.scraper.dedup import deduplicate_articles
from forensics.scraper.fetcher import archive_raw_year_dirs, fetch_articles
from forensics.storage.export import export_articles_jsonl
from forensics.storage.repository import Repository, ensure_repo

logger = logging.getLogger(__name__)

scrape_app = typer.Typer(help="Crawl and fetch articles for configured authors")


class ScrapeMode(Enum):
    """Valid `forensics scrape` flag combinations routed by `dispatch_scrape`."""

    ARCHIVE_ONLY = auto()
    DEDUP_ONLY = auto()
    FETCH_ONLY = auto()
    FETCH_DEDUP_EXPORT = auto()
    DISCOVER_ONLY = auto()
    METADATA_ONLY = auto()
    DISCOVER_AND_METADATA = auto()
    FULL_PIPELINE = auto()


_ScrapeFlagKey = tuple[bool, bool, bool, bool, bool]

_FLAG_TO_SCRAPE_MODE: dict[_ScrapeFlagKey, ScrapeMode] = {
    (False, False, False, False, True): ScrapeMode.ARCHIVE_ONLY,
    (False, False, False, True, False): ScrapeMode.DEDUP_ONLY,
    (False, False, True, False, False): ScrapeMode.FETCH_ONLY,
    (False, False, True, True, False): ScrapeMode.FETCH_DEDUP_EXPORT,
    (True, False, False, False, False): ScrapeMode.DISCOVER_ONLY,
    (False, True, False, False, False): ScrapeMode.METADATA_ONLY,
    (True, True, False, False, False): ScrapeMode.DISCOVER_AND_METADATA,
    (False, False, False, False, False): ScrapeMode.FULL_PIPELINE,
}

if set(ScrapeMode) != set(_FLAG_TO_SCRAPE_MODE.values()):
    msg = "ScrapeMode members and _FLAG_TO_SCRAPE_MODE values must stay in sync"
    raise RuntimeError(msg)


def _resolve_scrape_mode(
    discover: bool,
    metadata: bool,
    fetch: bool,
    dedup: bool,
    archive: bool,
) -> ScrapeMode | None:
    return _FLAG_TO_SCRAPE_MODE.get((discover, metadata, fetch, dedup, archive))


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
    db_path: Path,
    settings: ForensicsSettings,
    manifest_path: Path,
    *,
    repo: Repository | None = None,
    all_authors: bool = False,
) -> int:
    if not manifest_path.is_file():
        logger.error(
            "author manifest not found: %s (run `forensics scrape --discover` first)",
            manifest_path,
        )
        return 1
    with ensure_repo(db_path, repo) as r:
        inserted = await collect_article_metadata(
            db_path, settings, repo=r, all_authors=all_authors
        )
    logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
    return 0


async def _fetch_only(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    dry_run: bool,
    repo: Repository | None = None,
) -> int:
    with ensure_repo(db_path, repo) as r:
        n = await fetch_articles(db_path, settings, dry_run=dry_run, repo=r)
    suffix = " (dry-run)" if dry_run else ""
    logger.info(
        "fetch: %s %d article(s)%s",
        "would fetch" if dry_run else "processed",
        n,
        suffix,
    )
    return 0


async def _fetch_dedup_export(
    db_path: Path,
    root: Path,
    settings: ForensicsSettings,
    *,
    dry_run: bool,
    repo: Repository | None = None,
) -> int:
    with ensure_repo(db_path, repo) as r:
        n = await fetch_articles(db_path, settings, dry_run=dry_run, repo=r)
    logger.info("fetch: processed %d article(s)%s", n, " (dry-run)" if dry_run else "")
    if not dry_run:
        dup_ids = deduplicate_articles(
            db_path, hamming_threshold=settings.scraping.simhash_threshold
        )
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
    all_authors: bool = False,
    repo: Repository | None = None,
) -> int:
    n_authors = await discover_authors(settings, force_refresh=force_refresh)
    if n_authors:
        logger.info("discover: wrote %d author(s) to %s", n_authors, manifest_path)
    else:
        logger.info("discover: skipped or unchanged (%s)", manifest_path)
    if not manifest_path.is_file():
        logger.error("author manifest missing after discover: %s", manifest_path)
        return 1
    with ensure_repo(db_path, repo) as r:
        inserted = await collect_article_metadata(
            db_path, settings, repo=r, all_authors=all_authors
        )
    logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
    return 0


async def _full_pipeline(
    db_path: Path,
    root: Path,
    settings: ForensicsSettings,
    manifest_path: Path,
    *,
    force_refresh: bool,
    all_authors: bool = False,
) -> int:
    with Repository(db_path) as repo:
        rc = await _discover_and_metadata(
            db_path,
            settings,
            manifest_path,
            force_refresh=force_refresh,
            all_authors=all_authors,
            repo=repo,
        )
        if rc != 0:
            return rc
        fetched = await fetch_articles(db_path, settings, dry_run=False, repo=repo)
    logger.info("fetch: processed %d article(s)", fetched)
    dup_ids = deduplicate_articles(db_path, hamming_threshold=settings.scraping.simhash_threshold)
    logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
    ex = _export_jsonl(db_path, root)
    logger.info("export: wrote %d article(s) to data/articles.jsonl", ex)
    return 0


async def _run_scrape_mode(
    mode: ScrapeMode,
    *,
    db_path: Path,
    root: Path,
    settings: ForensicsSettings,
    manifest_path: Path,
    dry_run: bool,
    force_refresh: bool,
    all_authors: bool,
) -> int:
    match mode:
        case ScrapeMode.ARCHIVE_ONLY:
            n = archive_raw_year_dirs(root, db_path)
            logger.info("archive: compressed %d year directory(ies) under data/raw/", n)
            return 0
        case ScrapeMode.DEDUP_ONLY:
            dup_ids = deduplicate_articles(
                db_path, hamming_threshold=settings.scraping.simhash_threshold
            )
            logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
            return 0
        case ScrapeMode.FETCH_ONLY:
            return await _fetch_only(db_path, settings, dry_run=dry_run)
        case ScrapeMode.FETCH_DEDUP_EXPORT:
            return await _fetch_dedup_export(db_path, root, settings, dry_run=dry_run)
        case ScrapeMode.DISCOVER_ONLY:
            return await _discover_only(settings, manifest_path, force_refresh=force_refresh)
        case ScrapeMode.METADATA_ONLY:
            return await _metadata_only(db_path, settings, manifest_path, all_authors=all_authors)
        case ScrapeMode.DISCOVER_AND_METADATA:
            return await _discover_and_metadata(
                db_path,
                settings,
                manifest_path,
                force_refresh=force_refresh,
                all_authors=all_authors,
            )
        case ScrapeMode.FULL_PIPELINE:
            return await _full_pipeline(
                db_path,
                root,
                settings,
                manifest_path,
                force_refresh=force_refresh,
                all_authors=all_authors,
            )
        case _ as unreachable:
            assert_never(unreachable)


async def dispatch_scrape(
    *,
    discover: bool,
    metadata: bool,
    fetch: bool,
    dedup: bool,
    archive: bool,
    dry_run: bool,
    force_refresh: bool,
    all_authors: bool = False,
) -> int:
    """Route flag combinations to the appropriate pipeline function.

    This is the testable core — all integration tests call this directly.
    """
    settings = get_settings()
    root = get_project_root()
    manifest_path = root / "data/authors_manifest.jsonl"
    db_path = root / DEFAULT_DB_RELATIVE

    if dry_run and not fetch:
        logger.error("--dry-run is only valid with --fetch")
        return 1

    scrape_like = discover or metadata or fetch
    default_full = not (scrape_like or dedup or archive)
    if not all_authors and (scrape_like or default_full):
        guard_placeholder_authors(settings)

    PipelineContext.resolve().record_audit(
        "forensics scrape",
        optional=True,
        log=logger,
    )

    mode = _resolve_scrape_mode(discover, metadata, fetch, dedup, archive)
    if mode is None:
        logger.error(
            "unsupported flag combination for scrape "
            "(try individual --discover, --metadata, --fetch, --dedup, --archive)"
        )
        return 1
    return await _run_scrape_mode(
        mode,
        db_path=db_path,
        root=root,
        settings=settings,
        manifest_path=manifest_path,
        dry_run=dry_run,
        force_refresh=force_refresh,
        all_authors=all_authors,
    )


@scrape_app.callback(invoke_without_command=True)
def scrape(
    discover: Annotated[
        bool, typer.Option("--discover", help="Run WordPress author discovery only")
    ] = False,
    metadata: Annotated[
        bool, typer.Option("--metadata", help="Collect article metadata only")
    ] = False,
    fetch: Annotated[
        bool, typer.Option("--fetch", help="Fetch HTML and extract article text only")
    ] = False,
    dedup: Annotated[
        bool, typer.Option("--dedup", help="Run near-duplicate detection only")
    ] = False,
    archive: Annotated[
        bool, typer.Option("--archive", help="Compress data/raw/{year}/ to tar.gz")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="With --fetch: report count without HTTP")
    ] = False,
    force_refresh: Annotated[
        bool,
        typer.Option("--force-refresh", help="With --discover: overwrite manifest"),
    ] = False,
    all_authors: Annotated[
        bool,
        typer.Option(
            "--all-authors",
            help="Collect metadata for every author in the manifest (ignore config.toml list)",
        ),
    ] = False,
) -> None:
    """Crawl and fetch articles for configured authors."""
    rc = asyncio.run(
        dispatch_scrape(
            discover=discover,
            metadata=metadata,
            fetch=fetch,
            dedup=dedup,
            archive=archive,
            dry_run=dry_run,
            force_refresh=force_refresh,
            all_authors=all_authors,
        )
    )
    raise typer.Exit(code=rc)
