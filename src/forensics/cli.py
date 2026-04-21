"""CLI entrypoints for forensic pipeline stages."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from forensics.config import get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.scraper.crawler import collect_article_metadata, discover_authors
from forensics.scraper.dedup import deduplicate_articles
from forensics.scraper.fetcher import archive_raw_year_dirs, fetch_articles
from forensics.storage.export import export_articles_jsonl


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
    print(f"archive: compressed {n} year directory(ies) under data/raw/")
    return 0


async def _scrape_dedup_only(db_path: Path) -> int:
    dup_ids = deduplicate_articles(db_path)
    print(f"dedup: marked {len(dup_ids)} article(s) as near-duplicates")
    return 0


async def _scrape_fetch_only(
    db_path: Path, settings: ForensicsSettings, *, dry_run: bool
) -> int:
    n = await fetch_articles(db_path, settings, dry_run=dry_run)
    suffix = " (dry-run)" if dry_run else ""
    print(f"fetch: {'would fetch' if dry_run else 'processed'} {n} article(s){suffix}")
    return 0


async def _scrape_fetch_dedup_export(
    db_path: Path, root: Path, settings: ForensicsSettings, *, dry_run: bool
) -> int:
    n = await fetch_articles(db_path, settings, dry_run=dry_run)
    print(f"fetch: processed {n} article(s)" + (" (dry-run)" if dry_run else ""))
    if not dry_run:
        dup_ids = deduplicate_articles(db_path)
        print(f"dedup: marked {len(dup_ids)} article(s) as near-duplicates")
        ex = _export_jsonl(db_path, root)
        print(f"export: wrote {ex} article(s) to data/articles.jsonl")
    return 0


async def _scrape_discover_only(
    settings: ForensicsSettings, manifest_path: Path, *, force_refresh: bool
) -> int:
    n = await discover_authors(settings, force_refresh=force_refresh)
    if n:
        print(f"discover: wrote {n} author(s) to {manifest_path}")
    else:
        print(
            f"discover: skipped (manifest exists). "
            f"Use --force-refresh to overwrite. path={manifest_path}"
        )
    return 0


async def _scrape_metadata_only(
    db_path: Path, settings: ForensicsSettings, manifest_path: Path
) -> int:
    if not manifest_path.is_file():
        print(
            f"error: author manifest not found: {manifest_path} "
            "(run `forensics scrape --discover` first)",
            file=sys.stderr,
        )
        return 1
    inserted = await collect_article_metadata(db_path, settings)
    print(f"metadata: inserted {inserted} new article row(s) into {db_path}")
    return 0


async def _scrape_discover_and_metadata(
    db_path: Path, settings: ForensicsSettings, manifest_path: Path, *, force_refresh: bool
) -> int:
    n_authors = await discover_authors(settings, force_refresh=force_refresh)
    if n_authors:
        print(f"discover: wrote {n_authors} author(s) to {manifest_path}")
    else:
        print(f"discover: skipped or unchanged ({manifest_path})")
    if not manifest_path.is_file():
        print(
            f"error: author manifest missing after discover: {manifest_path}",
            file=sys.stderr,
        )
        return 1
    inserted = await collect_article_metadata(db_path, settings)
    print(f"metadata: inserted {inserted} new article row(s) into {db_path}")
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
        print(f"discover: wrote {n_authors} author(s) to {manifest_path}")
    else:
        print(f"discover: skipped or unchanged ({manifest_path})")
    if not manifest_path.is_file():
        print(
            f"error: author manifest missing after discover: {manifest_path}",
            file=sys.stderr,
        )
        return 1
    inserted = await collect_article_metadata(db_path, settings)
    print(f"metadata: inserted {inserted} new article row(s) into {db_path}")
    fetched = await fetch_articles(db_path, settings, dry_run=False)
    print(f"fetch: processed {fetched} article(s)")
    dup_ids = deduplicate_articles(db_path)
    print(f"dedup: marked {len(dup_ids)} article(s) as near-duplicates")
    ex = _export_jsonl(db_path, root)
    print(f"export: wrote {ex} article(s) to data/articles.jsonl")
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
        print("error: --dry-run is only valid with --fetch", file=sys.stderr)
        return 1

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

    print(
        "error: unsupported flag combination for scrape "
        "(try individual --discover, --metadata, --fetch, --dedup, --archive)",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scrape":
        return asyncio.run(_async_scrape(args))

    print("Phase not yet implemented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
