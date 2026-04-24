"""Phase 15 Step 0.3 reference fixtures: feature-parquet schema v1 -> v2 migration.

The migration entry point is
:func:`forensics.storage.migrations.002_feature_parquet_section.migrate_feature_parquet`.
A v1 parquet either lacks any stamped ``forensics.schema_version`` or carries
``... = 1`` in its parquet metadata (and crucially, no ``section`` column).
After migration the file is stamped at v2 and gains a ``section`` column
derived from the original ``url``.

These tests pin three behaviours the rest of Phase 15 depends on:

1. **Roundtrip happy path** — a v1 parquet is upgraded in place with a backup
   copy left behind for forensic re-runs.
2. **Edge case** — already-v2 parquets are no-ops (the migrator returns
   ``False`` and touches no bytes besides the existing file).
3. **Regression pin** — ``section`` values are derived via
   :func:`forensics.utils.url.section_from_url`, so any future URL-shape drift
   (e.g. mediaite.com path renames) shows up here as a test diff rather than a
   silent re-classification of historical articles.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from forensics.storage.parquet import (
    FEATURE_PARQUET_SCHEMA_METADATA_KEY,
    _read_parquet_schema_version,
    write_parquet_atomic,
)

# The migration module starts with a digit, so it cannot be imported via the
# usual ``from ... import`` statement. ``importlib.import_module`` is the
# pattern used in ``forensics.cli.migrate``.
_migrate_mod = importlib.import_module("forensics.storage.migrations.002_feature_parquet_section")
migrate_feature_parquet = _migrate_mod.migrate_feature_parquet


def _v1_rows() -> list[dict[str, object]]:
    """Three legacy rows — pre-J1 parquets had ``url`` but no ``section``."""
    return [
        {
            "article_id": "art-1",
            "author_id": "author-x",
            "url": "https://www.mediaite.com/news/headline-one/",
            "ttr": 0.55,
        },
        {
            "article_id": "art-2",
            "author_id": "author-x",
            "url": "https://www.mediaite.com/opinion/take-two/",
            "ttr": 0.61,
        },
        {
            "article_id": "art-3",
            "author_id": "author-x",
            "url": "https://www.mediaite.com/tv/clip-three/",
            "ttr": 0.49,
        },
    ]


def _write_v1_parquet(path: Path) -> None:
    """Write a parquet with no ``section`` column and no schema-version stamp."""
    pl.DataFrame(_v1_rows()).write_parquet(path)
    # Sanity: confirm the parquet is genuinely "v1" — no stamp + no section.
    assert _read_parquet_schema_version(path) is None
    table = pq.read_table(path)
    assert "section" not in table.schema.names


def test_migrate_v1_parquet_roundtrips_to_v2_with_section(tmp_path: Path) -> None:
    """Happy path: v1 parquet -> v2 parquet with derived ``section`` column + backup."""
    feat_path = tmp_path / "author-x.parquet"
    _write_v1_parquet(feat_path)

    migrated = migrate_feature_parquet(feat_path)
    assert migrated is True

    # Schema-version metadata is now stamped at v2.
    assert _read_parquet_schema_version(feat_path) == 2

    # Section column populated via section_from_url on the URL field.
    df = pl.read_parquet(feat_path)
    assert "section" in df.columns
    sections = df["section"].to_list()
    assert sections == ["news", "opinion", "tv"]

    # Backup copy preserved alongside under ``_pre_phase15_backup/``.
    backup = feat_path.parent / "_pre_phase15_backup" / feat_path.name
    assert backup.is_file(), "migration must leave a backup of the pre-migration file"


def test_migrate_already_v2_parquet_is_a_noop(tmp_path: Path) -> None:
    """Edge case: a parquet stamped at v2 is left alone (returns ``False``)."""
    feat_path = tmp_path / "author-y.parquet"
    rows = _v1_rows()
    for row in rows:
        row["section"] = "news"  # Pretend it's already v2.
    # ``write_parquet_atomic`` stamps via ``settings.features.feature_parquet_schema_version``.
    write_parquet_atomic(feat_path, rows)
    assert _read_parquet_schema_version(feat_path) is not None

    migrated = migrate_feature_parquet(feat_path)
    assert migrated is False, "v2 parquet must not be re-migrated"
    # No backup directory created on a no-op pass.
    assert not (feat_path.parent / "_pre_phase15_backup").exists()


def test_migration_section_values_pin_to_section_from_url(tmp_path: Path) -> None:
    """Regression pin: ``section`` values are an exact function of ``section_from_url``.

    Locking the table here means a future change to ``_SECTION_RE`` (e.g.
    accepting subdomain shifts) shows up loudly rather than re-classifying
    every historical row in the next pipeline run.
    """
    feat_path = tmp_path / "author-z.parquet"
    rows: list[dict[str, object]] = [
        {
            "article_id": "edge-1",
            "author_id": "author-z",
            "url": "https://www.mediaite.com/News/Mixed-Case/",  # case-insensitive
            "ttr": 0.5,
        },
        {
            "article_id": "edge-2",
            "author_id": "author-z",
            "url": "https://example.com/news/foreign/",  # non-mediaite -> unknown
            "ttr": 0.5,
        },
        {
            "article_id": "edge-3",
            "author_id": "author-z",
            "url": "",  # empty URL -> unknown
            "ttr": 0.5,
        },
    ]
    pl.DataFrame(rows).write_parquet(feat_path)
    assert _read_parquet_schema_version(feat_path) is None

    migrate_feature_parquet(feat_path)

    df = pl.read_parquet(feat_path)
    # Mixed case lowercased to "news"; foreign domain + empty URL -> "unknown".
    assert df["section"].to_list() == ["news", "unknown", "unknown"]


def test_metadata_key_constant_is_stable() -> None:
    """Edge case: the parquet metadata key is part of the cross-tool contract.

    DuckDB / pyarrow readers outside the Forensics package look this key up by
    string. If someone renames it, every previously-stamped file looks
    "unstamped" and gets re-migrated on next read. Pinning the constant
    surfaces the rename loudly.
    """
    assert FEATURE_PARQUET_SCHEMA_METADATA_KEY == "forensics.schema_version"
