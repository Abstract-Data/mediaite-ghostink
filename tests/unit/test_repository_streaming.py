"""Unit tests for streaming iterator variants on ``Repository`` (H2 / P2-PERF-001)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from forensics.models.article import Article
from forensics.models.author import Author
from forensics.storage.repository import Repository


def _author(slug: str = "author-x") -> Author:
    return Author(
        id=f"id-{slug}",
        name="X",
        slug=slug,
        outlet="mediaite.com",
        role="target",
        archive_url=f"https://www.mediaite.com/author/{slug}/",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
    )


def _article(author_id: str, *, i: int, slug: str = "x") -> Article:
    return Article(
        id=f"{slug}-{i}",
        author_id=author_id,
        url=f"https://www.mediaite.com/p/{slug}/{i}",
        title=f"T{i}",
        published_date=datetime(2026, 1, i + 1, tzinfo=UTC),
        clean_text=f"body {i}",
        word_count=2,
        content_hash=f"h{slug}{i}",
    )


def test_iter_articles_by_author_yields_only_that_author(tmp_path: Path) -> None:
    target = _author("t")
    control = _author("c")
    with Repository(tmp_path / "articles.db") as repo:
        repo.upsert_author(target)
        repo.upsert_author(control)
        for i in range(3):
            repo.upsert_article(_article(target.id, i=i, slug="t"))
            repo.upsert_article(_article(control.id, i=i, slug="c"))
        ids = [a.id for a in repo.iter_articles_by_author(target.id)]
    assert ids == ["t-0", "t-1", "t-2"]


def test_iter_articles_by_author_respects_batch_size(tmp_path: Path) -> None:
    author = _author()
    with Repository(tmp_path / "articles.db") as repo:
        repo.upsert_author(author)
        for i in range(5):
            repo.upsert_article(_article(author.id, i=i))
        collected = list(repo.iter_articles_by_author(author.id, batch_size=2))
    assert [a.id for a in collected] == ["x-0", "x-1", "x-2", "x-3", "x-4"]


def test_iter_articles_by_author_rejects_invalid_batch_size(tmp_path: Path) -> None:
    with Repository(tmp_path / "articles.db") as repo:
        with pytest.raises(ValueError):
            list(repo.iter_articles_by_author("nope", batch_size=0))


def test_get_articles_by_author_matches_iterator(tmp_path: Path) -> None:
    author = _author()
    with Repository(tmp_path / "articles.db") as repo:
        repo.upsert_author(author)
        for i in range(3):
            repo.upsert_article(_article(author.id, i=i))
        eager = repo.get_articles_by_author(author.id)
        streamed = list(repo.iter_articles_by_author(author.id))
    assert [a.id for a in eager] == [a.id for a in streamed]
