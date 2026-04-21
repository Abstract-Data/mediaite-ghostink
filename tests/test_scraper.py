"""Phase 2 scraper unit tests (no live HTTP)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import httpx
import pytest

from forensics.config.settings import ScrapingConfig
from forensics.models.article import Article
from forensics.models.author import AuthorManifest
from forensics.scraper.crawler import (
    _int_header,
    iter_manifests_from_users_json,
    load_authors_manifest,
    stable_article_id,
    stable_author_id,
    user_dict_to_manifest,
    wp_post_to_article,
)
from forensics.scraper.dedup import deduplicate_articles
from forensics.scraper.fetcher import RateLimiter, _is_mediaite_host, request_with_retry
from forensics.scraper.parser import extract_article_text, extract_metadata, looks_coauthored
from forensics.storage.repository import Repository
from forensics.utils.datetime import parse_wp_datetime
from forensics.utils.hashing import simhash, simhash_hamming
from forensics.utils.text import word_count


def test_stable_author_id_deterministic() -> None:
    assert stable_author_id("jane-doe") == stable_author_id("jane-doe")
    assert stable_author_id("a") != stable_author_id("b")


def test_parse_wp_datetime_naive_becomes_utc() -> None:
    dt = parse_wp_datetime("2024-06-01T12:30:00")
    assert dt.tzinfo == UTC


def test_parse_wp_datetime_z_suffix() -> None:
    dt = parse_wp_datetime("2024-06-01T12:30:00Z")
    assert dt.year == 2024


def test_user_dict_to_manifest() -> None:
    user = {"id": 42, "name": "Test User", "slug": "test-user"}
    when = datetime(2025, 1, 2, tzinfo=UTC)
    m = user_dict_to_manifest(user, total_posts=7, discovered_at=when)
    assert m.wp_id == 42
    assert m.slug == "test-user"
    assert m.total_posts == 7
    assert m.discovered_at == when


def test_iter_manifests_from_users_json() -> None:
    users = [
        {"id": 1, "name": "A", "slug": "a"},
        {"id": 2, "name": "B", "slug": "b"},
    ]
    counts = {1: 10, 2: 3}
    rows = list(iter_manifests_from_users_json(users, total_posts_by_id=counts))
    assert {r.slug for r in rows} == {"a", "b"}
    assert next(r for r in rows if r.slug == "a").total_posts == 10


def test_wp_post_to_article(sample_author) -> None:
    post = {
        "id": 99,
        "link": "https://www.mediaite.com/2024/01/02/sample/",
        "title": {"rendered": "Hello &amp; goodbye"},
        "date": "2024-01-02T15:00:00",
        "modified": "2024-01-03T10:00:00",
        "meta": {"_edit_last": "7"},
    }
    art = wp_post_to_article(post, sample_author.id)
    assert art.author_id == sample_author.id
    assert "Hello & goodbye" in art.title
    assert art.word_count == 0
    assert art.clean_text == ""
    assert art.metadata.get("wp_post_id") == 99
    assert str(art.url).rstrip("/") == "https://www.mediaite.com/2024/01/02/sample"
    assert art.modified_date is not None
    assert art.modified_date.year == 2024
    assert art.modifier_user_id == 7


def test_int_header_parsing() -> None:
    r = httpx.Response(200, headers={"X-WP-TotalPages": "4", "X-WP-Total": "120"})
    assert _int_header(r, "X-WP-TotalPages", 1) == 4
    assert _int_header(r, "X-WP-Total", 0) == 120
    assert _int_header(httpx.Response(200), "X-WP-TotalPages", 7) == 7


def test_load_authors_manifest_roundtrip(tmp_path) -> None:
    path = tmp_path / "manifest.jsonl"
    m = AuthorManifest(
        wp_id=1,
        name="N",
        slug="s",
        total_posts=2,
        discovered_at=datetime.now(UTC),
    )
    path.write_text(m.model_dump_json() + "\n", encoding="utf-8")
    loaded = load_authors_manifest(path)
    assert loaded["s"].wp_id == 1


@pytest.mark.asyncio
async def test_rate_limiter_enforces_gap() -> None:
    limiter = RateLimiter(0.06, 0.0)
    await limiter.wait()
    t0 = time.monotonic()
    await limiter.wait()
    assert time.monotonic() - t0 >= 0.055


@pytest.mark.asyncio
async def test_retry_on_5xx_then_success(tmp_path: Path) -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 2:
            return httpx.Response(500, text="no")
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    scraping = ScrapingConfig(
        rate_limit_seconds=0.0,
        rate_limit_jitter=0.0,
        max_retries=4,
        retry_backoff_seconds=0.01,
    )
    limiter = RateLimiter(0.0, 0.0)
    errors_path = tmp_path / "scrape_errors.jsonl"

    async with httpx.AsyncClient(transport=transport) as client:
        patcher = mock.patch(
            "forensics.scraper.fetcher.append_scrape_error",
            new_callable=mock.AsyncMock,
        )
        with patcher:
            resp = await request_with_retry(
                client,
                limiter,
                scraping,
                "GET",
                "https://example.test/x",
                errors_path=errors_path,
                phase="test",
            )
    assert resp.status_code == 200
    assert attempts["n"] == 2


def test_article_url_exists_and_duplicate_skip(tmp_db, sample_author, sample_article) -> None:
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        assert not repo.article_url_exists(str(sample_article.url))
        repo.upsert_article(sample_article)
        assert repo.article_url_exists(str(sample_article.url))
        arts = repo.get_all_articles()
    assert len(arts) == 1


def test_extract_article_text_fixture() -> None:
    path = Path(__file__).parent / "fixtures/sample_mediaite_article.html"
    html = path.read_text(encoding="utf-8")
    text = extract_article_text(html)
    assert "opening paragraph" in text
    assert "Related noise" not in text
    assert "Skip this navigation" not in text


def test_content_validation_short_article_word_count() -> None:
    path = Path(__file__).parent / "fixtures/sample_mediaite_short.html"
    html = path.read_text(encoding="utf-8")
    text = extract_article_text(html)
    assert word_count(text) < 50


def test_extract_metadata_fixture() -> None:
    path = Path(__file__).parent / "fixtures/sample_mediaite_article.html"
    html = path.read_text(encoding="utf-8")
    meta = extract_metadata(html)
    assert meta.get("og_section") == "Politics"
    assert "Breaking" in (meta.get("article_tags") or [])


def test_looks_coauthored() -> None:
    assert looks_coauthored("Alice and Bob")
    assert not looks_coauthored("Alice Smith")


def test_mediaite_host_detection() -> None:
    assert _is_mediaite_host("www.mediaite.com")
    assert _is_mediaite_host("mediaite.com")
    assert not _is_mediaite_host("lawandcrime.com")


def test_simhash_near_duplicate_distance() -> None:
    a = "the quick brown fox jumps over the lazy dog " * 20
    b = a[: len(a) // 2] + "X" + a[len(a) // 2 + 1 :]
    assert simhash_hamming(simhash(a), simhash(b)) <= 3


def test_simhash_distinct_texts() -> None:
    a = "quantum chromodynamics and lattice gauge theory " * 6
    b = "recipes for sourdough bread and pastry techniques " * 6
    assert simhash_hamming(simhash(a), simhash(b)) > 3


def test_list_unfetched_resumability(tmp_db, sample_author, sample_article) -> None:
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(sample_article)
        assert len(repo.list_unfetched_for_fetch()) == 1
        filled = sample_article.model_copy(
            update={"clean_text": "fetched body text here", "word_count": 4, "content_hash": "abc"}
        )
        repo.upsert_article(filled)
        assert repo.list_unfetched_for_fetch() == []


def test_deduplicate_articles_marks_second(tmp_db, sample_author) -> None:
    body = "national politics coverage continues with detailed reporting " * 30

    u1 = "https://www.mediaite.com/2020/01/01/a/"
    u2 = "https://www.mediaite.com/2020/01/02/b/"
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
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(a1)
        repo.upsert_article(a2)
    dup_ids = deduplicate_articles(tmp_db)
    assert len(dup_ids) == 1
    with Repository(tmp_db) as repo:
        arts = {a.id: a for a in repo.get_all_articles()}
    assert arts[a1.id].is_duplicate is False
    assert arts[a2.id].is_duplicate is True


def test_stable_article_id_upsert_same_url(tmp_db, sample_author) -> None:
    post = {
        "id": 1,
        "link": "https://www.mediaite.com/2024/01/02/x/",
        "title": {"rendered": "T"},
        "date": "2024-01-02T00:00:00",
    }
    a1 = wp_post_to_article(post, sample_author.id)
    a2 = wp_post_to_article(post, sample_author.id)
    assert a1.id == a2.id == stable_article_id(str(post["link"]))
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(a1)
        repo.upsert_article(a2)
        assert len(repo.get_all_articles()) == 1
