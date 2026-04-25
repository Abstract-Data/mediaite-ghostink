"""Unit tests for the Phase 15 J6 per-author section-contrast diagnostic.

Coverage targets (per H1 spec, ≥ 3 tests):

* happy path — synthetic two-section author with a clear feature shift
  produces a non-empty ``significant_features_by_family`` dict for the
  single qualifying pair.
* edge case — fewer than two sections meeting the article bar yields
  ``disposition: "insufficient_section_volume"`` and an empty ``pairs``
  list (no exception).
* edge case — when every feature passes BH the module emits a WARNING
  ("wholly different registers" sanity check).
* edge case — single qualifying pair (only two sections) is handled
  without crashing and contains the expected pair entry.
* artifact write-out — JSON lands on disk and round-trips through
  ``json.loads`` to the expected schema.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS
from forensics.analysis.section_contrast import (
    MIN_SECTION_ARTICLES,
    SectionContrastResult,
    compute_and_write_section_contrast,
    compute_section_contrast,
    section_contrast_artifact_path,
)


def _make_author_frame(
    *,
    sections: dict[str, dict[str, object]],
    seed: int = 1234,
) -> pl.DataFrame:
    """Build a synthetic per-author feature frame for J6 tests.

    Each section spec is ``{"n": int, "shifts": {feature: mean}}``. Features
    are drawn from ``Normal(mean, 0.05)`` so within-section variance is
    small relative to between-section shifts — Welch + MW will reject the
    null cleanly on small fixtures.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for section, spec in sections.items():
        n = int(spec["n"])  # type: ignore[arg-type]
        shifts: dict[str, float] = dict(spec.get("shifts", {}))  # type: ignore[arg-type]
        for i in range(n):
            row: dict[str, object] = {
                "author_id": "author-1",
                "section": section,
                "url": f"https://www.mediaite.com/{section}/article-{i}/",
            }
            for feature in PELT_FEATURE_COLUMNS:
                base = shifts.get(feature, 0.0)
                row[feature] = float(base + rng.normal(0.0, 0.05))
            rows.append(row)
    return pl.DataFrame(rows)


def test_happy_path_two_distinct_sections_produces_significant_pair() -> None:
    """Two clearly-different sections → one pair with significant features by family."""
    df = _make_author_frame(
        sections={
            "opinion": {
                "n": 60,
                "shifts": {
                    "first_person_ratio": 1.5,
                    "hedging_frequency": 1.5,
                    "flesch_kincaid": 1.5,
                },
            },
            "politics": {
                "n": 60,
                "shifts": {
                    "first_person_ratio": -1.5,
                    "hedging_frequency": -1.5,
                    "flesch_kincaid": -1.5,
                },
            },
        },
        seed=42,
    )
    result = compute_section_contrast(df, author_id="author-1")
    assert result.disposition == "ok"
    assert len(result.pairs) == 1
    pair = result.pairs[0]
    assert pair.section_a == "opinion"
    assert pair.section_b == "politics"
    assert pair.n_a == 60
    assert pair.n_b == 60
    # Phase 15 B-followup (issue #5): ``first_person_ratio`` was folded into
    # ``ai_markers`` to remove the convergence-ratio ceiling, so both
    # voice-style and hedging features now surface under the same family.
    assert "ai_markers" in pair.significant_features_by_family
    assert "first_person_ratio" in pair.significant_features_by_family["ai_markers"]
    assert "hedging_frequency" in pair.significant_features_by_family["ai_markers"]
    assert "readability" in pair.significant_features_by_family
    assert "flesch_kincaid" in pair.significant_features_by_family["readability"]


def test_insufficient_section_volume_yields_disposition_marker() -> None:
    """One section above the bar → no pairs, ``insufficient_section_volume`` disposition."""
    df = _make_author_frame(
        sections={
            "opinion": {"n": MIN_SECTION_ARTICLES + 5, "shifts": {}},
            # Politics is below the per-section minimum so the pair isn't formed.
            "politics": {"n": MIN_SECTION_ARTICLES - 5, "shifts": {}},
        },
        seed=7,
    )
    result = compute_section_contrast(df, author_id="author-1")
    assert result.pairs == []
    assert result.disposition == "insufficient_section_volume"


