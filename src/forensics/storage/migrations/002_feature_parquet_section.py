"""Phase 15 Step 0.3 migration: add ``section`` column to feature parquets.

Reads an existing feature parquet, derives ``section`` from each row's article
URL via :func:`forensics.utils.url.section_from_url`, writes a new parquet
stamped with schema version 2, and atomically swaps the file in place —
preserving a backup under ``data/features/_pre_phase15_backup/``.
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


def migrate_feature_parquet(
    path: Path,
    *,
    backup_root: Path | None = None,
    dry_run: bool = False,
) -> bool:
    """Upgrade one feature parquet to schema v2 (in-place, with backup).

    Returns True if the file was migrated, False if it was already current.
    ``dry_run=True`` logs the would-be actions but touches nothing on disk.
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

    df = pl.read_parquet(path)
    if "section" not in df.columns:
        if "url" in df.columns:
            df = df.with_columns(
                pl.col("url").map_elements(section_from_url, return_dtype=pl.Utf8).alias("section")
            )
        else:
            # No URL column to derive from — fall back to ``unknown``.
            df = df.with_columns(pl.lit("unknown").alias("section"))

    tmp = path.with_suffix(path.suffix + ".migrating")
    df.write_parquet(tmp)
    tmp.replace(path)
    _stamp_parquet_schema_version(path, TARGET_SCHEMA_VERSION)
    logger.info("migrated %s to v%d", path, TARGET_SCHEMA_VERSION)
    return True


def migrate_all(features_dir: Path, *, dry_run: bool = False) -> tuple[int, int]:
    """Walk ``features_dir`` upgrading every parquet. Returns ``(migrated, skipped)``.

    Skips the internal backup subdirectory so re-runs don't migrate-then-
    shadow the backup copy.
    """
    migrated = 0
    skipped = 0
    for path in sorted(features_dir.glob("*.parquet")):
        if path.parent.name == BACKUP_SUBDIR:
            continue
        if migrate_feature_parquet(path, dry_run=dry_run):
            migrated += 1
        else:
            skipped += 1
    return migrated, skipped
