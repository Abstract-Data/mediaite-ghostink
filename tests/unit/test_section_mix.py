"""Unit tests for :mod:`forensics.analysis.section_mix` (Phase 15 J4)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from forensics.analysis.section_mix import (
    SectionMixSeries,
    compute_and_write_section_mix,
    compute_section_mix,
    section_mix_artifact_path,
    write_section_mix_artifact,
)


def _articles_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    """Build a deterministic articles DataFrame for the test."""
    return pl.DataFrame(rows)


def test_compute_section_mix_happy_path_three_months_two_sections() -> None:
    """One author across 3 months, 2 sections produces the expected dense matrix."""
    rows: list[dict[str, object]] = [
        # 2024-01: 2 media, 2 politics  → shares (0.5, 0.5)
        {"author_id": "auth-1", "timestamp": datetime(2024, 1, 5, tzinfo=UTC), "section": "media"},
        {"author_id": "auth-1", "timestamp": datetime(2024, 1, 12, tzinfo=UTC), "section": "media"},
        {
            "author_id": "auth-1",
            "timestamp": datetime(2024, 1, 18, tzinfo=UTC),
            "section": "politics",
        },
        {
            "author_id": "auth-1",
            "timestamp": datetime(2024, 1, 30, tzinfo=UTC),
            "section": "politics",
        },
        # 2024-02: 3 media, 1 politics  → shares (0.75, 0.25)
        {"author_id": "auth-1", "timestamp": datetime(2024, 2, 2, tzinfo=UTC), "section": "media"},
        {"author_id": "auth-1", "timestamp": datetime(2024, 2, 9, tzinfo=UTC), "section": "media"},
        {"author_id": "auth-1", "timestamp": datetime(2024, 2, 14, tzinfo=UTC), "section": "media"},
        {
            "author_id": "auth-1",
            "timestamp": datetime(2024, 2, 21, tzinfo=UTC),
            "section": "politics",
        },
        # 2024-03: 1 politics only      → shares (0.0, 1.0)
        {
            "author_id": "auth-1",
            "timestamp": datetime(2024, 3, 6, tzinfo=UTC),
            "section": "politics",
        },
    ]
    df = _articles_frame(rows)

    series = compute_section_mix("auth-1", df)

    assert series.author_id == "auth-1"
    assert series.months == ["2024-01", "2024-02", "2024-03"]
    assert series.sections == ["media", "politics"]
    assert series.shares == [
        [0.5, 0.5],
        [0.75, 0.25],
        [0.0, 1.0],
    ]
    for row in series.shares:
        assert sum(row) == pytest.approx(1.0)


def test_compute_section_mix_filters_to_requested_author() -> None:
    """Articles by other authors must not contribute to the requested author's matrix."""
    rows: list[dict[str, object]] = [
        {"author_id": "auth-1", "timestamp": datetime(2024, 1, 5, tzinfo=UTC), "section": "media"},
        {
            "author_id": "auth-2",
            "timestamp": datetime(2024, 1, 5, tzinfo=UTC),
            "section": "politics",
        },
        {
            "author_id": "auth-2",
            "timestamp": datetime(2024, 1, 6, tzinfo=UTC),
            "section": "opinion",
        },
    ]
    df = _articles_frame(rows)

    series = compute_section_mix("auth-1", df)
    assert series.sections == ["media"]
    assert series.shares == [[1.0]]


def test_compute_section_mix_single_section_only() -> None:
    """An author who only ever wrote in one section produces shape ``[[1.0]]``."""
    rows: list[dict[str, object]] = [
        {"author_id": "auth-1", "timestamp": datetime(2024, 5, 5, tzinfo=UTC), "section": "media"},
        {"author_id": "auth-1", "timestamp": datetime(2024, 5, 9, tzinfo=UTC), "section": "media"},
        {"author_id": "auth-1", "timestamp": datetime(2024, 5, 15, tzinfo=UTC), "section": "media"},
    ]
    df = _articles_frame(rows)

    series = compute_section_mix("auth-1", df)
    assert series.months == ["2024-05"]
    assert series.sections == ["media"]
    assert series.shares == [[1.0]]


def test_compute_section_mix_unique_months_only_no_zero_filling() -> None:
    """Months with no articles are not filled in (months list reflects observations).

    A month with zero articles for the author would only appear if some other
    column were grouped by it; since we group by ``(month, section)``, an
    author-month with no rows simply isn't in the output. This documents that
    contract — and shows that months that DO appear always have a non-zero
    sum (i.e., we never emit an all-zero row in the no-fill regime).
    """
    rows: list[dict[str, object]] = [
        {"author_id": "auth-1", "timestamp": datetime(2024, 1, 5, tzinfo=UTC), "section": "media"},
        # Skip 2024-02 entirely.
        {
            "author_id": "auth-1",
            "timestamp": datetime(2024, 3, 6, tzinfo=UTC),
            "section": "politics",
        },
    ]
    series = compute_section_mix("auth-1", _articles_frame(rows))
    # 2024-02 is absent — no zero-share row is emitted for it.
    assert series.months == ["2024-01", "2024-03"]
    for row in series.shares:
        assert sum(row) == pytest.approx(1.0)


