"""Add ``section`` to feature parquets (schema v2), with backup under ``_pre_phase15_backup/``.

Derives ``section`` from a ``url`` column, else from ``article_id`` + optional SQLite URL map,
else ``unknown``. Logs warnings when many rows resolve to ``unknown``.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import polars as pl

from forensics.storage.parquet import (
    _read_parquet_schema_version,
    _stamp_parquet_schema_version,
)
from forensics.utils.url import section_from_url

logger = logging.getLogger(__name__)

TARGET_SCHEMA_VERSION = 2
BACKUP_SUBDIR = "_pre_phase15_backup"


def _has_target_version(path: Path) -> bool:
    found = _read_parquet_schema_version(path)
    return found is not None and found >= TARGET_SCHEMA_VERSION


def _load_article_url_map(articles_db: Path | None) -> dict[str, str] | None:
    """Return ``{article_id: url}`` for the articles DB, or None if unavailable.

    Loaded once per ``migrate_all`` run so we don't reopen SQLite per-parquet
    or per-row. Returns ``None`` (rather than ``{}``) when the DB doesn't
    exist so callers can distinguish "no DB available" from "DB has no rows".

    Uses :func:`open_repository_connection` so this matches the rest of the
    codebase's WAL/busy-timeout connection policy (ADR-005).
    """
    if articles_db is None or not Path(articles_db).is_file():
        return None
    # Local import: ``repository`` imports this package at init.
    from forensics.storage.repository import open_repository_connection

    conn = open_repository_connection(articles_db)
    try:
        rows = conn.execute("SELECT id, url FROM articles").fetchall()
    finally:
        conn.close()
    return {str(rid): str(url) for rid, url in rows if rid is not None and url is not None}


def _derive_section_column(
    df: pl.DataFrame,
    *,
    parquet_path: Path,
    article_url_map: dict[str, str] | None,
) -> pl.DataFrame:
    """Add a ``section`` column to ``df`` using the best URL source available."""
    if "section" in df.columns:
        return df
    if "url" in df.columns:
        return df.with_columns(
            pl.col("url").map_elements(section_from_url, return_dtype=pl.Utf8).alias("section")
        )
    if "article_id" in df.columns and article_url_map:
        sections = [
            section_from_url(article_url_map.get(str(aid))) for aid in df["article_id"].to_list()
        ]
        unknown = sum(1 for s in sections if s == "unknown")
        if unknown:
            logger.warning(
                "feature parquet %s: %d/%d rows resolved to section='unknown' "
                "via articles.db JOIN (missing article_id or unparseable URL)",
                parquet_path,
                unknown,
                len(sections),
            )
        return df.with_columns(pl.Series("section", sections, dtype=pl.Utf8))
    logger.warning(
        "feature parquet %s: no url/article_id+articles.db available; "
        "filling section='unknown' for all %d rows",
        parquet_path,
        df.height,
    )
    return df.with_columns(pl.lit("unknown").alias("section"))


def migrate_feature_parquet(
    path: Path,
    *,
    backup_root: Path | None = None,
    dry_run: bool = False,
    articles_db: Path | None = None,
    article_url_map: dict[str, str] | None = None,
) -> bool:
    """Upgrade one feature parquet to schema v2 (in-place, with backup).

    Returns True if the file was migrated, False if it was already current.
    ``dry_run=True`` logs the would-be actions but touches nothing on disk.

    ``article_url_map`` is the preferred way to supply URLs for parquets that
    only carry ``article_id`` (the loader has already paid the SQLite cost).
    If absent but ``articles_db`` is provided, the map is loaded from that DB
    on demand (handy for one-off migrations of a single file).
    """
    if _has_target_version(path):
        logger.debug("feature parquet %s already at v%d", path, TARGET_SCHEMA_VERSION)
        return False
    backup_dir = backup_root if backup_root is not None else path.parent / BACKUP_SUBDIR
    backup_path = backup_dir / path.name
    if dry_run:
        logger.info(
            "DRY-RUN would migrate %s to v%d (backup -> %s)",
            path,
            TARGET_SCHEMA_VERSION,
            backup_path,
        )
        return True

    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    logger.info("backed up %s -> %s", path, backup_path)

    if article_url_map is None and articles_db is not None:
        article_url_map = _load_article_url_map(articles_db)

    df = pl.read_parquet(path)
    df = _derive_section_column(df, parquet_path=path, article_url_map=article_url_map)

    tmp = path.with_suffix(path.suffix + ".migrating")
    df.write_parquet(tmp)
    tmp.replace(path)
    _stamp_parquet_schema_version(path, TARGET_SCHEMA_VERSION)
    logger.info("migrated %s to v%d", path, TARGET_SCHEMA_VERSION)
    return True


def migrate_all(
    features_dir: Path,
    *,
    dry_run: bool = False,
    articles_db: Path | None = None,
) -> tuple[int, int]:
    """Walk ``features_dir`` upgrading every parquet. Returns ``(migrated, skipped)``.

    Skips the internal backup subdirectory so re-runs don't migrate-then-
    shadow the backup copy. The ``articles_db`` is opened once and the
    ``{id: url}`` map reused across every parquet in the run; the JOIN path
    handles legacy parquets that store only ``article_id`` (URLs live in the
    SQLite corpus DB rather than the parquet itself).
    """
    article_url_map = _load_article_url_map(articles_db)
    if articles_db is not None and article_url_map is None:
        logger.warning(
            "articles.db not found at %s; section JOIN unavailable, "
            "rows without a 'url' column will fall back to 'unknown'",
            articles_db,
        )
    migrated = 0
    skipped = 0
    for path in sorted(features_dir.glob("*.parquet")):
        if path.parent.name == BACKUP_SUBDIR:
            continue
        if migrate_feature_parquet(
            path,
            dry_run=dry_run,
            article_url_map=article_url_map,
        ):
            migrated += 1
        else:
            skipped += 1
    return migrated, skipped
