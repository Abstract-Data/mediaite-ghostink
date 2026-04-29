"""Property tests: REST ``content.rendered`` shaped strings must not raise."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from forensics.scraper.parser import extract_article_text_from_rest


@settings(max_examples=50, deadline=None)
@given(payload=st.binary(min_size=0, max_size=4096))
def test_extract_article_text_from_rest_never_raises_on_binary_roundtrip(payload: bytes) -> None:
    rendered = payload.decode("utf-8", errors="replace")
    text = extract_article_text_from_rest(rendered)
    assert isinstance(text, str)
    # Idempotent under a second parse (no hidden state; stable normalization path).
    assert extract_article_text_from_rest(text) == text
    # Parser output is plain text: no HTML brackets from this extractor path.
    assert "<" not in text and ">" not in text


@settings(max_examples=40, deadline=None)
@given(
    inner=st.text(
        alphabet=st.characters(
            min_codepoint=1,
            max_codepoint=255,
            blacklist_characters="<>\"'&",
        ),
        max_size=800,
    ),
)
def test_extract_article_text_from_rest_never_raises_on_plain_text(inner: str) -> None:
    text = extract_article_text_from_rest(inner)
    assert isinstance(text, str)
    assert extract_article_text_from_rest(text) == text


@settings(max_examples=30, deadline=None)
@given(
    inner=st.text(
        alphabet=st.characters(
            min_codepoint=1,
            max_codepoint=255,
            blacklist_characters="<>\"'&",
        ),
        max_size=400,
    ),
    wrap_sentinel=st.booleans(),
)
def test_extract_article_text_from_rest_sentinel_preserved(inner: str, wrap_sentinel: bool) -> None:
    sentinel = "GHOSTINK_FUZZ_SENTINEL"
    core = f"{inner}{sentinel}" if wrap_sentinel else inner
    html = f'<div class="entry-content">{core}</div>'
    text = extract_article_text_from_rest(html)
    assert isinstance(text, str)
    if wrap_sentinel:
        assert sentinel in text