def test_compute_section_mix_no_articles_returns_empty_series() -> None:
    """An author with zero articles in the frame produces an empty SectionMixSeries."""
    rows: list[dict[str, object]] = [
        {"author_id": "auth-2", "timestamp": datetime(2024, 1, 5, tzinfo=UTC), "section": "media"},
    ]
    series = compute_section_mix("auth-1", _articles_frame(rows))
    assert series == SectionMixSeries(
        author_id="auth-1",
        months=[],
        sections=[],
        shares=[],
    )


def test_compute_section_mix_derives_section_from_url_when_absent() -> None:
    """When ``section`` is missing the loader derives it from ``url`` (J1 fallback)."""
    rows: list[dict[str, object]] = [
        {
            "author_id": "auth-1",
            "timestamp": datetime(2024, 1, 5, tzinfo=UTC),
            "url": "https://www.mediaite.com/politics/some-headline/",
        },
        {
            "author_id": "auth-1",
            "timestamp": datetime(2024, 1, 9, tzinfo=UTC),
            "url": "https://www.mediaite.com/media/another-headline/",
        },
    ]
    df = _articles_frame(rows)

    series = compute_section_mix("auth-1", df)
    assert series.sections == ["media", "politics"]
    assert series.shares == [[0.5, 0.5]]


def test_compute_section_mix_accepts_lazyframe() -> None:
    """Passing a LazyFrame directly works and avoids materialising upstream."""
    rows: list[dict[str, object]] = [
        {"author_id": "auth-1", "timestamp": datetime(2024, 1, 5, tzinfo=UTC), "section": "media"},
    ]
    df = _articles_frame(rows).lazy()
    series = compute_section_mix("auth-1", df)
    assert series.shares == [[1.0]]


def test_compute_section_mix_drops_null_timestamps() -> None:
    """Rows with a null timestamp must not contribute to any month bucket."""
    df = pl.DataFrame(
        {
            "author_id": ["auth-1", "auth-1"],
            "timestamp": [datetime(2024, 1, 5, tzinfo=UTC), None],
            "section": ["media", "politics"],
        }
    )
    series = compute_section_mix("auth-1", df)
    assert series.months == ["2024-01"]
    assert series.sections == ["media"]


def test_compute_section_mix_missing_required_column_raises() -> None:
    """The function refuses inputs missing the contractual columns."""
    df = pl.DataFrame({"author_id": ["auth-1"]})
    with pytest.raises(ValueError, match="timestamp"):
        compute_section_mix("auth-1", df)


def test_write_section_mix_artifact_round_trip(tmp_path: Path) -> None:
    """Persisted JSON parses back to the original shape."""
    series = SectionMixSeries(
        author_id="auth-1",
        months=["2024-01", "2024-02"],
        sections=["media", "politics"],
        shares=[[0.5, 0.5], [0.75, 0.25]],
    )
    artifact_path = section_mix_artifact_path(tmp_path, "auth-1")
    write_section_mix_artifact(series, artifact_path)

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload == {
        "author_id": "auth-1",
        "months": ["2024-01", "2024-02"],
        "sections": ["media", "politics"],
        "shares": [[0.5, 0.5], [0.75, 0.25]],
    }


def test_write_section_mix_artifact_byte_stable_for_fixed_fixture(tmp_path: Path) -> None:
    """Regression-pin: serialised JSON bytes are stable for a fixed input fixture.

    Locks in (a) sort_keys=True at the top level, (b) the canonical key order,
    (c) chronological months, (d) alphabetical sections, and (e) trailing
    newline. Any change to the on-disk format will flip the SHA-256 below and
    must be made deliberately.
    """
    rows: list[dict[str, object]] = [
        {"author_id": "auth-1", "timestamp": datetime(2024, 1, 5, tzinfo=UTC), "section": "media"},
        {
            "author_id": "auth-1",
            "timestamp": datetime(2024, 2, 9, tzinfo=UTC),
            "section": "politics",
        },
        {"author_id": "auth-1", "timestamp": datetime(2024, 2, 12, tzinfo=UTC), "section": "media"},
    ]
    series = compute_section_mix("auth-1", _articles_frame(rows))

    artifact_path = section_mix_artifact_path(tmp_path, "auth-1")
    write_section_mix_artifact(series, artifact_path)

    written = artifact_path.read_bytes()
    expected_payload = {
        "author_id": "auth-1",
        "months": ["2024-01", "2024-02"],
        "sections": ["media", "politics"],
        "shares": [[1.0, 0.0], [0.5, 0.5]],
    }
    expected_text = json.dumps(expected_payload, indent=2, sort_keys=True) + "\n"
    assert written.decode("utf-8") == expected_text

    # Lock the byte hash so even a "harmless" indent or separator change is a test failure.
    digest = hashlib.sha256(written).hexdigest()
    expected_digest = hashlib.sha256(expected_text.encode("utf-8")).hexdigest()
    assert digest == expected_digest


def test_compute_and_write_section_mix_returns_series_and_path(tmp_path: Path) -> None:
    """The convenience wrapper computes, writes, and returns both pieces."""
    rows: list[dict[str, object]] = [
        {"author_id": "auth-1", "timestamp": datetime(2024, 1, 5, tzinfo=UTC), "section": "media"},
    ]
    series, path = compute_and_write_section_mix(
        "auth-1",
        "auth-one",
        _articles_frame(rows),
        tmp_path,
    )
    assert path == tmp_path / "auth-one_section_mix.json"
    assert path.is_file()
    assert series.shares == [[1.0]]
