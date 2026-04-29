"""Property tests: REST ``content.rendered`` shaped strings must not raise."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from forensics.scraper.parser import extract_article_text_from_rest
from forensics.utils.text import word_count


@settings(max_examples=50, deadline=None)
@given(payload=st.binary(min_size=0, max_size=4096))
def test_extract_article_text_from_rest_never_raises_on_binary_roundtrip(payload: bytes) -> None:
    rendered = payload.decode("utf-8", errors="replace")
    text = extract_article_text_from_rest(rendered)
    assert isinstance(text, str)
    assert word_count(text) >= 0


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
    assert word_count(text) >= 0