def test_no_qualifying_sections_yields_disposition_marker() -> None:
    """Empty / single-section frame → ``insufficient_section_volume`` (no crash)."""
    df = _make_author_frame(
        sections={"opinion": {"n": MIN_SECTION_ARTICLES + 1, "shifts": {}}},
        seed=11,
    )
    result = compute_section_contrast(df, author_id="author-1")
    assert result.disposition == "insufficient_section_volume"
    assert result.pairs == []


def test_all_features_pass_emits_warning(caplog: pytest.LogCaptureFixture) -> None:
    """All-features-pass pair triggers the documented WARNING."""
    huge_shifts = {
        feature: 5.0 * (1 if i % 2 == 0 else -1) for i, feature in enumerate(PELT_FEATURE_COLUMNS)
    }
    inv_shifts = {feature: -shift for feature, shift in huge_shifts.items()}
    df = _make_author_frame(
        sections={
            "opinion": {"n": 60, "shifts": huge_shifts},
            "politics": {"n": 60, "shifts": inv_shifts},
        },
        seed=3,
    )
    with caplog.at_level(logging.WARNING, logger="forensics.analysis.section_contrast"):
        result = compute_section_contrast(df, author_id="author-1")
    pair = result.pairs[0]
    n_sig = sum(len(features) for features in pair.significant_features_by_family.values())
    # Sanity: every feature really did pass.
    assert n_sig == len(PELT_FEATURE_COLUMNS)
    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert any(
        "section_contrast" in rec.message and "spot-check" in rec.message for rec in warnings
    ), "Expected the all-features-pass spot-check WARNING."


def test_artifact_round_trips_through_json(tmp_path: Path) -> None:
    """JSON artifact lands on disk with the documented schema."""
    df = _make_author_frame(
        sections={
            "opinion": {"n": 50, "shifts": {"first_person_ratio": 1.5}},
            "politics": {"n": 50, "shifts": {"first_person_ratio": -1.5}},
        },
        seed=2026,
    )
    result, path = compute_and_write_section_contrast(
        df,
        author_id="author-1",
        author_slug="author-one",
        analysis_dir=tmp_path,
    )
    assert path == section_contrast_artifact_path(tmp_path, "author-one")
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["author_id"] == "author-1"
    assert payload["disposition"] == "ok"
    assert isinstance(payload["pairs"], list) and len(payload["pairs"]) == 1
    pair = payload["pairs"][0]
    assert set(pair.keys()) == {
        "section_a",
        "section_b",
        "n_a",
        "n_b",
        "significant_features_by_family",
    }
    assert pair["section_a"] == "opinion"
    assert pair["section_b"] == "politics"
    assert isinstance(pair["significant_features_by_family"], dict)
    assert isinstance(result, SectionContrastResult)


def test_three_qualifying_sections_emit_three_pairs() -> None:
    """Three qualifying sections produce all C(3,2)=3 pairs in deterministic order."""
    df = _make_author_frame(
        sections={
            "opinion": {"n": 40, "shifts": {"first_person_ratio": 1.5}},
            "politics": {"n": 40, "shifts": {"first_person_ratio": -1.5}},
            "media": {"n": 40, "shifts": {"first_person_ratio": 0.0}},
        },
        seed=99,
    )
    result = compute_section_contrast(df, author_id="author-1")
    assert result.disposition == "ok"
    pair_keys = [(p.section_a, p.section_b) for p in result.pairs]
    # ``itertools.combinations`` over the alphabetically-sorted qualifying sections
    # yields ('media', 'opinion'), ('media', 'politics'), ('opinion', 'politics').
    assert pair_keys == [
        ("media", "opinion"),
        ("media", "politics"),
        ("opinion", "politics"),
    ]
