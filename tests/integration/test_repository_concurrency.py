"""Phase 16 E: ``Repository`` serializes mutations across threads (internal lock)."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest

from forensics.models.article import Article
from forensics.models.author import Author
from forensics.storage.repository import Repository


def _bench_author() -> Author:
    return Author(
        id="author-concurrency-1",
        name="Concurrency Author",
        slug="concurrency-author",
        outlet="mediaite.com",
        role="control",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url="https://www.mediaite.com/author/concurrency-author/",
    )


def _bench_article(author_id: str, worker_id: int, seq: int) -> Article:
    return Article(
        id=f"w{worker_id}-s{seq}",
        author_id=author_id,
        url=f"https://www.mediaite.com/2024/{worker_id:02d}/{seq:04d}/post/",
        title=f"Title {worker_id}-{seq}",
        published_date=datetime(2024, 1, 1 + (seq % 27), 12, 0, tzinfo=UTC),
        clean_text=f"body text for {worker_id} article {seq} " * 20,
        word_count=120,
        content_hash=f"hash-{worker_id}-{seq}",
    )


@pytest.mark.asyncio
async def test_repository_concurrent_writes_and_reader(tmp_path) -> None:
    """Eight worker threads upsert 100 articles each alongside a concurrent reader."""
    db_path = tmp_path / "concurrent.db"
    with Repository(db_path) as repo:
        author = _bench_author()
        await asyncio.to_thread(repo.upsert_author, author)

        async def writer(worker_id: int) -> None:
            for seq in range(100):
                art = _bench_article(author.id, worker_id, seq)
                await asyncio.to_thread(repo.upsert_article, art)

        reader_ok = True

        async def reader() -> None:
            nonlocal reader_ok
            # Enough overlap with 800 upserts without loading the full table thousands of times.
            for _ in range(400):
                articles = await asyncio.to_thread(repo.get_all_articles)
                ids = [a.id for a in articles]
                if len(ids) != len(set(ids)):
                    reader_ok = False
                    return
                for a in articles:
                    if a.word_count < 1 or not a.title or not str(a.url):
                        reader_ok = False
                        return
                    if not a.content_hash.startswith("hash-"):
                        reader_ok = False
                        return

        await asyncio.gather(
            *(writer(w) for w in range(8)),
            reader(),
        )

        assert reader_ok
        final = repo.get_all_articles()
        ids_final = [a.id for a in final]
        assert len(ids_final) == 800
        assert len(set(ids_final)) == 800
