"""Unit tests for corpus hashing in :mod:`forensics.utils.provenance` (Phase 16 C)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from forensics.utils.provenance import (
    compute_corpus_hash,
    compute_corpus_hash_legacy,
)


def _articles_table_ddl() -> str:
    return (
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY, "
        "content_hash TEXT NOT NULL, "
        "is_duplicate INTEGER NOT NULL DEFAULT 0)"
    )


def test_corpus_hash_uuid_order_dependency_same_analyzable_fingerprint(tmp_path: Path) -> None:
    """Two DBs with the same multiset of ``content_hash`` but different ``id`` order.

    Legacy :func:`compute_corpus_hash_legacy` depended on surrogate key order (Phase 16
    bug). :func:`compute_corpus_hash` orders by ``content_hash`` and excludes duplicates,
    so both databases must agree.
    """
    db_a = tmp_path / "order_a.db"
    db_b = tmp_path / "order_b.db"
    for path, first, second in (
        (db_a, (1, "aaa"), (2, "bbb")),
        (db_b, (1, "bbb"), (2, "aaa")),
    ):
        conn = sqlite3.connect(path)
        conn.execute(_articles_table_ddl())
        conn.execute(
            "INSERT INTO articles(id, content_hash, is_duplicate) VALUES (?,?,0)",
            first,
        )
        conn.execute(
            "INSERT INTO articles(id, content_hash, is_duplicate) VALUES (?,?,0)",
            second,
        )
        conn.commit()
        conn.close()

    assert compute_corpus_hash_legacy(db_a) != compute_corpus_hash_legacy(db_b)
    assert compute_corpus_hash(db_a) == compute_corpus_hash(db_b)


def test_compute_corpus_hash_excludes_duplicates(tmp_path: Path) -> None:
    solo = tmp_path / "solo_only.db"
    c2 = sqlite3.connect(solo)
    c2.execute(_articles_table_ddl())
    c2.execute("INSERT INTO articles(id, content_hash) VALUES (9,'solo')")
    c2.commit()
    c2.close()

    db = tmp_path / "dup.db"
    conn = sqlite3.connect(db)
    conn.execute(_articles_table_ddl())
    conn.execute(
        "INSERT INTO articles(id, content_hash, is_duplicate) VALUES (1,'solo',0)",
    )
    conn.execute(
        "INSERT INTO articles(id, content_hash, is_duplicate) VALUES (2,'duped',1)",
    )
    conn.commit()
    conn.close()
    assert compute_corpus_hash(db) != compute_corpus_hash_legacy(db)
    assert compute_corpus_hash(db) == compute_corpus_hash(solo)
