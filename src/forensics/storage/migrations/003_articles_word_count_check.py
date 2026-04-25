"""Phase 16 F migration: enforce ``word_count >= 0`` on ``articles``.

SQLite cannot attach a new ``CHECK`` to an existing table. This migration
rebuilds ``articles`` with ``CHECK (word_count >= 0)``, copies all rows, swaps
the table, and recreates ``idx_articles_author_date``. Column layout matches
``_SCHEMA`` in :mod:`forensics.storage.repository` (no ``is_shared_byline`` on
``articles`` — that column lives on ``authors``).

Idempotent: if the live ``CREATE TABLE`` SQL for ``articles`` already encodes
the non-negative ``word_count`` check, the migration no-ops.
"""

from __future__ import annotations

import sqlite3


def _articles_enforce_word_count_non_negative(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='articles'"
    ).fetchone()
    if not row or not row[0]:
        return False
    normalized = "".join(str(row[0]).lower().split())
    return "check(word_count>=0)" in normalized


def migrate(conn: sqlite3.Connection) -> None:
    if _articles_enforce_word_count_non_negative(conn):
        return
    conn.executescript(
        """
CREATE TABLE articles_new (
    id TEXT PRIMARY KEY,
    author_id TEXT NOT NULL REFERENCES authors(id),
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    published_date DATETIME NOT NULL,
    raw_html_path TEXT,
    clean_text TEXT NOT NULL,
    word_count INTEGER NOT NULL CHECK (word_count >= 0),
    metadata JSON,
    content_hash TEXT NOT NULL,
    modified_date TEXT,
    modifier_user_id INTEGER,
    scraped_at TEXT,
    is_duplicate INTEGER NOT NULL DEFAULT 0
);

INSERT INTO articles_new (
    id, author_id, url, title, published_date, raw_html_path,
    clean_text, word_count, metadata, content_hash,
    modified_date, modifier_user_id, scraped_at, is_duplicate
)
SELECT
    id, author_id, url, title, published_date, raw_html_path,
    clean_text, word_count, metadata, content_hash,
    modified_date, modifier_user_id, scraped_at, is_duplicate
FROM articles;

DROP TABLE articles;
ALTER TABLE articles_new RENAME TO articles;

CREATE INDEX IF NOT EXISTS idx_articles_author_date ON articles(author_id, published_date);
"""
    )
