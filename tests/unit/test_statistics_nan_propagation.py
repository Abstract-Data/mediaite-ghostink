"""Phase 16 D6 — NaN handling, skipped rows, BH denominators, convergence rankable map."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta

import pytest

from forensics.analysis.convergence import (
    FAMILY_COUNT,
    ConvergenceInput,
    _eligible_convergence_family_axes,
    _pipeline_a_from_stylometry,
    compute_convergence_scores,
)
from forensics.analysis.statistics import (
    apply_correction,
    compute_n_rankable_features_per_family,
    hypothesis_test_is_bh_rankable,
    run_hypothesis_tests,
)
from forensics.models.analysis import ChangePoint, HypothesisTest


def test_run_hypothesis_tests_logs_nan_drops_and_counts(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    # 4+ points, valid breakpoint; inject NaN in pre segment only
    pre = [1.0, float("nan"), 2.0, 3.0]
    post = [8.0, 9.0, 10.0, 11.0]
    series = pre + post
    out = run_hypothesis_tests(series, len(pre), "ttr", "author-z", n_bootstrap=30)
    assert any("dropped_nonfinite pre=1 post=0" in r.message for r in caplog.records)
    assert len(out) == 2
    assert all(t.n_nan_dropped == 1 for t in out)
    assert all(t.n_pre == 3 for t in out)
    assert all(t.n_post == 4 for t in out)
    assert all(t.skipped_reason is None for t in out)


def test_insufficient_finite_mass_returns_skipped_battery() -> None:
    out = run_hypothesis_tests([1.0, float("nan"), 5.0, 5.0], 1, "ttr", "a")
    assert len(out) == 2
    assert {t.test_name for t in out} == {"welch_t_ttr", "mann_whitney_ttr"}
    assert all(t.skipped_reason == "insufficient_finite_values_per_segment" for t in out)
    assert all(not hypothesis_test_is_bh_rankable(t) for t in out)
    assert out[0].n_pre == 1 and out[0].n_post == 2


def test_apply_correction_bh_denominator_excludes_non_rankable() -> None:
    nan = float("nan")
    tests = [
        HypothesisTest(
            test_name="welch_t_a",
            feature_name="ttr",
            author_id="x",
            raw_p_value=0.01,
            corrected_p_value=0.01,
            effect_size_cohens_d=0.5,
            confidence_interval_95=(0.0, 1.0),
            significant=False,
            n_pre=4,
            n_post=4,
            degenerate=False,
        ),
        HypothesisTest(
            test_name="mann_whitney_a",
            feature_name="ttr",
            author_id="x",
            raw_p_value=nan,
            corrected_p_value=nan,
            effect_size_cohens_d=0.5,
            confidence_interval_95=(0.0, 1.0),
            significant=False,
            n_pre=4,
            n_post=4,
            degenerate=True,
        ),
        HypothesisTest(
            test_name="welch_t_b",
            feature_name="mattr",
            author_id="x",
            raw_p_value=0.02,
            corrected_p_value=0.02,
            effect_size_cohens_d=0.5,
            confidence_interval_95=(0.0, 1.0),
            significant=False,
            n_pre=4,
            n_post=4,
            degenerate=False,
        ),
    ]
    out = apply_correction(tests, method="benjamini_hochberg", alpha=0.05)
    rankable = [t for t in out if hypothesis_test_is_bh_rankable(t)]
    assert len(rankable) == 2
    assert not hypothesis_test_is_bh_rankable(out[1])
    assert math.isnan(float(out[1].corrected_p_value))
    # BH with m=2: larger raw p (0.02) gets rank 2 => 0.02 * 2 / 2 = 0.02
    welch_b = next(t for t in out if t.test_name == "welch_t_b")
    assert welch_b.corrected_p_value == pytest.approx(0.02)


def test_hypothesis_test_from_legacy_defaults_sample_fields() -> None:
    legacy = {
        "test_name": "welch_t_x",
        "feature_name": "ttr",
        "author_id": "1",
        "raw_p_value": 0.05,
        "corrected_p_value": 0.05,
        "effect_size_cohens_d": 0.1,
        "confidence_interval_95": (0.0, 0.2),
        "significant": False,
    }
    t = HypothesisTest.from_legacy(legacy)
    assert t.n_pre == -1 and t.n_post == -1
    assert t.n_nan_dropped == 0
    assert t.skipped_reason is None
    assert t.degenerate is False


def test_compute_n_rankable_features_per_family_counts_distinct_features() -> None:
    tests = [
        HypothesisTest(
            test_name="welch_t_ttr",
            feature_name="ttr",
            author_id="1",
            raw_p_value=0.1,
            corrected_p_value=0.1,
            effect_size_cohens_d=0.1,
            confidence_interval_95=(0.0, 0.0),
            significant=False,
            n_pre=3,
            n_post=3,
        ),
        HypothesisTest(
            test_name="mann_whitney_ttr",
            feature_name="ttr",
            author_id="1",
            raw_p_value=0.2,
            corrected_p_value=0.2,
            effect_size_cohens_d=0.1,
            confidence_interval_95=(0.0, 0.0),
            significant=False,
            n_pre=3,
            n_post=3,
        ),
        HypothesisTest(
            test_name="welch_t_mattr",
            feature_name="mattr",
            author_id="1",
            raw_p_value=0.3,
            corrected_p_value=0.3,
            effect_size_cohens_d=0.1,
            confidence_interval_95=(0.0, 0.0),
            significant=False,
            n_pre=3,
            n_post=3,
        ),
    ]
    m = compute_n_rankable_features_per_family(tests)
    assert m.get("lexical_richness") == 2  # ttr + mattr


def test_eligible_convergence_axes_falls_back_when_empty() -> None:
    assert _eligible_convergence_family_axes({}, FAMILY_COUNT) == FAMILY_COUNT
    assert _eligible_convergence_family_axes({"readability": 2}, FAMILY_COUNT) == 1


def test_pipeline_a_ratio_uses_eligible_denominator() -> None:
    cp = ChangePoint(
        feature_name="ttr",
        author_id="1",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        confidence=0.95,
        method="pelt",
        effect_size_cohens_d=0.4,
        direction="increase",
    )
    n_rank = {"lexical_richness": 2, "readability": 0}
    feats, fams, ratio, _score = _pipeline_a_from_stylometry([cp], n_rank)
    assert feats == ["ttr"]
    eligible = _eligible_convergence_family_axes(n_rank, FAMILY_COUNT)
    assert ratio == pytest.approx(1.0 / float(eligible))


def test_compute_convergence_scores_attaches_n_rankable_per_window() -> None:
    """Mirror ``test_single_changepoint_single_feature_emits_window`` signals + rankable map."""
    cp_time = datetime(2024, 3, 15, tzinfo=UTC)
    cp = ChangePoint(
        feature_name="ttr",
        author_id="author-1",
        timestamp=cp_time,
        confidence=0.9,
        method="pelt",
        effect_size_cohens_d=0.8,
        direction="increase",
    )
    velocities = [
        ("2024-01", 0.05),
        ("2024-02", 0.08),
        ("2024-03", 0.90),
        ("2024-04", 0.85),
    ]
    baseline = [
        (cp_time + timedelta(days=d), s)
        for d, s in [(0, 0.95), (10, 0.90), (20, 0.60), (30, 0.30), (40, 0.20)]
    ]
    n_map = {"lexical_richness": 3}
    inp = ConvergenceInput.build(
        change_points=[cp],
        centroid_velocities=velocities,
        baseline_similarity_curve=baseline,
        window_days=90,
        total_feature_count=1,
        min_feature_ratio=0.0,
        n_rankable_per_family=n_map,
    )
    wins = compute_convergence_scores(inp)
    assert wins
    assert wins[0].n_rankable_per_family == n_map
