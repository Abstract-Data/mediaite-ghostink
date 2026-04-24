"""Phase 15 D migration: add ``is_shared_byline`` column to ``authors``.

Adds a boolean (INTEGER 0/1) flag to the ``authors`` table. No backfill —
downstream ``forensics survey`` runs populate the field heuristically using
:func:`forensics.survey.shared_byline.is_shared_byline` on next contact.

Idempotent: the ALTER is gated by a ``PRAGMA table_info`` check so repeated
runs are harmless.
"""

from __future__ import annotations

import sqlite3


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(r[1]) == column for r in rows)


def migrate(conn: sqlite3.Connection) -> None:
    if _column_exists(conn, "authors", "is_shared_byline"):
        return
    conn.execute("ALTER TABLE authors ADD COLUMN is_shared_byline INTEGER NOT NULL DEFAULT 0")
