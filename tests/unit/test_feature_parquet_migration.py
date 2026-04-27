"""Phase 15 Step 0.3 reference fixtures: feature-parquet schema v1 -> v2 migration.

The migration entry point is
:func:`forensics.storage.migrations.002_feature_parquet_section.migrate_feature_parquet`.
A v1 parquet either lacks any stamped ``forensics.schema_version`` or carries
``... = 1`` in its parquet metadata (and crucially, no ``section`` column).
After migration the file is stamped at v2 and gains a ``section`` column
derived from the original ``url``.

These tests pin the behaviours the rest of Phase 15 depends on:

1. **Roundtrip happy path** — a v1 parquet is upgraded in place with a backup
   copy left behind for forensic re-runs.
2. **Edge case** — already-v2 parquets are no-ops (the migrator returns
   ``False`` and touches no bytes besides the existing file).
3. **Regression pin** — ``section`` values are derived via
   :func:`forensics.utils.url.section_from_url`, so any future URL-shape drift
   (e.g. mediaite.com path renames) shows up here as a test diff rather than a
   silent re-classification of historical articles.
4. **JOIN happy path** — corpus parquets that store only ``article_id`` get
   ``section`` backfilled by JOINing against ``articles.db``.
5. **JOIN miss** — IDs that don't match anything in ``articles.db`` get
   ``section = "unknown"`` plus a per-file WARNING.
6. **Missing DB** — when the DB is absent entirely, the migrator falls back to
   ``unknown`` for every row without crashing.
7. **JOIN regression pin** — the resulting section value-counts for a fixed
   fixture corpus are locked.
"""

from __future__ import annotations

import importlib
import logging
import sqlite3
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq
import pytest

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


