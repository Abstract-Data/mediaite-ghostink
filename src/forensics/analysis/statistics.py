"""Hypothesis tests, effect sizes, bootstrap CIs, and multiple-comparison correction (Phase 7).

Per-family vs per-author FDR (Phase 15 C2)
------------------------------------------

Benjamini–Hochberg (BH) assumes the p-values it corrects are drawn from
independent hypotheses. In this pipeline, many stylometric features live in
the same logical "family" and test correlated hypotheses of the same
underlying shift (e.g. ``flesch_kincaid`` / ``coleman_liau`` / ``gunning_fog``
all read "this author got easier to read"; the passive-voice /
nominalization / first-person-plural features all move together when a
writer leans on AI-style boilerplate).

Running a single author-wide BH collapses those correlated families into one
pooled denominator, inflates ``n`` in ``rank * alpha / n``, and over-corrects
away real signal. The methodologically preferable alternative — implemented
by :func:`apply_correction_grouped` — is to run BH independently within
each feature family and concatenate the results. Each family becomes its own
FDR regime (so ``n`` is the within-family test count) while the across-
family denominator stays honest because families are, by construction,
designed to be independent axes of writing style.

Residual within-family correlation (e.g. three readability formulas inside
one ``readability`` family) still over-corrects slightly: BH is conservative
under positive dependence. Closing that gap requires an effective-N
correction (correlation-matrix estimation per author) and is out of scope
for v0.4.0; it is documented as a known limitation rather than silently
adjusted here.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable

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


def _hypothesis_test(
    *,
    prefix: str,
    feature_name: str,
    author_id: str,
    raw_p: float,
    d: float,
    ci: tuple[float, float],
) -> HypothesisTest:
    """Single Welch / Mann–Whitney / KS row with shared effect size and CI (RF-SMELL-005)."""
    sp = _safe_pvalue(float(raw_p))
    return HypothesisTest(
        test_name=f"{prefix}_{feature_name}",
        feature_name=feature_name,
        author_id=author_id,
        raw_p_value=sp,
        corrected_p_value=sp,
        effect_size_cohens_d=d,
        confidence_interval_95=ci,
        significant=False,
    )


def run_hypothesis_tests(
    feature_values: list[float],
    breakpoint_idx: int,
    feature_name: str,
    author_id: str,
    *,
    n_bootstrap: int = 1000,
    enable_ks_test: bool = False,
) -> list[HypothesisTest]:
    """Welch t and Mann–Whitney U at a candidate split index (KS opt-in).

    Phase 15 C1: KS is dropped from the default battery. Welch and Mann–Whitney
    already cover the location shifts the forensic analysis cares about, and
    KS overlaps Mann–Whitney enough that keeping it just inflates the BH FDR
    denominator with a correlated test (per-CP test count drops 3 → 2). Pass
    ``enable_ks_test=True`` to re-introduce the two-sample KS branch for
    replication runs that want distribution-shape detection.
    """
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
        _hypothesis_test(
            prefix="welch_t",
            feature_name=feature_name,
            author_id=author_id,
            raw_p=float(p_welch),
            d=d,
            ci=ci,
        )
    )

    try:
        _u_stat, p_mw = stats.mannwhitneyu(pre, post, alternative="two-sided")
    except ValueError:
        p_mw = 1.0
    tests.append(
        _hypothesis_test(
            prefix="mann_whitney",
            feature_name=feature_name,
            author_id=author_id,
            raw_p=float(p_mw),
            d=d,
            ci=ci,
        )
    )

    if enable_ks_test:
        _ks_stat, p_ks = stats.ks_2samp(pre, post)
        tests.append(
            _hypothesis_test(
                prefix="ks_2samp",
                feature_name=feature_name,
                author_id=author_id,
                raw_p=float(p_ks),
                d=d,
                ci=ci,
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

    return [
        test.model_copy(update={"corrected_p_value": cp, "significant": cp < alpha})
        for test, cp in zip(tests, corrected, strict=True)
    ]


def apply_correction_grouped(
    tests: list[HypothesisTest],
    group_key: Callable[[HypothesisTest], str],
    method: str = "benjamini_hochberg",
    alpha: float = 0.05,
) -> list[HypothesisTest]:
    """Group ``tests`` by ``group_key``, apply BH per group, then concatenate.

    Singleton groups return raw p-values unchanged (BH is a no-op when the
    denominator ``n == 1``) — this is mathematically correct and intentional;
    do not "patch" it. Empty groups (should never occur given ``defaultdict``
    semantics, but guarded defensively) are skipped.

    See the module docstring for the per-family BH rationale (Phase 15 C2).
    """
    groups: dict[str, list[HypothesisTest]] = defaultdict(list)
    for test in tests:
        groups[group_key(test)].append(test)
    out: list[HypothesisTest] = []
    for _key, group in groups.items():
        if not group:
            continue
        out.extend(apply_correction(group, method=method, alpha=alpha))
    return out


def filter_by_effect_size(
    tests: list[HypothesisTest],
    min_d: float,
    *,
    alpha: float,
) -> list[HypothesisTest]:
    """Require both corrected significance and minimum |Cohen's d|."""
    updated: list[HypothesisTest] = []
    for test in tests:
        sig_p = test.corrected_p_value < alpha
        sig_d = abs(test.effect_size_cohens_d) >= min_d
        updated.append(test.model_copy(update={"significant": sig_p and sig_d}))
    return updated
