"""Add optional persisted simhash fingerprint columns for dedup (D-01 / PR94)."""

from __future__ import annotations

import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(articles)").fetchall()
    names = {str(r[1]) for r in rows}
    if "dedup_simhash" not in names:
        conn.execute("ALTER TABLE articles ADD COLUMN dedup_simhash TEXT;")
    if "dedup_simhash_version" not in names:
        conn.execute("ALTER TABLE articles ADD COLUMN dedup_simhash_version TEXT;")
