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
from forensics.storage.repository import Repository, insert_analysis_run

logger = logging.getLogger(__name__)

scrape_app = typer.Typer(help="Crawl and fetch articles for configured authors")


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
    if repo is not None:
        inserted = await collect_article_metadata(
            db_path, settings, repo=repo, all_authors=all_authors
        )
    else:
        with Repository(db_path) as r:
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
    if repo is not None:
        n = await fetch_articles(db_path, settings, dry_run=dry_run, repo=repo)
    else:
        with Repository(db_path) as r:
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
    if repo is not None:
        n = await fetch_articles(db_path, settings, dry_run=dry_run, repo=repo)
    else:
        with Repository(db_path) as r:
            n = await fetch_articles(db_path, settings, dry_run=dry_run, repo=r)
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
    all_authors: bool = False,
) -> int:
    n_authors = await discover_authors(settings, force_refresh=force_refresh)
    if n_authors:
        logger.info("discover: wrote %d author(s) to %s", n_authors, manifest_path)
    else:
        logger.info("discover: skipped or unchanged (%s)", manifest_path)
    if not manifest_path.is_file():
        logger.error("author manifest missing after discover: %s", manifest_path)
        return 1
    with Repository(db_path) as repo:
        inserted = await collect_article_metadata(
            db_path, settings, repo=repo, all_authors=all_authors
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
    n_authors = await discover_authors(settings, force_refresh=force_refresh)
    if n_authors:
        logger.info("discover: wrote %d author(s) to %s", n_authors, manifest_path)
    else:
        logger.info("discover: skipped or unchanged (%s)", manifest_path)
    if not manifest_path.is_file():
        logger.error("author manifest missing after discover: %s", manifest_path)
        return 1
    with Repository(db_path) as repo:
        inserted = await collect_article_metadata(
            db_path, settings, repo=repo, all_authors=all_authors
        )
        logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
        fetched = await fetch_articles(db_path, settings, dry_run=False, repo=repo)
    logger.info("fetch: processed %d article(s)", fetched)
    dup_ids = deduplicate_articles(db_path)
    logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
    ex = _export_jsonl(db_path, root)
    logger.info("export: wrote %d article(s) to data/articles.jsonl", ex)
    return 0


_ScrapeFlagKey = tuple[bool, bool, bool, bool, bool]


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
    db_path = root / "data/articles.db"

    if dry_run and not fetch:
        logger.error("--dry-run is only valid with --fetch")
        return 1

    scrape_like = discover or metadata or fetch
    default_full = not (scrape_like or dedup or archive)
    if not all_authors and (scrape_like or default_full):
        guard_placeholder_authors(settings)

    try:
        insert_analysis_run(
            db_path,
            config_hash=config_fingerprint(),
            description="forensics scrape",
        )
    except OSError as exc:
        logger.warning("Could not record analysis_runs row: %s", exc)

    key: _ScrapeFlagKey = (discover, metadata, fetch, dedup, archive)

    async def _archive_branch() -> int:
        n = archive_raw_year_dirs(root, db_path)
        logger.info("archive: compressed %d year directory(ies) under data/raw/", n)
        return 0

    async def _dedup_branch() -> int:
        dup_ids = deduplicate_articles(db_path)
        logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
        return 0

    routes: dict[_ScrapeFlagKey, object] = {
        (False, False, False, False, True): _archive_branch,
        (False, False, False, True, False): _dedup_branch,
        (False, False, True, False, False): lambda: _fetch_only(db_path, settings, dry_run=dry_run),
        (False, False, True, True, False): lambda: _fetch_dedup_export(
            db_path, root, settings, dry_run=dry_run
        ),
        (True, False, False, False, False): lambda: _discover_only(
            settings, manifest_path, force_refresh=force_refresh
        ),
        (False, True, False, False, False): lambda: _metadata_only(
            db_path, settings, manifest_path, all_authors=all_authors
        ),
        (True, True, False, False, False): lambda: _discover_and_metadata(
            db_path,
            settings,
            manifest_path,
            force_refresh=force_refresh,
            all_authors=all_authors,
        ),
        (False, False, False, False, False): lambda: _full_pipeline(
            db_path,
            root,
            settings,
            manifest_path,
            force_refresh=force_refresh,
            all_authors=all_authors,
        ),
    }

    handler = routes.get(key)
    if handler is None:
        logger.error(
            "unsupported flag combination for scrape "
            "(try individual --discover, --metadata, --fetch, --dedup, --archive)"
        )
        return 1
    maybe = handler()
    return await maybe if asyncio.iscoroutine(maybe) else int(maybe)


async def _dispatch(
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
    """Deprecated alias for :func:`dispatch_scrape` (tests and older imports)."""
    return await dispatch_scrape(
        discover=discover,
        metadata=metadata,
        fetch=fetch,
        dedup=dedup,
        archive=archive,
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
