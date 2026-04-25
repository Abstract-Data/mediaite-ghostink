"""SQLite forward migrations (``forensics.storage.migrations``)."""

from __future__ import annotations

import sqlite3

import pytest

from forensics.storage.migrations import applied_versions, discover_migrations
from forensics.storage.repository import init_db


def test_discover_includes_003_sqlite_migration() -> None:
    discovered = {name for _ver, name, _fn in discover_migrations()}
    assert "003_articles_word_count_check" in discovered


def test_init_db_applies_migrations_including_word_count_check(tmp_db) -> None:
    init_db(tmp_db)
    conn = sqlite3.connect(tmp_db)
    try:
        versions = applied_versions(conn)
        assert 3 in versions
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='articles'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and row[0]
    sql_norm = "".join(row[0].lower().split())
    assert "check(word_count>=0)" in sql_norm


def test_word_count_check_rejects_negative_insert(tmp_db, sample_author) -> None:
    init_db(tmp_db)
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            """
            INSERT INTO authors (
                id, name, slug, outlet, role, baseline_start, baseline_end,
                archive_url, is_shared_byline
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                sample_author.id,
                sample_author.name,
                sample_author.slug,
                sample_author.outlet,
                sample_author.role,
                sample_author.baseline_start.isoformat(),
                sample_author.baseline_end.isoformat(),
                sample_author.archive_url,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO articles (
                    id, author_id, url, title, published_date, raw_html_path,
                    clean_text, word_count, metadata, content_hash,
                    modified_date, modifier_user_id, scraped_at, is_duplicate
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, NULL, NULL, 0)
                """,
                (
                    "bad-wc-id",
                    sample_author.id,
                    "https://example.com/bad-wc/",
                    "t",
                    "2020-01-01T00:00:00+00:00",
                    "body",
                    -1,
                    "{}",
                    "h",
                ),
            )
        conn.rollback()
    finally:
        conn.close()
