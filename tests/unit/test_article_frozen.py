"""Unit tests for the frozen Article model (G2 / P1-ARCH-001)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from forensics.models.article import Article


def _article(**overrides: object) -> Article:
    defaults = dict(
        id="a-1",
        author_id="au-1",
        url="https://www.mediaite.com/p/",
        title="t",
        published_date=datetime(2026, 1, 1, tzinfo=UTC),
    )
    defaults.update(overrides)
    return Article(**defaults)


def test_article_is_frozen() -> None:
    art = _article()
    with pytest.raises(ValidationError):
        art.clean_text = "mutated"


def test_with_updates_returns_new_instance_without_mutation() -> None:
    original = _article(clean_text="one")
    updated = original.with_updates(clean_text="two", word_count=3)
    assert updated is not original
    assert original.clean_text == "one"
    assert updated.clean_text == "two"
    assert updated.word_count == 3


def test_with_updates_preserves_unchanged_fields() -> None:
    original = _article(raw_html_path="raw/2024/x.html", metadata={"k": "v"})
    updated = original.with_updates(clean_text="body")
    assert updated.raw_html_path == "raw/2024/x.html"
    assert updated.metadata == {"k": "v"}


def test_metadata_is_deep_copied_on_construction() -> None:
    """Mutating the caller's source dict must not leak into the frozen model."""
    source = {"tags": ["a", "b"]}
    art = _article(metadata=source)
    source["tags"].append("c")
    source["extra"] = "injected"
    assert art.metadata == {"tags": ["a", "b"]}


def test_metadata_is_deep_copied_on_with_updates() -> None:
    """Two copies of one article must not share a mutable metadata reference."""
    original = _article(metadata={"tags": ["a"]})
    copy_a = original.with_updates(clean_text="one")
    copy_b = original.with_updates(clean_text="two")
    assert copy_a.metadata is not copy_b.metadata
    assert copy_a.metadata is not original.metadata
    # Mutating the nested list in one copy does not reach the others.
    copy_a.metadata["tags"].append("mutated")
    assert original.metadata == {"tags": ["a"]}
    assert copy_b.metadata == {"tags": ["a"]}
