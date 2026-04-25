"""Tests for ``corpus_custody.json`` schema v1 vs v2 and :func:`verify_corpus_hash`."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from forensics.utils.provenance import (
    compute_corpus_hash,
    compute_corpus_hash_legacy,
    verify_corpus_hash,
    write_corpus_custody,
)


def _articles_ddl() -> str:
    return (
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY, "
        "content_hash TEXT NOT NULL, "
        "is_duplicate INTEGER NOT NULL DEFAULT 0)"
    )


def _seed_two_row_id_order_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(_articles_ddl())
    conn.execute(
        "INSERT INTO articles(id, content_hash, is_duplicate) VALUES (1,'bbb',0)",
    )
    conn.execute(
        "INSERT INTO articles(id, content_hash, is_duplicate) VALUES (2,'aaa',0)",
    )
    conn.commit()
    conn.close()


def test_verify_schema_v1_compares_legacy_hash(tmp_path: Path) -> None:
    db = tmp_path / "articles.db"
    _seed_two_row_id_order_db(db)
    legacy = compute_corpus_hash_legacy(db)
    assert legacy != compute_corpus_hash(db)

    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    payload = {
        "corpus_hash": legacy,
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    (analysis_dir / "corpus_custody.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    ok, msg = verify_corpus_hash(db, analysis_dir)
    assert ok is True
    assert "v1" in msg


def test_verify_schema_v2_compares_analyzable_hash(tmp_path: Path) -> None:
    db = tmp_path / "articles.db"
    _seed_two_row_id_order_db(db)
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    write_corpus_custody(db, analysis_dir)
    loaded = json.loads((analysis_dir / "corpus_custody.json").read_text(encoding="utf-8"))
    assert loaded.get("schema_version") == 2
    assert loaded.get("corpus_hash_v1") == compute_corpus_hash_legacy(db)
    assert loaded.get("corpus_hash") == compute_corpus_hash(db)

    ok, msg = verify_corpus_hash(db, analysis_dir)
    assert ok is True
    assert "v2" in msg


def test_verify_schema_v2_detects_tamper(tmp_path: Path) -> None:
    db = tmp_path / "articles.db"
    _seed_two_row_id_order_db(db)
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    write_corpus_custody(db, analysis_dir)
    path = analysis_dir / "corpus_custody.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["corpus_hash"] = "0" * 12
    path.write_text(json.dumps(data), encoding="utf-8")

    ok, msg = verify_corpus_hash(db, analysis_dir)
    assert ok is False
    assert "mismatch" in msg.lower()
    assert "v2" in msg