def _write_articles_db(path: Path, rows: list[tuple[str, str]]) -> None:
    """Build a minimal ``articles`` table at ``path`` with ``(id, url)`` rows.

    Uses just the columns the migrator's JOIN reads. Real schema is broader
    (see ``Repository._SCHEMA``); narrowing keeps the fixture surface small.
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE articles (id TEXT PRIMARY KEY, url TEXT NOT NULL)")
        conn.executemany("INSERT INTO articles (id, url) VALUES (?, ?)", rows)
        conn.commit()
    finally:
        conn.close()


def _id_only_rows() -> list[dict[str, object]]:
    """Real-corpus shape: parquet has ``article_id`` but no ``url``."""
    return [
        {"article_id": "art-1", "author_id": "author-x", "ttr": 0.55},
        {"article_id": "art-2", "author_id": "author-x", "ttr": 0.61},
        {"article_id": "art-3", "author_id": "author-x", "ttr": 0.49},
    ]


def _write_v1_id_only_parquet(path: Path) -> None:
    pl.DataFrame(_id_only_rows()).write_parquet(path)
    assert _read_parquet_schema_version(path) is None
    table = pq.read_table(path)
    assert "section" not in table.schema.names
    assert "url" not in table.schema.names
    assert "article_id" in table.schema.names


def test_migrate_id_only_parquet_joins_articles_db_for_section(tmp_path: Path) -> None:
    """JOIN happy path: parquet with ``article_id`` only -> derive via articles.db."""
    feat_path = tmp_path / "author-x.parquet"
    _write_v1_id_only_parquet(feat_path)

    db_path = tmp_path / "articles.db"
    _write_articles_db(
        db_path,
        [
            ("art-1", "https://www.mediaite.com/news/headline-one/"),
            ("art-2", "https://www.mediaite.com/opinion/take-two/"),
            ("art-3", "https://www.mediaite.com/tv/clip-three/"),
        ],
    )

    migrated = migrate_feature_parquet(feat_path, articles_db=db_path)
    assert migrated is True
    assert _read_parquet_schema_version(feat_path) == 2

    df = pl.read_parquet(feat_path)
    assert "section" in df.columns
    assert df["section"].to_list() == ["news", "opinion", "tv"]
    assert (feat_path.parent / "_pre_phase15_backup" / feat_path.name).is_file()


def test_migrate_id_only_parquet_unknown_for_unmatched_ids_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """JOIN miss: unknown article_ids land at 'unknown' and a WARNING is logged."""
    feat_path = tmp_path / "author-y.parquet"
    _write_v1_id_only_parquet(feat_path)

    db_path = tmp_path / "articles.db"
    # Only one row matches; the other two are absent from the DB.
    _write_articles_db(
        db_path,
        [("art-1", "https://www.mediaite.com/news/headline-one/")],
    )

    with caplog.at_level(logging.WARNING, logger="forensics.storage.migrations"):
        migrate_feature_parquet(feat_path, articles_db=db_path)

    df = pl.read_parquet(feat_path)
    assert df["section"].to_list() == ["news", "unknown", "unknown"]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("section='unknown'" in r.getMessage() for r in warnings), (
        "expected a per-file WARNING when JOIN leaves rows unresolved"
    )


def test_migrate_id_only_parquet_no_articles_db_falls_back_to_unknown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Missing DB: every row falls back to 'unknown' without crashing."""
    feat_path = tmp_path / "author-z.parquet"
    _write_v1_id_only_parquet(feat_path)
    missing_db = tmp_path / "does_not_exist.db"
    assert not missing_db.exists()

    with caplog.at_level(logging.WARNING, logger="forensics.storage.migrations"):
        migrated = migrate_feature_parquet(feat_path, articles_db=missing_db)

    assert migrated is True
    df = pl.read_parquet(feat_path)
    assert df["section"].to_list() == ["unknown", "unknown", "unknown"]
    assert _read_parquet_schema_version(feat_path) == 2
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_migrate_all_locks_section_value_counts_for_fixture_corpus(tmp_path: Path) -> None:
    """JOIN regression pin: the resulting ``section`` distribution is locked.

    A fixed-seed fixture corpus + fixed articles.db must always produce the
    same ``section.value_counts()``. Any drift in URL parsing or JOIN logic
    surfaces here as a test diff rather than a silent shift in J5 verdicts.
    """
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    db_path = tmp_path / "articles.db"

    fixture_urls = [
        ("art-001", "https://www.mediaite.com/news/a/"),
        ("art-002", "https://www.mediaite.com/news/b/"),
        ("art-003", "https://www.mediaite.com/news/c/"),
        ("art-004", "https://www.mediaite.com/opinion/a/"),
        ("art-005", "https://www.mediaite.com/opinion/b/"),
        ("art-006", "https://www.mediaite.com/tv/a/"),
        ("art-007", "https://www.mediaite.com/politics/a/"),
        ("art-008", "https://example.com/foreign/"),  # -> unknown via parse
    ]
    _write_articles_db(db_path, fixture_urls)

    # Two parquets — half the corpus each, both id-only.
    for name, slice_ in (("a.parquet", fixture_urls[:4]), ("b.parquet", fixture_urls[4:])):
        rows = [{"article_id": aid, "author_id": "shared", "ttr": 0.5} for aid, _ in slice_]
        pl.DataFrame(rows).write_parquet(features_dir / name)

    mig = importlib.import_module("forensics.storage.migrations.002_feature_parquet_section")
    migrated, skipped = mig.migrate_all(features_dir, articles_db=db_path)
    assert (migrated, skipped) == (2, 0)

    combined = pl.concat(
        [
            pl.read_parquet(features_dir / "a.parquet"),
            pl.read_parquet(features_dir / "b.parquet"),
        ]
    )
    counts = {row["section"]: row["count"] for row in combined["section"].value_counts().to_dicts()}
    # Locked distribution: 3 news / 2 opinion / 1 tv / 1 politics / 1 unknown.
    assert counts == {"news": 3, "opinion": 2, "tv": 1, "politics": 1, "unknown": 1}


def test_migrate_with_url_column_ignores_articles_db(tmp_path: Path) -> None:
    """Regression: legacy parquets carrying a ``url`` column don't need the DB."""
    feat_path = tmp_path / "legacy.parquet"
    _write_v1_parquet(feat_path)

    # Even with a wrong/missing DB, the URL-column path must still derive
    # sections directly. (Pinning preserves backwards compatibility.)
    migrate_feature_parquet(feat_path, articles_db=tmp_path / "no_such.db")

    df = pl.read_parquet(feat_path)
    assert df["section"].to_list() == ["news", "opinion", "tv"]
    assert _read_parquet_schema_version(feat_path) == 2


def test_migrate_dry_run_with_articles_db_writes_nothing(tmp_path: Path) -> None:
    """``--dry-run`` must remain inert even when an articles.db is supplied."""
    feat_path = tmp_path / "dry.parquet"
    _write_v1_id_only_parquet(feat_path)
    db_path = tmp_path / "articles.db"
    _write_articles_db(db_path, [("art-1", "https://www.mediaite.com/news/x/")])

    migrated = migrate_feature_parquet(feat_path, articles_db=db_path, dry_run=True)
    assert migrated is True
    # No section column added, no schema stamp, no backup directory.
    assert _read_parquet_schema_version(feat_path) is None
    df = pl.read_parquet(feat_path)
    assert "section" not in df.columns
    assert not (feat_path.parent / "_pre_phase15_backup").exists()
