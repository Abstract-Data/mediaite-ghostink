"""T-07 — duplicate-flag transaction rolls back if the mark phase fails."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from forensics.models import Article
from forensics.scraper.crawler import stable_article_id
from forensics.storage.repository import Repository


def test_apply_duplicate_flags_transaction_rollbacks_on_mark_failure(
    tmp_db,
    sample_author,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_db

    u1 = "https://www.mediaite.com/2020/01/01/a/"
    u2 = "https://www.mediaite.com/2020/01/02/b/"
    body = "duplicate body for rollback fixture " * 20
    a1 = Article(
        id=stable_article_id(u1),
        author_id=sample_author.id,
        url=u1,
        title="A",
        published_date=datetime(2020, 1, 1, tzinfo=UTC),
        clean_text=body,
        word_count=50,
        content_hash="h1",
        is_duplicate=False,
    )
    a2 = Article(
        id=stable_article_id(u2),
        author_id=sample_author.id,
        url=u2,
        title="B",
        published_date=datetime(2020, 1, 2, tzinfo=UTC),
        clean_text=body,
        word_count=50,
        content_hash="h2",
        is_duplicate=True,
    )
    with Repository(db_path) as repo:
        repo.ensure_schema()
        repo.upsert_author(sample_author)
        repo.upsert_article(a1)
        repo.upsert_article(a2)

    real_bulk = Repository._bulk_set_is_duplicate_on_conn

    def flaky_bulk(
        conn,
        article_ids: list[str],
        value: int,
        *,
        chunk_size: int = 500,
    ) -> int:
        if value == 1:
            msg = "simulated mark-phase failure"
            raise OSError(msg)
        return real_bulk(conn, article_ids, value, chunk_size=chunk_size)

    monkeypatch.setattr(
        Repository,
        "_bulk_set_is_duplicate_on_conn",
        staticmethod(flaky_bulk),
    )

    with Repository(db_path) as repo:
        repo.ensure_schema()
        with pytest.raises(OSError, match="simulated mark-phase failure"):
            repo.apply_duplicate_flags_transaction([a1.id, a2.id], [a2.id])

    with Repository(db_path) as repo:
        arts = {a.id: a for a in repo.get_all_articles()}
    assert arts[a1.id].is_duplicate is False
    assert arts[a2.id].is_duplicate is True
