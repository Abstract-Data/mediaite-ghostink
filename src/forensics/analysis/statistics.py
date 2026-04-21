"""Hypothesis tests, effect sizes, bootstrap CIs, and multiple-comparison correction (Phase 7)."""

from __future__ import annotations

import math

import numpy as np
from scipy import stats

from forensics.models.analysis import HypothesisTest


def cohens_d(
    group1: list[float] | np.ndarray,
    group2: list[float] | np.ndarray,
) -> float:
    """Pooled Cohen's d (mean2 - mean1) / pooled_std for two samples (array-like).

    Handles length-1 tails (changepoint segments) like the legacy numpy helper.
    """
    a = np.asarray(group1, dtype=float).ravel()
    b = np.asarray(group2, dtype=float).ravel()
    if a.size < 1 or b.size < 1:
        return 0.0
    if a.size == 1 and b.size >= 2:
        pooled = float(np.std(b, ddof=1))
        if pooled < 1e-12:
            return 0.0
        return (float(np.mean(b)) - float(a[0])) / pooled
    if b.size == 1 and a.size >= 2:
        pooled = float(np.std(a, ddof=1))
        if pooled < 1e-12:
            return 0.0
        return (float(b[0]) - float(np.mean(a))) / pooled
    if a.size < 2 or b.size < 2:
        return float(np.mean(b) - np.mean(a)) if a.size and b.size else 0.0
    m1, m2 = float(np.mean(a)), float(np.mean(b))
    v1, v2 = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    n1, n2 = a.size, b.size
    pooled_std = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    if pooled_std <= 0.0 or not math.isfinite(pooled_std):
        return 0.0
    return float((m2 - m1) / pooled_std)


def bootstrap_ci(
    group1: list[float],
    group2: list[float],
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
    *,
    seed: int = 42,
) -> tuple[float, float]:
    """Percentile bootstrap CI for mean(group2) - mean(group1)."""
    a = np.asarray(group1, dtype=float).ravel()
    b = np.asarray(group2, dtype=float).ravel()
    if a.size == 0 or b.size == 0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    diffs: list[float] = []
    for _ in range(n_bootstrap):
        s1 = rng.choice(a, size=a.size, replace=True)
        s2 = rng.choice(b, size=b.size, replace=True)
        diffs.append(float(np.mean(s2) - np.mean(s1)))
    arr = np.asarray(diffs, dtype=float)
    lo = float(np.percentile(arr, 100 * alpha / 2))
    hi = float(np.percentile(arr, 100 * (1 - alpha / 2)))
    return (lo, hi)


def _safe_pvalue(p: float) -> float:
    if p is None or not math.isfinite(float(p)):
        return 1.0
    return float(min(1.0, max(0.0, float(p))))


def run_hypothesis_tests(
    feature_values: list[float],
    breakpoint_idx: int,
    feature_name: str,
    author_id: str,
    *,
    n_bootstrap: int = 1000,
) -> list[HypothesisTest]:
    """Welch t, Mann–Whitney U, and two-sample KS at a candidate split index."""
    y = list(feature_values)
    n = len(y)
    if n < 4 or breakpoint_idx < 1 or breakpoint_idx >= n:
        return []
    pre = y[:breakpoint_idx]
    post = y[breakpoint_idx:]
    if len(pre) < 2 or len(post) < 2:
        return []

    tests: list[HypothesisTest] = []

    _t_stat, p_welch = stats.ttest_ind(pre, post, equal_var=False)
    d = cohens_d(pre, post)
    ci = bootstrap_ci(pre, post, n_bootstrap=n_bootstrap)
    tests.append(
        HypothesisTest(
            test_name=f"welch_t_{feature_name}",
            feature_name=feature_name,
            author_id=author_id,
            raw_p_value=_safe_pvalue(float(p_welch)),
            corrected_p_value=_safe_pvalue(float(p_welch)),
            effect_size_cohens_d=d,
            confidence_interval_95=ci,
            significant=False,
        )
    )

    try:
        _u_stat, p_mw = stats.mannwhitneyu(pre, post, alternative="two-sided")
    except ValueError:
        p_mw = 1.0
    tests.append(
        HypothesisTest(
            test_name=f"mann_whitney_{feature_name}",
            feature_name=feature_name,
            author_id=author_id,
            raw_p_value=_safe_pvalue(float(p_mw)),
            corrected_p_value=_safe_pvalue(float(p_mw)),
            effect_size_cohens_d=d,
            confidence_interval_95=ci,
            significant=False,
        )
    )

    _ks_stat, p_ks = stats.ks_2samp(pre, post)
    tests.append(
        HypothesisTest(
            test_name=f"ks_test_{feature_name}",
            feature_name=feature_name,
            author_id=author_id,
            raw_p_value=_safe_pvalue(float(p_ks)),
            corrected_p_value=_safe_pvalue(float(p_ks)),
            effect_size_cohens_d=d,
            confidence_interval_95=ci,
            significant=False,
        )
    )
    return tests


def apply_correction(
    tests: list[HypothesisTest],
    method: str = "benjamini_hochberg",
    alpha: float = 0.05,
) -> list[HypothesisTest]:
    """Assign Benjamini–Hochberg or Bonferroni adjusted p-values and significance (p-only)."""
    if not tests:
        return tests
    p_values = [t.raw_p_value for t in tests]
    n = len(p_values)
    if method == "bonferroni":
        corrected = [min(p * n, 1.0) for p in p_values]
    elif method == "benjamini_hochberg":
        order = sorted(range(n), key=lambda i: p_values[i])
        bh = [0.0] * n
        for rank, idx in enumerate(order, start=1):
            bh[idx] = min(p_values[idx] * n / rank, 1.0)
        for k in range(n - 2, -1, -1):
            idx_k = order[k]
            idx_next = order[k + 1]
            bh[idx_k] = min(bh[idx_k], bh[idx_next])
        corrected = [min(c, 1.0) for c in bh]
    else:
        msg = f"Unknown correction method: {method!r}"
        raise ValueError(msg)

    for test, cp in zip(tests, corrected, strict=True):
        test.corrected_p_value = cp
        test.significant = cp < alpha
    return tests


def filter_by_effect_size(
    tests: list[HypothesisTest],
    min_d: float,
    *,
    alpha: float,
) -> list[HypothesisTest]:
    """Require both corrected significance and minimum |Cohen's d|."""
    for test in tests:
        sig_p = test.corrected_p_value < alpha
        sig_d = abs(test.effect_size_cohens_d) >= min_d
        test.significant = sig_p and sig_d
    return tests
