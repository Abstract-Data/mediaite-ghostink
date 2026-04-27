"""Phase 17 golden tests: direction concordance + volume ramp + strength on fixtures.

Committed JSON under ``tests/fixtures/phase17/`` avoids depending on gitignored
``data/analysis/*_result.json`` in CI. To refresh expectations after a full
local analyze, recompute window-scoped rows for each slug and update
``golden_cases.json`` together with this module's assertions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from forensics.models.analysis import ConvergenceWindow, HypothesisTest
from forensics.models.report import (
    DirectionConcordance,
    FindingStrength,
    VolumeRampFlag,
    classify_direction_concordance,
    classify_finding_strength,
    compute_volume_ramp_flag,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "phase17" / "golden_cases.json"
)


def _load_cases() -> list[dict[str, Any]]:
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return list(raw["cases"])


def _parse_window(payload: dict[str, Any]) -> ConvergenceWindow:
    return ConvergenceWindow.model_validate(payload["convergence_window"])


def _parse_tests(payload: dict[str, Any]) -> list[HypothesisTest]:
    return [HypothesisTest.from_legacy(row) for row in payload["window_hypothesis_tests"]]


@pytest.mark.integration
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["slug"])
def test_phase17_golden_direction_volume_strength(case: dict[str, Any]) -> None:
    window = _parse_window(case)
    tests = _parse_tests(case)
    exp = case["expected"]

    direction, _breakdown = classify_direction_concordance(window, tests)
    assert direction == DirectionConcordance(exp["direction_concordance"])

    vol_flag, vol_ratio = compute_volume_ramp_flag(tests)
    assert vol_flag == VolumeRampFlag(exp["volume_flag"])
    expected_ratio = exp["volume_ratio"]
    if expected_ratio is None:
        assert vol_ratio is None
    else:
        assert vol_ratio is not None
        assert vol_ratio == pytest.approx(float(expected_ratio), rel=0, abs=1e-9)

    strength = classify_finding_strength(
        window,
        tests,
        case["control_comparison"],
        probability_features_available=case["probability_features_available"],
    )
    assert strength == FindingStrength(exp["finding_strength"])


@pytest.mark.integration
def test_phase17_fixture_slugs_match_prompt_cohort() -> None:
    """Nine authors: target + eight MODERATE controls from Phase 17 prompt."""
    slugs = {c["slug"] for c in _load_cases()}
    expected = {
        "colby-hall",
        "ahmad-austin",
        "charlie-nash",
        "isaac-schorr",
        "jennifer-bowers-bahney",
        "joe-depaolo",
        "sarah-rumpf",
        "tommy-christopher",
        "zachary-leeman",
    }
    assert slugs == expected
