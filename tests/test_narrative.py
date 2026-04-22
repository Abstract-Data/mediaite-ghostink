"""Phase 12 §6d — evidence-chain narrative determinism + signal tiers."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from forensics.models.analysis import (
    AnalysisResult,
    ChangePoint,
    ConvergenceWindow,
    DriftScores,
    HypothesisTest,
)
from forensics.reporting.narrative import generate_evidence_narrative
from forensics.survey.scoring import compute_composite_score

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _empty_result(slug: str = "jane-doe") -> AnalysisResult:
    """An AnalysisResult with no signal in any pipeline."""
    return AnalysisResult(
        author_id=slug,
        run_id="00000000-0000-0000-0000-000000000000",
        run_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        config_hash="deadbeefcafebabe",
        change_points=[],
        convergence_windows=[],
        drift_scores=None,
        hypothesis_tests=[],
    )


def _strong_result(slug: str = "jane-doe") -> AnalysisResult:
    """An AnalysisResult that clears the STRONG thresholds in scoring.py."""
    # STRONG requires:
    #   composite >= 0.7 AND conv_score >= 0.5 AND max_effect >= 0.8 AND
    #   num_windows >= 2
    # conv_score = min(num_windows * 0.2 + strongest_ratio * 0.8, 1.0)
    # With 2 windows at 0.9 ratio => conv = 1.0; composite = 0.4 * 1.0 +
    # 0.3 * pa + 0.3 * pb. pa comes from unique-cp-feature count relative
    # to 35 * 0.3 = 10.5 — we push it to 1.0 via 11 distinct features.
    features = [f"feature_{i}" for i in range(11)]
    cps = [
        ChangePoint(
            feature_name=f,
            author_id=slug,
            timestamp=datetime(2023, 3, 15, tzinfo=UTC),
            confidence=0.95,
            method="pelt",
            effect_size_cohens_d=0.9,
            direction="increase",
        )
        for f in features
    ]
    windows = [
        ConvergenceWindow(
            start_date=date(2023, 3, 1),
            end_date=date(2023, 6, 1),
            features_converging=features[:6],
            convergence_ratio=0.9,
            pipeline_a_score=0.9,
            pipeline_b_score=0.9,
            pipeline_c_score=None,
        ),
        ConvergenceWindow(
            start_date=date(2023, 7, 1),
            end_date=date(2023, 10, 1),
            features_converging=features[5:10],
            convergence_ratio=0.85,
            pipeline_a_score=0.85,
            pipeline_b_score=0.85,
            pipeline_c_score=None,
        ),
    ]
    drift = DriftScores(
        author_id=slug,
        baseline_centroid_similarity=0.82,
        ai_baseline_similarity=0.77,
        monthly_centroid_velocities=[0.1, 0.1, 0.1, 0.3, 0.3, 0.3],
        intra_period_variance_trend=[0.05, 0.06, 0.07, 0.08, 0.09, 0.10],
    )
    tests = [
        HypothesisTest(
            test_name="mann_whitney",
            feature_name="ttr",
            author_id=slug,
            raw_p_value=0.0001,
            corrected_p_value=0.001,
            effect_size_cohens_d=1.2,
            confidence_interval_95=(0.8, 1.6),
            significant=True,
        ),
        HypothesisTest(
            test_name="mann_whitney",
            feature_name="hapax_ratio",
            author_id=slug,
            raw_p_value=0.001,
            corrected_p_value=0.005,
            effect_size_cohens_d=-0.95,
            confidence_interval_95=(-1.2, -0.7),
            significant=True,
        ),
        HypothesisTest(
            test_name="mann_whitney",
            feature_name="burstiness",
            author_id=slug,
            raw_p_value=0.002,
            corrected_p_value=0.01,
            effect_size_cohens_d=0.85,
            confidence_interval_95=(0.5, 1.2),
            significant=True,
        ),
    ]
    return AnalysisResult(
        author_id=slug,
        run_id="11111111-2222-3333-4444-555555555555",
        run_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        config_hash="deadbeefcafebabe",
        change_points=cps,
        convergence_windows=windows,
        drift_scores=drift,
        hypothesis_tests=tests,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_narrative_deterministic() -> None:
    """Same AnalysisResult + slug → byte-identical narrative."""
    analysis = _strong_result()
    a = generate_evidence_narrative(analysis, "jane-doe")
    b = generate_evidence_narrative(analysis, "jane-doe")
    assert a == b
    assert a.encode("utf-8") == b.encode("utf-8")


def test_narrative_no_signal() -> None:
    """NONE tier should use calibrated 'no evidence' language."""
    analysis = _empty_result()
    text = generate_evidence_narrative(analysis, "jane-doe")
    assert "NONE" in text
    assert "no evidence" in text.lower()
    # Do not overclaim in the absence of signal.
    assert "convergence window" not in text.lower()


def test_narrative_strong_signal() -> None:
    """STRONG tier should cite quantitative effect sizes."""
    analysis = _strong_result()
    score = compute_composite_score(analysis)
    text = generate_evidence_narrative(analysis, "jane-doe", score=score)
    assert score.strength.value == "strong"
    assert "STRONG" in text
    # Effect sizes appear in "d=..." form for at least one feature.
    assert "d=" in text
    assert "ttr" in text  # largest |d| = 1.2
    # Convergence window appears.
    assert "convergence window" in text.lower()


def test_narrative_contains_slug() -> None:
    """Author slug must appear verbatim."""
    analysis = _strong_result()
    for slug in ("jane-doe", "john-q-public", "another-writer"):
        text = generate_evidence_narrative(analysis, slug)
        assert slug in text


def test_narrative_control_sentence_toggle() -> None:
    """control_count > 0 should surface the control cohort sentence."""
    analysis = _strong_result()
    text_no_ctrl = generate_evidence_narrative(analysis, "jane-doe", control_count=0)
    text_ctrl = generate_evidence_narrative(analysis, "jane-doe", control_count=3)
    assert "natural-control" not in text_no_ctrl.lower()
    assert "natural-control" in text_ctrl.lower()
    assert "3 natural-control" in text_ctrl


@pytest.mark.parametrize("slug", ["jane-doe", "a-b-c"])
def test_narrative_caveat_always_present(slug: str) -> None:
    """The caveat sentence should always appear, regardless of signal tier."""
    for factory in (_empty_result, _strong_result):
        text = generate_evidence_narrative(factory(slug), slug)
        assert "do not by themselves demonstrate AI authorship" in text
