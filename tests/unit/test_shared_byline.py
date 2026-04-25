"""Shared-byline classifier tests."""

from __future__ import annotations

from forensics.utils.byline import shared_byline_reason


def test_shared_byline_excludes_outlet_prefixed_slugs() -> None:
    assert shared_byline_reason("mediaite", "Mediaite", "mediaite.com") == "outlet_slug"
    assert (
        shared_byline_reason("mediaite-staff", "Mediaite Staff", "mediaite.com")
        == "outlet_prefixed_slug"
    )


def test_shared_byline_matches_shared_tokens() -> None:
    assert shared_byline_reason("the-daily-staff", "The Daily Staff", "mediaite.com")


def test_shared_byline_matches_multi_author_names() -> None:
    assert shared_byline_reason("jane-john", "Jane Doe and John Smith", "mediaite.com")
    assert shared_byline_reason("jane-john", "Jane Doe & John Smith", "mediaite.com")
    assert shared_byline_reason("jane-john", "Jane Doe, John Smith", "mediaite.com")


def test_shared_byline_does_not_match_individual_names() -> None:
    assert shared_byline_reason("brandon-morse", "Brandon Morse", "mediaite.com") is None
    assert shared_byline_reason("sarah-rumpf", "Sarah Rumpf", "mediaite.com") is None
    assert shared_byline_reason("isaac-schorr", "Isaac Schorr", "mediaite.com") is None
