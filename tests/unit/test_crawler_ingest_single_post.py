"""Unit tests for ``_ingest_single_post`` (C1 extraction)."""

from __future__ import annotations

from forensics.scraper.crawler import _ingest_single_post


def _wp_post(
    *,
    post_id: int = 12345,
    slug: str = "test-slug",
    link: str = "https://www.mediaite.com/news/test-article/",
    title: str = "Test Title",
    date: str = "2024-06-15T12:00:00",
    modified: str | None = "2024-06-16T09:00:00",
    content: str | None = None,
) -> dict[str, object]:
    post: dict[str, object] = {
        "id": post_id,
        "slug": slug,
        "link": link,
        "title": {"rendered": title},
        "date": date,
    }
    if modified is not None:
        post["modified"] = modified
    if content is not None:
        post["content"] = {"rendered": content}
    return post


def test_ingest_single_post_rejects_non_dict() -> None:
    assert _ingest_single_post("not a dict", "author-123") is None
    assert _ingest_single_post(None, "author-123") is None
    assert _ingest_single_post(42, "author-123") is None
    assert _ingest_single_post([{"a": 1}], "author-123") is None


def test_ingest_single_post_parses_metadata_only_row() -> None:
    post = _wp_post()
    article = _ingest_single_post(post, "author-123")
    assert article is not None
    assert article.author_id == "author-123"
    assert str(article.url) == "https://www.mediaite.com/news/test-article/"
    assert article.title == "Test Title"
    assert article.clean_text == ""
    assert article.word_count == 0
    assert article.content_hash == ""
    assert article.scraped_at is None


def test_ingest_single_post_parses_content_when_provided() -> None:
    post = _wp_post(content="<p>Hello world, this is a test article body.</p>")
    article = _ingest_single_post(post, "author-123")
    assert article is not None
    assert "Hello world" in article.clean_text
    assert article.word_count > 0
    assert article.content_hash  # non-empty
    assert article.scraped_at is not None


def test_ingest_single_post_unescapes_html_entities_in_title() -> None:
    post = _wp_post(title="Trump &amp; Biden debate")
    article = _ingest_single_post(post, "author-123")
    assert article is not None
    assert article.title == "Trump & Biden debate"


def test_ingest_single_post_handles_missing_modified() -> None:
    post = _wp_post(modified=None)
    article = _ingest_single_post(post, "author-123")
    assert article is not None
    assert article.modified_date is None


def test_ingest_single_post_returns_none_for_missing_required_field() -> None:
    # link missing → _wp_post_to_article raises KeyError; helper must swallow.
    bad = {
        "id": 1,
        "title": {"rendered": "no link"},
        "date": "2024-01-01T00:00:00",
    }
    assert _ingest_single_post(bad, "author-123") is None


def test_ingest_single_post_returns_none_for_bad_title_shape() -> None:
    # title is a string instead of the expected {"rendered": ...} dict.
    bad = {
        "id": 2,
        "link": "https://www.mediaite.com/x/",
        "title": "Unwrapped title",
        "date": "2024-01-01T00:00:00",
    }
    assert _ingest_single_post(bad, "author-123") is None


def test_ingest_single_post_returns_none_for_unparseable_date() -> None:
    bad = _wp_post(date="not-a-date")
    assert _ingest_single_post(bad, "author-123") is None
