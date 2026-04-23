"""Phase 2 scraper unit tests (no live HTTP)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import httpx
import pytest
from pydantic import ValidationError

from forensics.config.settings import ScrapingConfig
from forensics.models.article import Article
from forensics.models.author import AuthorManifest
from forensics.scraper.crawler import (
    _author_config_from_manifest,
    _int_header,
    _iter_manifests_from_users_json,
    _load_authors_manifest,
    _stable_author_id,
    _user_dict_to_manifest,
    _wp_post_to_article,
    posts_year_query_fragment,
    resolve_posts_year_window,
    stable_article_id,
)
from forensics.scraper.dedup import deduplicate_articles
from forensics.scraper.fetcher import (
    RateLimiter,
    _is_mediaite_host,
    _write_raw_html_file,
    request_with_retry,
)
from forensics.scraper.parser import extract_article_text, extract_metadata, looks_coauthored
from forensics.storage.repository import Repository
from forensics.utils.datetime import parse_wp_datetime
from forensics.utils.hashing import simhash, simhash_hamming
from forensics.utils.text import word_count


def test_stable_author_id_deterministic() -> None:
    assert _stable_author_id("jane-doe") == _stable_author_id("jane-doe")
    assert _stable_author_id("a") != _stable_author_id("b")


def test_parse_wp_datetime_naive_becomes_utc() -> None:
    dt = parse_wp_datetime("2024-06-01T12:30:00")
    assert dt.tzinfo == UTC


def test_parse_wp_datetime_z_suffix() -> None:
    dt = parse_wp_datetime("2024-06-01T12:30:00Z")
    assert dt.year == 2024


def test_user_dict_to_manifest() -> None:
    user = {"id": 42, "name": "Test User", "slug": "test-user"}
    when = datetime(2025, 1, 2, tzinfo=UTC)
    m = _user_dict_to_manifest(user, total_posts=7, discovered_at=when)
    assert m.wp_id == 42
    assert m.slug == "test-user"
    assert m.total_posts == 7
    assert m.discovered_at == when


def test_author_config_from_manifest() -> None:
    when = datetime(2025, 1, 2, tzinfo=UTC)
    m = AuthorManifest(
        wp_id=9,
        name="Pat Example",
        slug="pat-example",
        total_posts=12,
        discovered_at=when,
    )
    cfg = _author_config_from_manifest(m)
    assert cfg.name == "Pat Example"
    assert cfg.slug == "pat-example"
    assert cfg.outlet == "mediaite.com"
    assert cfg.role == "target"
    assert cfg.archive_url == "https://www.mediaite.com/author/pat-example/"


def test_iter_manifests_from_users_json() -> None:
    users = [
        {"id": 1, "name": "A", "slug": "a"},
        {"id": 2, "name": "B", "slug": "b"},
    ]
    counts = {1: 10, 2: 3}
    rows = list(_iter_manifests_from_users_json(users, total_posts_by_id=counts))
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
    art = _wp_post_to_article(post, sample_author.id)
    assert art.author_id == sample_author.id
    assert "Hello & goodbye" in art.title
    assert art.word_count == 0
    assert art.clean_text == ""
    assert art.metadata == {}
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
    loaded = _load_authors_manifest(path)
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
    assert looks_coauthored("Alice & Bob")
    assert looks_coauthored("Alice with Bob")
    assert looks_coauthored("Alice, Bob")
    assert looks_coauthored("Alice AND Bob")
    assert not looks_coauthored("Alice Smith")
    assert not looks_coauthored("")
    assert not looks_coauthored("   ")


def test_mediaite_host_detection() -> None:
    assert _is_mediaite_host("www.mediaite.com")
    assert _is_mediaite_host("mediaite.com")
    assert not _is_mediaite_host("lawandcrime.com")


@pytest.mark.parametrize(
    "bad_id",
    ["../evil", "a/b", "..\\evil", "x\\y", "foo/../bar", ".."],
)
def test_write_raw_html_file_rejects_unsafe_article_id(tmp_path: Path, bad_id: str) -> None:
    """Defense-in-depth: reject any article_id that could escape data/raw/{year}/."""
    with pytest.raises(ValueError, match="unsafe article_id"):
        _write_raw_html_file(tmp_path, 2025, bad_id, "<html/>")
    # and nothing was written anywhere under data/raw/
    assert not (tmp_path / "data").exists() or not any(
        p.is_file() for p in (tmp_path / "data").rglob("*")
    )


def test_write_raw_html_file_accepts_uuid_id(tmp_path: Path) -> None:
    """Baseline: a normal UUID5-shaped id writes exactly one file under data/raw/{year}/."""
    rel = _write_raw_html_file(
        tmp_path,
        2025,
        "0c1e8c0e-1234-5abc-8def-0123456789ab",
        "<html>ok</html>",
    )
    assert rel == "raw/2025/0c1e8c0e-1234-5abc-8def-0123456789ab.html"
    out = tmp_path / "data" / "raw" / "2025" / "0c1e8c0e-1234-5abc-8def-0123456789ab.html"
    assert out.is_file()
    assert out.read_text(encoding="utf-8") == "<html>ok</html>"


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


def test_posts_year_query_fragment_uses_wp_after_before_bounds() -> None:
    frag = posts_year_query_fragment(2019, 2025)
    assert "&after=" in frag
    assert "&before=" in frag
    assert "2019-01-01T00%3A00%3A00Z" in frag
    assert "2026-01-01T00%3A00%3A00Z" in frag


def test_resolve_posts_year_window_unset() -> None:
    s = ScrapingConfig()
    assert resolve_posts_year_window(s) is None


def test_resolve_posts_year_window_from_config() -> None:
    s = ScrapingConfig(post_year_min=2020, post_year_max=2022)
    assert resolve_posts_year_window(s) == (2020, 2022)


def test_resolve_posts_year_window_cli_overrides_config() -> None:
    s = ScrapingConfig(post_year_min=2010, post_year_max=2015)
    assert resolve_posts_year_window(s, override_min=2019, override_max=2021) == (2019, 2021)


def test_resolve_posts_year_window_partial_override_raises() -> None:
    s = ScrapingConfig()
    with pytest.raises(ValueError, match="both min and max"):
        resolve_posts_year_window(s, override_min=2020, override_max=None)


def test_resolve_posts_year_window_inverted_raises() -> None:
    s = ScrapingConfig()
    with pytest.raises(ValueError, match="max must be >="):
        resolve_posts_year_window(s, override_min=2022, override_max=2020)


def test_scraping_config_post_year_requires_both() -> None:
    with pytest.raises(ValidationError):
        ScrapingConfig(post_year_min=2020)


def test_stable_article_id_upsert_same_url(tmp_db, sample_author) -> None:
    post = {
        "id": 1,
        "link": "https://www.mediaite.com/2024/01/02/x/",
        "title": {"rendered": "T"},
        "date": "2024-01-02T00:00:00",
    }
    a1 = _wp_post_to_article(post, sample_author.id)
    a2 = _wp_post_to_article(post, sample_author.id)
    assert a1.id == a2.id == stable_article_id(str(post["link"]))
    with Repository(tmp_db) as repo:
        repo.upsert_author(sample_author)
        repo.upsert_article(a1)
        repo.upsert_article(a2)
        assert len(repo.get_all_articles()) == 1
