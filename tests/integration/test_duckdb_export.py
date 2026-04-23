"""Integration test for ``export_to_duckdb`` (F2)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import polars as pl
import pytest

from forensics.models.article import Article
from forensics.models.author import Author
from forensics.storage.duckdb_queries import export_to_duckdb
from forensics.storage.repository import Repository


def _seed_repo(db_path: Path) -> None:
    with Repository(db_path) as repo:
        author = Author(
            id="author-1",
            name="Alice",
            slug="alice",
            outlet="mediaite.com",
            role="target",
            baseline_start=date(2024, 1, 1),
            baseline_end=date(2024, 6, 30),
            archive_url="https://example.com/a",
        )
        repo.upsert_author(author)
        for i in range(3):
            article = Article(
                id=f"art-{i}",
                author_id=author.id,
                url=f"https://example.com/a/{i}",  # type: ignore[arg-type]
                title=f"Post {i}",
                published_date=datetime(2024, 3, 1, tzinfo=UTC),
                clean_text=f"body {i}",
                word_count=50,
                metadata={},
                content_hash=f"h{i}",
            )
            repo.upsert_article(article)


def _write_feature_shard(features_dir: Path, slug: str = "alice") -> None:
    features_dir.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(
        {
            "article_id": [f"art-{i}" for i in range(3)],
            "author_id": ["author-1"] * 3,
            "timestamp": [datetime(2024, 3, i + 1, tzinfo=UTC).isoformat() for i in range(3)],
            "ttr": [0.5, 0.52, 0.48],
        }
    )
    df.write_parquet(features_dir / f"{slug}.parquet")


def test_export_to_duckdb_creates_file_with_core_tables(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "articles.db"
    _seed_repo(db_path)

    out = tmp_path / "out.duckdb"
    report = export_to_duckdb(db_path, out, include_features=False, include_analysis=False)

    assert out.is_file()
    assert report.bytes_written > 0
    assert report.tables == {"authors": 1, "articles": 3}
    assert report.total_rows == 4
    assert report.output_path == out

    con = duckdb.connect(str(out))
    try:
        author_names = con.execute("SELECT name FROM authors").fetchall()
        assert author_names == [("Alice",)]
        article_count = con.execute("SELECT COUNT(*) FROM articles").fetchone()
        assert article_count == (3,)
    finally:
        con.close()


def test_export_to_duckdb_includes_feature_shards(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "articles.db"
    _seed_repo(db_path)
    _write_feature_shard(data_dir / "features")

    out = tmp_path / "out.duckdb"
    report = export_to_duckdb(db_path, out, include_features=True, include_analysis=False)

    assert "features" in report.tables
    assert report.tables["features"] == 3


def test_export_to_duckdb_overwrites_existing_output(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "articles.db"
    _seed_repo(db_path)

    out = tmp_path / "out.duckdb"
    out.write_text("sentinel", encoding="utf-8")  # not a real duckdb file

    report = export_to_duckdb(db_path, out, include_features=False, include_analysis=False)
    assert out.is_file()
    assert report.bytes_written > 0

    # readable as a duckdb DB (proves we didn't just keep the sentinel)
    con = duckdb.connect(str(out))
    try:
        con.execute("SELECT 1").fetchone()
    finally:
        con.close()


def test_export_to_duckdb_requires_existing_sqlite(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        export_to_duckdb(tmp_path / "missing.db", tmp_path / "out.duckdb")
