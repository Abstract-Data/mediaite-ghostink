"""Walk ``data/features/`` and upgrade every feature parquet to schema v2.

Phase 15 Step 0.3. Intended to be run once after merging Phase-15 Unit 1.
Idempotent: re-runs skip files that are already stamped with the target
schema version. See ``docs/settings_phase15.md`` for the rationale.

Usage::

    uv run python scripts/migrate_feature_parquets.py             # migrate in place
    uv run python scripts/migrate_feature_parquets.py --dry-run   # preview only
    uv run python scripts/migrate_feature_parquets.py --features-dir path/to/features

Backups land under ``<features-dir>/_pre_phase15_backup/``. Rollback is a
``mv`` of the backup copy back into place.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
from pathlib import Path

from forensics.config import DEFAULT_DB_RELATIVE, get_project_root

# Module names starting with a digit are not importable via ``import``; use
# ``importlib`` to load the numbered migration module.
_mig = importlib.import_module("forensics.storage.migrations.002_feature_parquet_section")


def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features-dir",
        type=Path,
        default=None,
        help="Path to the features directory (default: <project_root>/data/features).",
    )
    parser.add_argument(
        "--articles-db",
        type=Path,
        default=None,
        help=(
            "Path to the SQLite DB used for the article_id -> url JOIN "
            f"(default: <project_root>/{DEFAULT_DB_RELATIVE.as_posix()})."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log the would-be actions without writing backups or rewriting parquets.",
    )
    args = parser.parse_args()

    project_root = get_project_root()
    root = args.features_dir or (project_root / "data" / "features")
    if not root.is_dir():
        logging.warning("features directory not found: %s", root)
        return 0
    db = args.articles_db or (project_root / DEFAULT_DB_RELATIVE)
    migrated, skipped = _mig.migrate_all(root, dry_run=args.dry_run, articles_db=db)
    logging.info(
        "migrate_feature_parquets: migrated=%d skipped=%d root=%s",
        migrated,
        skipped,
        root,
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
