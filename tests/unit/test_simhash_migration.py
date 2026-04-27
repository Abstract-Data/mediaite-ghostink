"""Simhash fingerprint versioning and recompute CLI (PR94 item 4)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from forensics.cli import app
from forensics.models.article import Article
from forensics.models.author import Author
from forensics.storage.repository import Repository, init_db
from forensics.utils.hashing import SIMHASH_FINGERPRINT_VERSION, simhash


def _article(aid: str, author_id: str, text: str) -> Article:
    return Article(
        id=aid,
        author_id=author_id,
        url=f"https://www.example.com/{aid}",
        title="t",
        published_date=datetime(2022, 1, 1, tzinfo=UTC),
        clean_text=text,
        word_count=max(50, len(text.split())),
        content_hash="0" * 64,
    )


def test_load_dedup_simhashes_filters_stale_then_recompute_restores(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = tmp_path / "articles.db"
    init_db(db)
    author = Author(
        name="A",
        slug="a",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 1, 1),
        archive_url="https://example.com/a",
        id="auth1",
    )
    body = "word " * 30
    a_ok = _article("id-ok", "auth1", body)
    a_old = _article("id-old", "auth1", body + " x")
    a_miss = _article("id-miss", "auth1", body + " y")

    fp_ok = simhash(body)
    fp_stale = simhash("different corpus text entirely for stale")

    with Repository(db) as repo:
        repo.upsert_author(author)
        for art in (a_ok, a_old, a_miss):
            repo.upsert_article(art)
        conn = repo._require_conn()
        conn.execute(
            "UPDATE articles SET dedup_simhash = ?, dedup_simhash_version = ? WHERE id = ?",
            (format(fp_ok, "x"), SIMHASH_FINGERPRINT_VERSION, "id-ok"),
        )
        conn.execute(
            "UPDATE articles SET dedup_simhash = ?, dedup_simhash_version = ? WHERE id = ?",
            (format(fp_stale, "x"), "v1", "id-old"),
        )
        conn.execute(
            "UPDATE articles SET dedup_simhash = ?, dedup_simhash_version = ? WHERE id = ?",
            (format(123, "x"), None, "id-miss"),
        )

    with Repository(db) as repo:
        with caplog.at_level("WARNING"):
            first = repo.load_dedup_simhashes()
        assert "excluding 2 article" in caplog.text
        assert len(first) == 1
        assert first[0][0] == "id-ok"
        summary = repo.recompute_stale_dedup_simhashes(limit=None)
        assert summary["recomputed"] == 2
        assert summary["errors"] == 0
        second = repo.load_dedup_simhashes()
        assert len(second) == 3
        ids = {t[0] for t in second}
        assert ids == {"id-ok", "id-old", "id-miss"}


def test_dedup_recompute_cli_json(tmp_path: Path) -> None:
    db = tmp_path / "articles.db"
    init_db(db)
    author = Author(
        name="A",
        slug="a",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 1, 1),
        archive_url="https://example.com/a",
        id="auth1",
    )
    art = _article("x1", "auth1", "hello " * 20)
    with Repository(db) as repo:
        repo.upsert_author(author)
        repo.upsert_article(art)

    runner = CliRunner()
    r = runner.invoke(
        app,
        ["--output", "json", "dedup", "recompute-fingerprints", "--db", str(db)],
        color=False,
    )
    assert r.exit_code == 0, (r.stdout or r.output) + (r.stderr or "")
    stdout = (r.stdout or r.output or "").strip()
    body = json.loads(stdout)
    assert body["ok"] is True
    assert body["type"] == "dedup.recompute_fingerprints"
    assert body["data"] == {"recomputed": 1, "skipped": 0, "errors": 0}
