"""Phase C: streaming dedup / export parity vs in-memory reference (small fixtures)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime

from forensics.models import Article
from forensics.scraper.crawler import stable_article_id
from forensics.scraper.dedup import _dedup_union_find, _find, deduplicate_articles
from forensics.storage.export import export_articles_jsonl
from forensics.storage.repository import Repository
from forensics.utils.hashing import simhash


def _reference_dup_ids_from_parent(
    pool: list[Article], parent: list[int]
) -> tuple[list[str], dict[str, bool]]:
    n = len(pool)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[_find(parent, i)].append(i)

    dup_ids: list[str] = []
    flags: dict[str, bool] = {}
    for members in groups.values():
        canonical_i = min(members, key=lambda i: pool[i].published_date)
        for i in members:
            is_dup = i != canonical_i
            flags[pool[i].id] = is_dup
            if is_dup:
                dup_ids.append(pool[i].id)
    return dup_ids, flags


def _reference_duplicate_ids_from_pool(
    pool: list[Article], *, hamming_threshold: int
) -> tuple[list[str], dict[str, bool]]:
    """Pre-streaming semantics: union-find on simhash(pool), earliest date wins per component."""
    if not pool:
        return [], {}
    fingerprints = [simhash(a.clean_text) for a in pool]
    parent = _dedup_union_find(fingerprints, hamming_threshold)
    return _reference_dup_ids_from_parent(pool, parent)


def test_iter_dedup_source_rows_matches_filtered_get_all(tmp_db, sample_author) -> None:
    body = "streaming parity fixture text " * 40
    u_skip = "https://www.mediaite.com/2020/01/01/redirect-case/"
    u_in = "https://www.mediaite.com/2020/01/02/in-pool/"
    a_redirect = Article(
        id=stable_article_id(u_skip),
        author_id=sample_author.id,
        url=u_skip,
        title="R",
        published_date=datetime(2020, 1, 1, tzinfo=UTC),
        clean_text="[REDIRECT:https://elsewhere]",
        word_count=10,
        content_hash="r1",
    )
    a_normal = Article(
        id=stable_article_id(u_in),
        author_id=sample_author.id,
        url=u_in,
        title="OK",
        published_date=datetime(2020, 1, 2, tzinfo=UTC),
        clean_text=body,
        word_count=50,
        content_hash="n1",
    )
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(a_redirect)
        repo.upsert_article(a_normal)
        pool_ref = [
            a
            for a in repo.get_all_articles()
            if a.clean_text and not a.clean_text.startswith("[REDIRECT:")
        ]
        streamed = list(repo.iter_dedup_source_rows(batch_size=1))
    assert [a.id for a in pool_ref] == [t[0] for t in streamed]
    for art, (sid, pub, title, ct) in zip(pool_ref, streamed, strict=True):
        assert art.id == sid
        assert art.published_date == pub
        assert art.title == title
        assert art.clean_text == ct


def test_deduplicate_articles_matches_reference_assignment(tmp_db, sample_author) -> None:
    body = "national politics coverage continues with detailed reporting " * 30
    u1 = "https://www.mediaite.com/2020/01/01/a/"
    u2 = "https://www.mediaite.com/2020/01/02/b/"
    u3 = "https://www.mediaite.com/2020/01/03/c/"
    a1 = Article(
        id=stable_article_id(u1),
        author_id=sample_author.id,
        url=u1,
        title="A",
        published_date=datetime(2020, 1, 1, tzinfo=UTC),
        clean_text=body,
        word_count=50,
        content_hash="h1",
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
    )
    a3 = Article(
        id=stable_article_id(u3),
        author_id=sample_author.id,
        url=u3,
        title="C",
        published_date=datetime(2020, 1, 3, tzinfo=UTC),
        clean_text="totally different content for isolation " * 20,
        word_count=50,
        content_hash="h3",
    )
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(a1)
        repo.upsert_article(a2)
        repo.upsert_article(a3)
        pool_ref = [
            a
            for a in repo.get_all_articles()
            if a.clean_text and not a.clean_text.startswith("[REDIRECT:")
        ]
    expected_dups, expected_flags = _reference_duplicate_ids_from_pool(
        pool_ref, hamming_threshold=3
    )

    got_dups = deduplicate_articles(tmp_db, hamming_threshold=3)
    assert sorted(got_dups) == sorted(expected_dups)

    with Repository(tmp_db) as repo:
        by_id = {a.id: a for a in repo.get_all_articles()}
    for aid, exp_dup in expected_flags.items():
        assert by_id[aid].is_duplicate is exp_dup
    assert by_id[a3.id].is_duplicate is False


def test_export_articles_jsonl_line_count_and_content_parity(
    tmp_path, tmp_db, sample_author
) -> None:
    """Streaming export matches one JSON line per DB row and equals reference dump."""
    rows: list[Article] = []
    for i in range(10):
        url = f"https://www.mediaite.com/2024/01/{i + 1:02d}/post/"
        rows.append(
            Article(
                id=stable_article_id(url),
                author_id=sample_author.id,
                url=url,
                title=f"T{i}",
                published_date=datetime(2024, 1, i + 1, tzinfo=UTC),
                clean_text=f"body {i} " * 30,
                word_count=60,
                content_hash=f"c{i}",
            )
        )
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        for a in rows:
            repo.upsert_article(a)

    out = tmp_path / "streamed.jsonl"
    count = export_articles_jsonl(tmp_db, out, batch_size=2)
    assert count == 10

    with Repository(tmp_db) as repo:
        ref_lines = []
        for a in repo.get_all_articles():
            ref_lines.append(json.dumps(a.model_dump(mode="json"), default=str) + "\n")
    assert out.read_text(encoding="utf-8") == "".join(ref_lines)

    with Repository(tmp_db) as repo:
        streamed = list(repo.iter_all_articles(batch_size=3))
    assert len(streamed) == 10
    assert [a.id for a in streamed] == [a.id for a in rows]


def test_iter_all_articles_matches_get_all_articles(tmp_db, sample_author, sample_article) -> None:
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(sample_article)
        all_a = repo.get_all_articles()
        iter_a = list(repo.iter_all_articles(batch_size=1))
    assert [a.model_dump(mode="json") for a in all_a] == [a.model_dump(mode="json") for a in iter_a]
