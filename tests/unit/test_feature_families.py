"""Tests for the Phase 15 B1 feature-family registry."""

from __future__ import annotations

from datetime import date

from forensics.analysis.feature_families import (
    FAMILY_COUNT,
    FEATURE_FAMILIES,
    family_for,
)
from forensics.models.analysis import ConvergenceWindow


def test_feature_families_covers_all_pelt_columns() -> None:
    """Importing the module triggers ``_assert_coverage`` — no exception means pass."""
    # Re-exercise the invariant explicitly to guard against future edits.
    from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS

    assert set(FEATURE_FAMILIES) == set(PELT_FEATURE_COLUMNS)


def test_family_count_matches_spec() -> None:
    assert FAMILY_COUNT == 8


def test_family_for_unknown_feature() -> None:
    assert family_for("does_not_exist") == "unknown"


def test_family_for_known_feature() -> None:
    assert family_for("ttr") == "lexical_richness"
    assert family_for("flesch_kincaid") == "readability"
    assert family_for("first_person_ratio") == "voice"


def test_convergence_window_accepts_families_converging() -> None:
    window = ConvergenceWindow(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        features_converging=["ttr", "flesch_kincaid"],
        families_converging=["readability", "voice"],
        convergence_ratio=0.5,
        pipeline_a_score=0.7,
        pipeline_b_score=0.6,
    )
    dumped = window.model_dump()
    assert dumped["families_converging"] == ["readability", "voice"]

    restored = ConvergenceWindow.model_validate(dumped)
    assert restored.families_converging == ["readability", "voice"]


def test_convergence_window_defaults_families_to_empty_list() -> None:
    """Backwards compat: persisted JSON without ``families_converging`` must round-trip."""
    legacy_payload = {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "features_converging": ["ttr"],
        "convergence_ratio": 0.25,
        "pipeline_a_score": 0.5,
        "pipeline_b_score": 0.5,
    }
    window = ConvergenceWindow.model_validate(legacy_payload)
    assert window.families_converging == []
