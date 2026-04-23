"""Pin-test for the derived scalar-feature count (E1 / P3-MAINT-001)."""

from __future__ import annotations

from forensics.models.features import count_scalar_features
from forensics.survey.scoring import _TOTAL_SCALAR_FEATURES


def test_count_scalar_features_matches_canonical_breakdown() -> None:
    # Lexical(6) + Structural(9) + Readability(4) + Content(7) + Productivity(5) + POS(4) = 35
    assert count_scalar_features() == 35


def test_survey_scoring_uses_computed_constant() -> None:
    assert _TOTAL_SCALAR_FEATURES == count_scalar_features()
