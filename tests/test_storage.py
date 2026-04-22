"""SQLite repository and export tests."""

from __future__ import annotations

import json
from pathlib import Path

from forensics.models import Article
from forensics.storage.export import export_articles_jsonl
from forensics.storage.repository import Repository, init_db, insert_analysis_run
from forensics.utils import clean_text, content_hash, simhash, word_count


def test_insert_analysis_run_persists_row(tmp_path: Path) -> None:
    import sqlite3
    from contextlib import closing

    db_path = tmp_path / "articles.db"
    rid = insert_analysis_run(db_path, config_hash="abc123", description="unit test")
    assert len(rid) == 36
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(
            "SELECT id, config_hash, description FROM analysis_runs WHERE id = ?",
            (rid,),
        ).fetchone()
    assert row is not None
    assert row[1] == "abc123"
    assert row[2] == "unit test"


def test_init_db_creates_tables(tmp_path: Path) -> None:
    import sqlite3
    from contextlib import closing

    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {r[0] for r in rows}
    assert "authors" in names
    assert "articles" in names
    assert "analysis_runs" in names


def test_upsert_author_round_trip(tmp_db: Path, sample_author) -> None:
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        loaded = repo.get_author(sample_author.id)
    assert loaded is not None
    assert loaded.slug == sample_author.slug


def test_upsert_article_and_query(tmp_db: Path, sample_author, sample_article) -> None:
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(sample_article)
        rows = repo.get_articles_by_author(sample_author.id)
        assert len(rows) == 1
        assert rows[0].title == sample_article.title
        unfetched = repo.get_unfetched_urls()
        assert len(unfetched) == 1


def test_export_articles_jsonl_round_trip(
    tmp_path: Path, tmp_db: Path, sample_author, sample_article
) -> None:
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(sample_article)
    out = tmp_path / "articles.jsonl"
    count = export_articles_jsonl(tmp_db, out)
    assert count == 1
    line = out.read_text(encoding="utf-8").strip()
    data = json.loads(line)
    restored = Article.model_validate(data)
    assert restored.id == sample_article.id
    assert str(restored.url) == str(sample_article.url)


def test_get_all_articles(tmp_db: Path, sample_author, sample_article) -> None:
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(sample_article)
        assert len(repo.get_all_articles()) == 1


def test_text_and_hash_helpers() -> None:
    raw = "  <p>Hello &amp; world</p>  \n\n"
    cleaned = clean_text(raw)
    assert "Hello" in cleaned
    assert word_count("one two three") == 3
    assert len(content_hash("abc")) == 64
    assert isinstance(simhash("token token token"), int)
