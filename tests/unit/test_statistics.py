"""Unit tests for ``forensics.analysis.statistics`` (F4 coverage pass)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from forensics.analysis.statistics import (
    apply_correction,
    apply_cross_author_correction,
    bootstrap_ci,
    cohens_d,
    filter_by_effect_size,
    run_hypothesis_tests,
)
from forensics.models.analysis import HypothesisTest


def test_cohens_d_equal_groups_is_zero() -> None:
    assert cohens_d([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 0.0


def test_cohens_d_sign_positive_when_group2_greater() -> None:
    d = cohens_d([1.0, 2.0, 3.0, 4.0], [10.0, 11.0, 12.0, 13.0])
    assert d > 0


def test_cohens_d_sign_negative_when_group1_greater() -> None:
    d = cohens_d([10.0, 11.0, 12.0, 13.0], [1.0, 2.0, 3.0, 4.0])
    assert d < 0


def test_cohens_d_handles_empty_inputs() -> None:
    assert cohens_d([], []) == 0.0
    assert cohens_d([1.0], []) == 0.0
    assert cohens_d([], [1.0]) == 0.0


def test_cohens_d_length_one_tail() -> None:
    # Single post-change point vs multi-sample pre-segment — uses pre std.
    d = cohens_d([1.0, 2.0, 3.0, 4.0], [10.0])
    assert math.isfinite(d)
    assert d > 0


def test_cohens_d_length_one_pre() -> None:
    d = cohens_d([10.0], [1.0, 2.0, 3.0, 4.0])
    assert math.isfinite(d)
    assert d < 0


def test_cohens_d_zero_variance_returns_zero() -> None:
    # Both groups are constant — pooled std is zero, so d collapses to 0.
    assert cohens_d([5.0, 5.0, 5.0], [7.0, 7.0, 7.0]) == 0.0


def test_cohens_d_accepts_ndarray() -> None:
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = np.array([5.0, 6.0, 7.0, 8.0])
    assert cohens_d(a, b) > 0


def test_bootstrap_ci_returns_ordered_bounds() -> None:
    lo, hi = bootstrap_ci([1.0] * 20, [5.0] * 20, n_bootstrap=200, seed=1)
    assert lo <= hi


def test_bootstrap_ci_is_deterministic_with_seed() -> None:
    a, b = [1.0, 2.0, 3.0, 4.0, 5.0], [10.0, 11.0, 12.0, 13.0, 14.0]
    r1 = bootstrap_ci(a, b, n_bootstrap=200, seed=42)
    r2 = bootstrap_ci(a, b, n_bootstrap=200, seed=42)
    assert r1 == r2


def test_bootstrap_ci_empty_inputs_return_zero() -> None:
    assert bootstrap_ci([], [1.0], n_bootstrap=10) == (0.0, 0.0)
    assert bootstrap_ci([1.0], [], n_bootstrap=10) == (0.0, 0.0)


def test_bootstrap_ci_contains_point_estimate() -> None:
    # Populations clearly separated — CI on the diff should not span zero.
    a = [1.0] * 30
    b = [5.0] * 30
    lo, hi = bootstrap_ci(a, b, n_bootstrap=500, seed=7)
    assert lo > 0


def test_run_hypothesis_tests_short_series_returns_skipped_battery() -> None:
    # Phase 16 D2 — invalid split yields explicit skipped rows (NaN p), not [].
    for out in (
        run_hypothesis_tests([1.0, 2.0, 3.0], 1, "f", "a"),
        run_hypothesis_tests([1.0] * 10, 0, "f", "a"),
        run_hypothesis_tests([1.0] * 10, 10, "f", "a"),
    ):
        assert len(out) == 2
        assert {t.test_name for t in out} == {"welch_t_f", "mann_whitney_f"}
        assert all(t.skipped_reason == "invalid_breakpoint_or_short_series" for t in out)
        assert all(not math.isfinite(t.raw_p_value) for t in out)


def test_run_hypothesis_tests_emits_welch_and_mw_by_default() -> None:
    # Phase 15 C1: KS dropped from default battery. Welch + Mann–Whitney
    # already cover the location shifts the forensic analysis cares about.
    pre = [1.0, 1.1, 0.9, 1.2, 0.95, 1.05, 1.1, 0.9, 1.0, 1.05]
    post = [5.0, 5.1, 4.9, 5.2, 4.95, 5.05, 5.1, 4.9, 5.0, 5.05]
    tests = run_hypothesis_tests(pre + post, len(pre), "ttr", "author-x", n_bootstrap=50)
    names = {t.test_name for t in tests}
    assert any(n.startswith("welch_t") for n in names)
    assert any(n.startswith("mann_whitney") for n in names)
    assert not any(n.startswith("ks_2samp") for n in names)
    for t in tests:
        assert t.feature_name == "ttr"
        assert t.author_id == "author-x"
        assert 0.0 <= t.raw_p_value <= 1.0
        assert isinstance(t.confidence_interval_95, tuple) and len(t.confidence_interval_95) == 2


def test_run_hypothesis_tests_tiny_segment_returns_skipped_battery() -> None:
    # Pre has only one finite element after NaN strip — skipped placeholders.
    out = run_hypothesis_tests([1.0, 5.0, 5.0, 5.0], 1, "f", "a")
    assert len(out) == 2
    assert all(t.skipped_reason == "insufficient_finite_values_per_segment" for t in out)


def _make_test(raw_p: float, effect: float = 0.5) -> HypothesisTest:
    return HypothesisTest(
        test_name="welch_t",
        feature_name="x",
        author_id="a",
        raw_p_value=raw_p,
        corrected_p_value=raw_p,
        effect_size_cohens_d=effect,
        confidence_interval_95=(0.0, 1.0),
        significant=False,
        n_pre=4,
        n_post=4,
    )


def test_apply_correction_empty_is_noop() -> None:
    assert apply_correction([]) == []


def test_apply_correction_bonferroni_scales_by_n() -> None:
    tests = [_make_test(p) for p in (0.01, 0.02, 0.03)]
    out = apply_correction(tests, method="bonferroni", alpha=0.05)
    assert pytest.approx(out[0].corrected_p_value) == 0.03  # 0.01 * 3
    assert pytest.approx(out[1].corrected_p_value) == 0.06  # clipped at 1.0 rule n/a
    assert pytest.approx(out[2].corrected_p_value) == 0.09
    assert out[0].significant is True
    assert out[1].significant is False
    assert out[2].significant is False


def test_apply_correction_bonferroni_clips_at_one() -> None:
    tests = [_make_test(0.6), _make_test(0.8)]
    out = apply_correction(tests, method="bonferroni")
    assert all(t.corrected_p_value <= 1.0 for t in out)


def test_apply_correction_benjamini_hochberg() -> None:
    tests = [_make_test(p) for p in (0.001, 0.010, 0.050, 0.500)]
    out = apply_correction(tests, method="benjamini_hochberg", alpha=0.05)
    # BH adjusted p-values must be monotonic non-decreasing after sort by raw_p.
    corr_sorted = sorted(t.corrected_p_value for t in out)
    assert corr_sorted == sorted(corr_sorted)
    # Input tests are not mutated (copy-on-write).
    for t in tests:
        assert t.corrected_p_value == t.raw_p_value
        assert t.significant is False


def test_apply_correction_rejects_unknown_method() -> None:
    with pytest.raises(ValueError, match="Unknown correction method"):
        apply_correction([_make_test(0.1)], method="holm")


def test_hypothesis_min_segment_n_skips_small_segments() -> None:
    pre = [1.0] * 9
    post = [5.0] * 9
    out = run_hypothesis_tests(pre + post, len(pre), "f", "a", hypothesis_min_segment_n=10)
    assert len(out) == 2
    assert all(t.skipped_reason and "insufficient_n_pre_or_post" in t.skipped_reason for t in out)


def test_apply_cross_author_correction_two_slugs() -> None:
    t_a = HypothesisTest(
        test_name="welch_t_ttr",
        feature_name="ttr",
        author_id="1",
        raw_p_value=0.01,
        corrected_p_value=0.01,
        effect_size_cohens_d=0.5,
        confidence_interval_95=(0.0, 1.0),
        significant=False,
        n_pre=10,
        n_post=10,
    )
    t_b = HypothesisTest(
        test_name="welch_t_ttr",
        feature_name="ttr",
        author_id="2",
        raw_p_value=0.04,
        corrected_p_value=0.04,
        effect_size_cohens_d=0.5,
        confidence_interval_95=(0.0, 1.0),
        significant=False,
        n_pre=10,
        n_post=10,
    )
    out = apply_cross_author_correction({"alice": [t_a], "bob": [t_b]})
    # Across-author BH on minima (0.01, 0.04) with stable slug tie-break:
    # adjusted = (0.01*2/1, 0.04*2/2) then backward pass → (0.02, 0.04).
    assert out["alice"][0].cross_author_corrected_p == pytest.approx(0.02, abs=1e-12)
    assert out["bob"][0].cross_author_corrected_p == pytest.approx(0.04, abs=1e-12)
    assert out["alice"][0].cross_author_correction_reason is None
    assert out["bob"][0].cross_author_correction_reason is None


def test_apply_cross_author_correction_single_author_no_pmin_substitution() -> None:
    lone = HypothesisTest(
        test_name="welch_t_ttr",
        feature_name="ttr",
        author_id="1",
        raw_p_value=0.02,
        corrected_p_value=0.02,
        effect_size_cohens_d=0.5,
        confidence_interval_95=(0.0, 1.0),
        significant=False,
        n_pre=10,
        n_post=10,
    )
    out = apply_cross_author_correction({"solo": [lone]})
    assert out["solo"][0].cross_author_corrected_p is None
    assert out["solo"][0].cross_author_correction_reason == "single-author-no-cross-correction"


def test_filter_by_effect_size_requires_both_criteria() -> None:
    sig_and_big = _make_test(0.001, effect=1.0).model_copy(update={"corrected_p_value": 0.001})
    sig_small = _make_test(0.001, effect=0.05).model_copy(update={"corrected_p_value": 0.001})
    insig_big = _make_test(0.9, effect=1.0).model_copy(update={"corrected_p_value": 0.9})
    out = filter_by_effect_size([sig_and_big, sig_small, insig_big], min_d=0.2, alpha=0.05)
    assert out[0].significant is True
    assert out[1].significant is False
    assert out[2].significant is False


def test_filter_by_effect_size_preserves_input() -> None:
    test = _make_test(0.001, effect=1.0).model_copy(update={"corrected_p_value": 0.001})
    out = filter_by_effect_size([test], min_d=0.2, alpha=0.05)
    # Input instance is unchanged; output is a fresh copy.
    assert test.significant is False
    assert out[0].significant is True
    assert out[0] is not test
