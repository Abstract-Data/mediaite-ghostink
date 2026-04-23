"""Unit tests for ``Repository._connect`` PRAGMA configuration (A1 / P1-DATA-001)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from forensics.storage.repository import Repository


def test_foreign_keys_pragma_enabled(tmp_path: Path) -> None:
    with Repository(tmp_path / "articles.db") as repo:
        row = repo._require_conn().execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1


def test_foreign_keys_enforced_against_orphan_article(tmp_path: Path) -> None:
    """An INSERT referencing a non-existent author must raise IntegrityError."""
    with Repository(tmp_path / "articles.db") as repo:
        conn = repo._require_conn()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO articles (
                    id, author_id, url, title, published_date, clean_text,
                    word_count, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "article-orphan",
                    "does-not-exist",
                    "https://www.mediaite.com/x",
                    "Orphan",
                    "2026-01-01T00:00:00+00:00",
                    "body",
                    1,
                    "abc",
                ),
            )
