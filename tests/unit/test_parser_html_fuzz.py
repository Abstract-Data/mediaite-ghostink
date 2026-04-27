"""T-06 — adversarial HTML inputs for article extract must not raise."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from forensics.scraper.parser import extract_article_text, extract_article_text_from_rest
from forensics.utils.text import word_count


@settings(max_examples=60, deadline=None)
@given(payload=st.binary(min_size=0, max_size=4096))
def test_extract_article_text_never_raises_on_binary_roundtrip(payload: bytes) -> None:
    html = payload.decode("utf-8", errors="replace")
    text = extract_article_text(html)
    assert isinstance(text, str)
    assert word_count(text) >= 0


_SENTINEL = "GHOSTINK_FUZZ_SENTINEL"


@settings(max_examples=40, deadline=None)
@given(
    inner=st.text(
        alphabet=st.characters(min_codepoint=0, max_codepoint=255),
        max_size=800,
    ),
    wrap_sentinel=st.booleans(),
)
def test_extract_article_text_from_rest_never_raises(inner: str, wrap_sentinel: bool) -> None:
    core = f"{inner}{_SENTINEL}" if wrap_sentinel else inner
    html = f'<div class="entry-content">{core}</div>'
    text = extract_article_text_from_rest(html)
    assert isinstance(text, str)
    assert word_count(text) >= 0
    if wrap_sentinel:
        assert _SENTINEL in text
