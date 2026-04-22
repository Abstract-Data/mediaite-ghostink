"""CLI entrypoints for forensic pipeline stages."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
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

    extract_p = subparsers.add_parser("extract", help="Run feature extraction pipeline")
    extract_p.add_argument(
        "--author",
        default=None,
        metavar="SLUG",
        help="Limit extraction to one configured author slug",
    )
    extract_p.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip sentence-transformer embeddings (faster for tests)",
    )
    analyze_p = subparsers.add_parser(
        "analyze", help="Run analysis (change-point, time-series, later drift/comparison)"
    )
    analyze_p.add_argument(
        "--changepoint",
        action="store_true",
        help="Run change-point detection only (PELT / BOCPD per feature)",
    )
    analyze_p.add_argument(
        "--timeseries",
        action="store_true",
        help="Run rolling statistics + STL-style decomposition only",
    )
    analyze_p.add_argument(
        "--drift",
        action="store_true",
        help="Run embedding drift analysis (Phase 6: centroids, velocities, UMAP)",
    )
    analyze_p.add_argument(
        "--ai-baseline",
        action="store_true",
        help="Generate or refresh synthetic AI baseline articles + embeddings (needs API key)",
    )
    analyze_p.add_argument(
        "--skip-generation",
        action="store_true",
        help="With --ai-baseline: re-embed existing JSON articles only (no LLM calls)",
    )
    analyze_p.add_argument(
        "--openai-key",
        default=None,
        metavar="KEY",
        help="OpenAI API key for --ai-baseline (else OPENAI_API_KEY)",
    )
    analyze_p.add_argument(
        "--llm-model",
        default="gpt-4o",
        metavar="MODEL",
        help="Chat model for --ai-baseline generation",
    )
    analyze_p.add_argument(
        "--author",
        default=None,
        metavar="SLUG",
        help="Limit analysis to one configured author slug",
    )
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


def _run_analyze(args: argparse.Namespace) -> int:
    from forensics.analysis.changepoint import run_changepoint_analysis
    from forensics.analysis.drift import run_ai_baseline_command, run_drift_analysis
    from forensics.analysis.timeseries import run_timeseries_analysis

    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"
    analysis_dir = root / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    want_cp = bool(getattr(args, "changepoint", False))
    want_ts = bool(getattr(args, "timeseries", False))
    want_drift = bool(getattr(args, "drift", False))
    want_ai = bool(getattr(args, "ai_baseline", False))
    explicit = want_cp or want_ts or want_drift or want_ai
    if explicit:
        do_changepoint = want_cp
        do_timeseries = want_ts
        do_drift = want_drift
    else:
        do_changepoint = True
        do_timeseries = True
        do_drift = False

    author_slug = getattr(args, "author", None)
    rid = insert_analysis_run(
        db_path,
        config_hash=_config_fingerprint(),
        description="forensics analyze",
    )
    meta = {
        "run_id": rid,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "config_hash": _config_fingerprint(),
        "changepoint": do_changepoint,
        "timeseries": do_timeseries,
        "drift": do_drift,
        "author": author_slug,
    }
    (analysis_dir / "run_metadata.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )

    if do_changepoint:
        run_changepoint_analysis(
            db_path,
            settings,
            project_root=root,
            author_slug=author_slug,
        )
    if do_timeseries:
        run_timeseries_analysis(
            db_path,
            settings,
            project_root=root,
            author_slug=author_slug,
        )
    if do_drift:
        run_drift_analysis(
            db_path,
            settings,
            project_root=root,
            author_slug=author_slug,
        )
    if want_ai:
        run_ai_baseline_command(
            db_path,
            settings,
            project_root=root,
            author_slug=author_slug,
            skip_generation=bool(getattr(args, "skip_generation", False)),
            openai_key=getattr(args, "openai_key", None),
            llm_model=str(getattr(args, "llm_model", "gpt-4o")),
        )
    logger.info(
        "analyze: completed (changepoint=%s, timeseries=%s, drift=%s, ai_baseline=%s, author=%s)",
        do_changepoint,
        do_timeseries,
        do_drift,
        want_ai,
        author_slug or "all",
    )
    return 0


def _run_extract(args: argparse.Namespace) -> int:
    from forensics.features.pipeline import extract_all_features

    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"
    author_slug = getattr(args, "author", None)
    skip_embeddings = bool(getattr(args, "skip_embeddings", False))
    n = extract_all_features(
        db_path,
        settings,
        author_slug=author_slug,
        skip_embeddings=skip_embeddings,
    )
    logger.info("extract: processed %d article(s)", n)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scrape":
        return asyncio.run(_async_scrape(args))

    if args.command == "extract":
        try:
            return _run_extract(args)
        except ValueError as exc:
            logger.error("%s", exc)
            return 1

    if args.command == "analyze":
        try:
            return _run_analyze(args)
        except ValueError as exc:
            logger.error("%s", exc)
            return 1

    logger.warning("Phase not yet implemented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
