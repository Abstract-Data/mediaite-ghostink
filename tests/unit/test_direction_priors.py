"""Unit tests for :mod:`forensics.models.direction_priors`.

Includes an audit that every key in :data:`AI_TYPICAL_DIRECTION` is either
(1) a column name that participates in PELT / hypothesis-test outputs, or
(2) explicitly allowlisted with a short justification (pre-registration
review may promote or drop those keys).
"""

from __future__ import annotations

import math

import pytest

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS
from forensics.models.direction_priors import (
    AI_TYPICAL_DIRECTION,
    direction_from_d,
)

# Keys in the priors registry that are not (yet) emitted as ``feature_name``
# in analysis JSON. Adding a new key here requires a one-line rationale.
_AUDIT_ALLOWLIST: dict[str, str] = {
    # Prompt v0.1.0 composite / glossary label; Parquet + PELT use ttr/mattr/etc.
    # If the pipeline ever emits ``lexical_diversity`` as a test feature, the
    # prior applies without further code changes.
    "lexical_diversity": (
        "Not in PELT_FEATURE_COLUMNS; reserved label from Phase 17 prompt — "
        "review at pre-reg lock or map to concrete columns."
    ),
}


def test_direction_from_d_none_and_nan() -> None:
    assert direction_from_d(None) is None
    assert direction_from_d(float("nan")) is None


def test_direction_from_d_signs_and_zero() -> None:
    assert direction_from_d(1.0) == "increase"
    assert direction_from_d(-0.5) == "decrease"
    assert direction_from_d(0.0) is None


def test_direction_from_d_non_float_rejected() -> None:
    assert direction_from_d("1.0") is None  # type: ignore[arg-type]


def test_hedging_frequency_prior_is_none_by_design() -> None:
    assert AI_TYPICAL_DIRECTION["hedging_frequency"] is None


def test_ai_typical_direction_keys_are_audited() -> None:
    """Every registry key must map to a real PELT axis or an explicit allowlist."""
    pelt = frozenset(PELT_FEATURE_COLUMNS)
    allow = frozenset(_AUDIT_ALLOWLIST)
    for key in AI_TYPICAL_DIRECTION:
        assert key in pelt or key in allow, (
            f"Unknown prior key {key!r}: add to PELT_FEATURE_COLUMNS pipeline, "
            f"or document in _AUDIT_ALLOWLIST with rationale."
        )


def test_audit_allowlist_entries_are_non_empty_rationale() -> None:
    for name, rationale in _AUDIT_ALLOWLIST.items():
        assert name.strip()
        assert len(rationale.strip()) >= 20


@pytest.mark.parametrize(
    ("cohens_d", "expected"),
    [
        (1e-300, "increase"),
        (-1e-300, "decrease"),
        (math.inf, "increase"),
        (-math.inf, "decrease"),
    ],
)
def test_direction_from_d_extreme_floats(cohens_d: float, expected: str) -> None:
    assert direction_from_d(cohens_d) == expected
