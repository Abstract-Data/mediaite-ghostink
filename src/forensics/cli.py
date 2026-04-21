"""CLI entrypoints for forensic pipeline stages."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
from pathlib import Path

from forensics.config import get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.scraper.crawler import collect_article_metadata, discover_authors
from forensics.scraper.dedup import deduplicate_articles
from forensics.scraper.fetcher import archive_raw_year_dirs, fetch_articles
from forensics.storage.export import export_articles_jsonl
from forensics.storage.repository import insert_analysis_run

logger = logging.getLogger(__name__)

_PLACEHOLDER_SLUGS = frozenset({"placeholder-target", "placeholder-control"})


def _config_fingerprint() -> str:
    """Short hash of the active TOML config file for ``analysis_runs``."""
    raw = os.environ.get("FORENSICS_CONFIG_FILE", "").strip()
    candidates = [Path(raw).expanduser()] if raw else []
    candidates.append(get_project_root() / "config.toml")
    for path in candidates:
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return digest[:48]
    return "no_config_file"


def _guard_placeholder_authors(settings: ForensicsSettings) -> None:
    """Reject template slugs before any live scrape stage (P3-SEC-3)."""
    if any(a.slug in _PLACEHOLDER_SLUGS for a in settings.authors):
        msg = (
            "config.toml still uses template authors (slug placeholder-target / "
            "placeholder-control). Replace them with real author rows before scraping."
        )
        raise ValueError(msg)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forensics",
        description="AI Writing Forensics Pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape = subparsers.add_parser(
        "scrape",
        help="Crawl and fetch articles for configured authors",
    )
    scrape.add_argument(
        "--discover",
        action="store_true",
        help="Run WordPress author discovery only (writes authors_manifest.jsonl)",
    )
    scrape.add_argument(
        "--metadata",
        action="store_true",
        help="Collect article metadata only (requires existing authors manifest)",
    )
    scrape.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch HTML and extract article text only (Phase 3)",
    )
    scrape.add_argument(
        "--dedup",
        action="store_true",
        help="Run near-duplicate detection (simhash) only",
    )
    scrape.add_argument(
        "--archive",
        action="store_true",
        help="Compress data/raw/{year}/ folders to tar.gz and update DB paths",
    )
    scrape.add_argument(
        "--dry-run",
        action="store_true",
        help="With --fetch: report how many URLs would be fetched without HTTP",
    )
    scrape.add_argument(
        "--force-refresh",
        action="store_true",
        help="With discovery: overwrite authors_manifest.jsonl if it exists",
    )

    subparsers.add_parser("extract", help="Run feature extraction pipeline")
    subparsers.add_parser("analyze", help="Run analysis (change-point, drift, comparison)")
    subparsers.add_parser("report", help="Generate notebook outputs")
    subparsers.add_parser("all", help="Full pipeline end-to-end")
    return parser


def _export_jsonl(db_path: Path, root: Path) -> int:
    out = root / "data/articles.jsonl"
    n = export_articles_jsonl(db_path, out)
    return n


async def _scrape_archive_only(root: Path, db_path: Path) -> int:
    n = archive_raw_year_dirs(root, db_path)
    logger.info("archive: compressed %d year directory(ies) under data/raw/", n)
    return 0


async def _scrape_dedup_only(db_path: Path) -> int:
    dup_ids = deduplicate_articles(db_path)
    logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
    return 0


async def _scrape_fetch_only(db_path: Path, settings: ForensicsSettings, *, dry_run: bool) -> int:
    n = await fetch_articles(db_path, settings, dry_run=dry_run)
    suffix = " (dry-run)" if dry_run else ""
    logger.info(
        "fetch: %s %d article(s)%s",
        "would fetch" if dry_run else "processed",
        n,
        suffix,
    )
    return 0


async def _scrape_fetch_dedup_export(
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


async def _scrape_discover_only(
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


async def _scrape_metadata_only(
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


async def _scrape_discover_and_metadata(
    db_path: Path, settings: ForensicsSettings, manifest_path: Path, *, force_refresh: bool
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


async def _scrape_full_pipeline(
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


async def _async_scrape(args: argparse.Namespace) -> int:
    settings = get_settings()
    root = get_project_root()
    manifest_path = root / "data/authors_manifest.jsonl"
    db_path = root / "data/articles.db"

    d = bool(args.discover)
    m = bool(args.metadata)
    f = bool(args.fetch)
    ded = bool(args.dedup)
    arch = bool(args.archive)
    dry = bool(args.dry_run)
    force_refresh = bool(args.force_refresh)

    if dry and not f:
        logger.error("--dry-run is only valid with --fetch")
        return 1

    try:
        if d or m or f or not (d or m or f or ded or arch):
            _guard_placeholder_authors(settings)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    try:
        insert_analysis_run(
            db_path,
            config_hash=_config_fingerprint(),
            description="forensics scrape",
        )
    except OSError as exc:
        logger.warning("Could not record analysis_runs row: %s", exc)

    if arch and not d and not m and not f and not ded:
        return await _scrape_archive_only(root, db_path)
    if ded and not d and not m and not f and not arch:
        return await _scrape_dedup_only(db_path)
    if f and not d and not m and not ded and not arch:
        return await _scrape_fetch_only(db_path, settings, dry_run=dry)
    if f and ded and not d and not m and not arch:
        return await _scrape_fetch_dedup_export(db_path, root, settings, dry_run=dry)
    if d and not m and not f and not ded and not arch:
        return await _scrape_discover_only(settings, manifest_path, force_refresh=force_refresh)
    if m and not d and not f and not ded and not arch:
        return await _scrape_metadata_only(db_path, settings, manifest_path)
    if d and m and not f and not ded and not arch:
        return await _scrape_discover_and_metadata(
            db_path, settings, manifest_path, force_refresh=force_refresh
        )
    if not (d or m or f or ded or arch):
        return await _scrape_full_pipeline(
            db_path, root, settings, manifest_path, force_refresh=force_refresh
        )

    logger.error(
        "unsupported flag combination for scrape "
        "(try individual --discover, --metadata, --fetch, --dedup, --archive)"
    )
    return 1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scrape":
        return asyncio.run(_async_scrape(args))

    logger.warning("Phase not yet implemented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
