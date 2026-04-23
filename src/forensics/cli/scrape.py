"""Scrape subcommand — WordPress discovery, metadata collection, HTML fetch."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import Enum, auto
from pathlib import Path
from typing import Annotated, assert_never

import typer

from forensics.cli._helpers import guard_placeholder_authors
from forensics.cli.state import get_cli_state
from forensics.config import DEFAULT_DB_RELATIVE, get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.pipeline_context import PipelineContext
from forensics.progress import PipelineObserver, PipelineStage, managed_rich_observer
from forensics.scraper.crawler import (
    collect_article_metadata,
    discover_authors,
    resolve_posts_year_window,
)
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


async def _with_pipeline_stage(
    observer: PipelineObserver | None,
    stage: PipelineStage,
    work: Callable[[], Awaitable[int]],
) -> int:
    if observer is not None:
        observer.pipeline_stage_start(stage)
    try:
        return await work()
    finally:
        if observer is not None:
            observer.pipeline_stage_end(stage)


def _export_jsonl(db_path: Path, root: Path) -> int:
    out = root / "data/articles.jsonl"
    return export_articles_jsonl(db_path, out)


async def _discover_only(
    settings: ForensicsSettings,
    manifest_path: Path,
    *,
    force_refresh: bool,
    post_year_min: int | None = None,
    post_year_max: int | None = None,
    observer: PipelineObserver | None = None,
) -> int:
    async def _work() -> int:
        n = await discover_authors(
            settings,
            force_refresh=force_refresh,
            post_year_min=post_year_min,
            post_year_max=post_year_max,
        )
        if n:
            logger.info("discover: wrote %d author(s) to %s", n, manifest_path)
        else:
            logger.info(
                "discover: skipped (manifest exists). Use --force-refresh to overwrite. path=%s",
                manifest_path,
            )
        return 0

    return await _with_pipeline_stage(observer, PipelineStage.DISCOVER, _work)


async def _metadata_only(
    db_path: Path,
    settings: ForensicsSettings,
    manifest_path: Path,
    *,
    repo: Repository | None = None,
    all_authors: bool = False,
    post_year_min: int | None = None,
    post_year_max: int | None = None,
    observer: PipelineObserver | None = None,
) -> int:
    if not manifest_path.is_file():
        logger.error(
            "author manifest not found: %s (run `forensics scrape --discover` first)",
            manifest_path,
        )
        return 1

    async def _work() -> int:
        with ensure_repo(db_path, repo) as r:
            inserted = await collect_article_metadata(
                db_path,
                settings,
                repo=r,
                all_authors=all_authors,
                post_year_min=post_year_min,
                post_year_max=post_year_max,
                observer=observer,
            )
        logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
        return 0

    return await _with_pipeline_stage(observer, PipelineStage.METADATA, _work)


async def _fetch_only(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    dry_run: bool,
    repo: Repository | None = None,
    observer: PipelineObserver | None = None,
) -> int:
    async def _work() -> int:
        with ensure_repo(db_path, repo) as r:
            n = await fetch_articles(
                db_path, settings, dry_run=dry_run, repo=r, observer=observer
            )
        suffix = " (dry-run)" if dry_run else ""
        logger.info(
            "fetch: %s %d article(s)%s",
            "would fetch" if dry_run else "processed",
            n,
            suffix,
        )
        return 0

    return await _with_pipeline_stage(observer, PipelineStage.FETCH, _work)


async def _fetch_dedup_export(
    db_path: Path,
    root: Path,
    settings: ForensicsSettings,
    *,
    dry_run: bool,
    repo: Repository | None = None,
    observer: PipelineObserver | None = None,
) -> int:
    async def _fetch_work() -> int:
        with ensure_repo(db_path, repo) as r:
            n = await fetch_articles(
                db_path, settings, dry_run=dry_run, repo=r, observer=observer
            )
        logger.info("fetch: processed %d article(s)%s", n, " (dry-run)" if dry_run else "")
        return 0

    await _with_pipeline_stage(observer, PipelineStage.FETCH, _fetch_work)
    if dry_run:
        return 0

    async def _dedup_work() -> int:
        dup_ids = deduplicate_articles(
            db_path, hamming_threshold=settings.scraping.simhash_threshold
        )
        logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
        return 0

    await _with_pipeline_stage(observer, PipelineStage.DEDUP, _dedup_work)

    async def _export_work() -> int:
        ex = _export_jsonl(db_path, root)
        logger.info("export: wrote %d article(s) to data/articles.jsonl", ex)
        return 0

    await _with_pipeline_stage(observer, PipelineStage.EXPORT, _export_work)
    return 0


async def _discover_and_metadata(
    db_path: Path,
    settings: ForensicsSettings,
    manifest_path: Path,
    *,
    force_refresh: bool,
    all_authors: bool = False,
    repo: Repository | None = None,
    post_year_min: int | None = None,
    post_year_max: int | None = None,
    observer: PipelineObserver | None = None,
) -> int:
    async def _discover_work() -> int:
        n_authors = await discover_authors(
            settings,
            force_refresh=force_refresh,
            post_year_min=post_year_min,
            post_year_max=post_year_max,
        )
        if n_authors:
            logger.info("discover: wrote %d author(s) to %s", n_authors, manifest_path)
        else:
            logger.info("discover: skipped or unchanged (%s)", manifest_path)
        return 0

    await _with_pipeline_stage(observer, PipelineStage.DISCOVER, _discover_work)
    if not manifest_path.is_file():
        logger.error("author manifest missing after discover: %s", manifest_path)
        return 1

    async def _metadata_work() -> int:
        with ensure_repo(db_path, repo) as r:
            inserted = await collect_article_metadata(
                db_path,
                settings,
                repo=r,
                all_authors=all_authors,
                post_year_min=post_year_min,
                post_year_max=post_year_max,
                observer=observer,
            )
        logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
        return 0

    return await _with_pipeline_stage(observer, PipelineStage.METADATA, _metadata_work)


async def _full_pipeline(
    db_path: Path,
    root: Path,
    settings: ForensicsSettings,
    manifest_path: Path,
    *,
    force_refresh: bool,
    all_authors: bool = False,
    post_year_min: int | None = None,
    post_year_max: int | None = None,
    observer: PipelineObserver | None = None,
) -> int:
    with Repository(db_path) as repo:
        rc = await _discover_and_metadata(
            db_path,
            settings,
            manifest_path,
            force_refresh=force_refresh,
            all_authors=all_authors,
            repo=repo,
            post_year_min=post_year_min,
            post_year_max=post_year_max,
            observer=observer,
        )
        if rc != 0:
            return rc

        async def _fetch_work() -> int:
            fetched = await fetch_articles(
                db_path, settings, dry_run=False, repo=repo, observer=observer
            )
            logger.info("fetch: processed %d article(s)", fetched)
            return 0

        await _with_pipeline_stage(observer, PipelineStage.FETCH, _fetch_work)

    async def _dedup_work() -> int:
        dup_ids = deduplicate_articles(
            db_path, hamming_threshold=settings.scraping.simhash_threshold
        )
        logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
        return 0

    await _with_pipeline_stage(observer, PipelineStage.DEDUP, _dedup_work)

    async def _export_work() -> int:
        ex = _export_jsonl(db_path, root)
        logger.info("export: wrote %d article(s) to data/articles.jsonl", ex)
        return 0

    await _with_pipeline_stage(observer, PipelineStage.EXPORT, _export_work)
    return 0


async def _archive_only(
    root: Path, db_path: Path, *, observer: PipelineObserver | None = None
) -> int:
    async def _work() -> int:
        n = archive_raw_year_dirs(root, db_path)
        logger.info("archive: compressed %d year directory(ies) under data/raw/", n)
        return 0

    return await _with_pipeline_stage(observer, PipelineStage.ARCHIVE, _work)


async def _dedup_only(
    db_path: Path, settings: ForensicsSettings, *, observer: PipelineObserver | None = None
) -> int:
    async def _work() -> int:
        dup_ids = deduplicate_articles(
            db_path, hamming_threshold=settings.scraping.simhash_threshold
        )
        logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
        return 0

    return await _with_pipeline_stage(observer, PipelineStage.DEDUP, _work)


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
    post_year_min: int | None,
    post_year_max: int | None,
    observer: PipelineObserver | None,
) -> int:
    """Dispatch ``mode`` to its handler (RF-PATTERN-001).

    Using a dict instead of a ``match`` keeps each branch type-checked
    independently and makes it easier to swap in alternative handlers in tests.
    ``assert_never`` still guards against new enum members landing without a
    corresponding dispatch entry.
    """
    py_min, py_max = post_year_min, post_year_max
    obs = observer
    dispatch: dict[ScrapeMode, Callable[[], Awaitable[int]]] = {
        ScrapeMode.ARCHIVE_ONLY: lambda: _archive_only(root, db_path, observer=obs),
        ScrapeMode.DEDUP_ONLY: lambda: _dedup_only(db_path, settings, observer=obs),
        ScrapeMode.FETCH_ONLY: lambda: _fetch_only(
            db_path, settings, dry_run=dry_run, observer=obs
        ),
        ScrapeMode.FETCH_DEDUP_EXPORT: lambda: _fetch_dedup_export(
            db_path, root, settings, dry_run=dry_run, observer=obs
        ),
        ScrapeMode.DISCOVER_ONLY: lambda: _discover_only(
            settings,
            manifest_path,
            force_refresh=force_refresh,
            post_year_min=py_min,
            post_year_max=py_max,
            observer=obs,
        ),
        ScrapeMode.METADATA_ONLY: lambda: _metadata_only(
            db_path,
            settings,
            manifest_path,
            all_authors=all_authors,
            post_year_min=py_min,
            post_year_max=py_max,
            observer=obs,
        ),
        ScrapeMode.DISCOVER_AND_METADATA: lambda: _discover_and_metadata(
            db_path,
            settings,
            manifest_path,
            force_refresh=force_refresh,
            all_authors=all_authors,
            post_year_min=py_min,
            post_year_max=py_max,
            observer=obs,
        ),
        ScrapeMode.FULL_PIPELINE: lambda: _full_pipeline(
            db_path,
            root,
            settings,
            manifest_path,
            force_refresh=force_refresh,
            all_authors=all_authors,
            post_year_min=py_min,
            post_year_max=py_max,
            observer=obs,
        ),
    }
    handler = dispatch.get(mode)
    if handler is None:
        assert_never(mode)
    return await handler()


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
    post_year_min: int | None = None,
    post_year_max: int | None = None,
    observer: PipelineObserver | None = None,
) -> int:
    """Route flag combinations to the appropriate pipeline function.

    This is the testable core — all integration tests call this directly.
    """
    settings = get_settings()
    root = get_project_root()
    manifest_path = root / "data/authors_manifest.jsonl"
    db_path = root / DEFAULT_DB_RELATIVE

    try:
        year_win = resolve_posts_year_window(
            settings.scraping,
            override_min=post_year_min,
            override_max=post_year_max,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    if dry_run and not fetch:
        logger.error("--dry-run is only valid with --fetch")
        return 1

    scrape_like = discover or metadata or fetch
    default_full = not (scrape_like or dedup or archive)
    if not all_authors and (scrape_like or default_full):
        guard_placeholder_authors(settings)

    audit_desc = "forensics scrape"
    if year_win is not None:
        audit_desc += f" post_years={year_win[0]}-{year_win[1]}"
    PipelineContext.resolve(root=root).record_audit(
        audit_desc,
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
        post_year_min=post_year_min,
        post_year_max=post_year_max,
        observer=observer,
    )


@scrape_app.callback(invoke_without_command=True)
def scrape(
    ctx: typer.Context,
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
    post_year_min: Annotated[
        int | None,
        typer.Option(
            "--post-year-min",
            help=(
                "Inclusive calendar year for WordPress posts (with --post-year-max); "
                "overrides config when set"
            ),
        ),
    ] = None,
    post_year_max: Annotated[
        int | None,
        typer.Option(
            "--post-year-max",
            help=(
                "Inclusive calendar year for WordPress posts (with --post-year-min); "
                "overrides config when set"
            ),
        ),
    ] = None,
) -> None:
    """Crawl and fetch articles for configured authors."""
    show = get_cli_state(ctx).show_progress
    with managed_rich_observer(show) as observer:
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
                post_year_min=post_year_min,
                post_year_max=post_year_max,
                observer=observer,
            )
        )
    raise typer.Exit(code=rc)
