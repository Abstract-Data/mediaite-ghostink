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

import logging
import math
from collections import defaultdict
from collections.abc import Callable

import numpy as np
from scipy import stats

from forensics.models.analysis import HypothesisTest

logger = logging.getLogger(__name__)


def _cohens_d_value_and_degenerate(
    group1: list[float] | np.ndarray,
    group2: list[float] | np.ndarray,
) -> tuple[float, bool]:
    """C-07 — single implementation for Cohen's *d* and variance-degeneracy (Phase 16 D3)."""
    a = np.asarray(group1, dtype=float).ravel()
    b = np.asarray(group2, dtype=float).ravel()
    degenerate = False
    if a.size < 1 or b.size < 1:
        return 0.0, degenerate
    if a.size == 1 and b.size >= 2:
        pooled = float(np.std(b, ddof=1))
        degenerate = pooled < 1e-12 or not math.isfinite(pooled)
        if degenerate:
            return 0.0, degenerate
        return (float(np.mean(b)) - float(a[0])) / pooled, degenerate
    if b.size == 1 and a.size >= 2:
        pooled = float(np.std(a, ddof=1))
        degenerate = pooled < 1e-12 or not math.isfinite(pooled)
        if degenerate:
            return 0.0, degenerate
        return (float(b[0]) - float(np.mean(a))) / pooled, degenerate
    if a.size < 2 or b.size < 2:
        d = float(np.mean(b) - np.mean(a)) if a.size and b.size else 0.0
        return d, degenerate
    m1, m2 = float(np.mean(a)), float(np.mean(b))
    v1, v2 = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    n1, n2 = a.size, b.size
    pooled_std = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    degenerate = pooled_std <= 0.0 or not math.isfinite(pooled_std)
    if degenerate:
        return 0.0, degenerate
    return float((m2 - m1) / pooled_std), degenerate


def cohens_d(
    group1: list[float] | np.ndarray,
    group2: list[float] | np.ndarray,
) -> float:
    """Pooled Cohen's d (mean2 - mean1) / pooled_std for two samples (array-like).

    Handles length-1 tails (changepoint segments) like the legacy numpy helper.
    """
    return _cohens_d_value_and_degenerate(group1, group2)[0]


def bootstrap_ci(
    group1: list[float],
    group2: list[float],
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
    *,
    seed: int = 42,
) -> tuple[float, float]:
    """Percentile bootstrap CI for ``mean(group2) - mean(group1)``.

    Phase 15 F1: vectorized via a single ``rng.choice`` call per group.
    The previous Python ``for`` loop drew ``a`` and ``b`` interleaved per
    iteration; the vectorized form draws all ``n_bootstrap`` rows for ``a``
    first, then ``b`` — so outputs differ from the pre-F1 implementation
    even at the same seed. The regression test in
    ``tests/unit/test_bootstrap_vectorized.py`` pins the post-F1 output for
    a fixed ``(a, b, seed)`` triple; any intentional change to the sampling
    or read-out (e.g. switching to percentile-t or BCa) must update those
    constants deliberately.
    """
    a = np.asarray(group1, dtype=float).ravel()
    b = np.asarray(group2, dtype=float).ravel()
    if a.size == 0 or b.size == 0:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    s1 = rng.choice(a, size=(n_bootstrap, a.size), replace=True).mean(axis=1)
    s2 = rng.choice(b, size=(n_bootstrap, b.size), replace=True).mean(axis=1)
    diffs = s2 - s1
    lo = float(np.percentile(diffs, 100 * alpha / 2))
    hi = float(np.percentile(diffs, 100 * (1 - alpha / 2)))
    return (lo, hi)


def _safe_pvalue(p: float) -> float:
    if p is None or not math.isfinite(float(p)):
        return 1.0
    return float(min(1.0, max(0.0, float(p))))


def hypothesis_test_is_bh_rankable(test: HypothesisTest) -> bool:
    """True iff ``test`` should enter BH / Bonferroni ranking (Phase 16 D4)."""
    if test.skipped_reason is not None:
        return False
    if test.degenerate:
        return False
    return math.isfinite(float(test.raw_p_value))


def compute_n_rankable_features_per_family(tests: list[HypothesisTest]) -> dict[str, int]:
    """Count distinct rankable features per stylometric family (Phase 16 D5).

    Used as the convergence ratio denominator: only families with at least one
    BH-rankable hypothesis row (finite raw *p*, not skipped, not degenerate)
    contribute an axis toward the eligible denominator.
    """
    # Local import avoids ``statistics → feature_families → changepoint → statistics``.
    from forensics.analysis.feature_families import family_for

    per_family: dict[str, set[str]] = defaultdict(set)
    for t in tests:
        if not hypothesis_test_is_bh_rankable(t):
            continue
        fam = family_for(t.feature_name)
        if fam == "unknown":
            continue
        per_family[fam].add(t.feature_name)
    return {fam: len(feats) for fam, feats in per_family.items()}


def _cohens_d_meta(
    group1: list[float] | np.ndarray,
    group2: list[float] | np.ndarray,
) -> tuple[float, bool]:
    """Cohen's *d* plus variance-degeneracy flag (Phase 16 D3)."""
    return _cohens_d_value_and_degenerate(group1, group2)


def _skipped_hypothesis_battery(
    *,
    feature_name: str,
    author_id: str,
    skipped_reason: str,
    n_pre: int,
    n_post: int,
    n_nan_dropped: int,
    enable_ks_test: bool,
) -> list[HypothesisTest]:
    """Welch + Mann–Whitney (+ optional KS) rows with NaN *p* placeholders (Phase 16 D2)."""
    nan = float("nan")
    ci = (nan, nan)
    prefixes: list[str] = ["welch_t", "mann_whitney"]
    if enable_ks_test:
        prefixes.append("ks_2samp")
    return [
        HypothesisTest(
            test_name=f"{prefix}_{feature_name}",
            feature_name=feature_name,
            author_id=author_id,
            raw_p_value=nan,
            corrected_p_value=nan,
            effect_size_cohens_d=0.0,
            confidence_interval_95=ci,
            significant=False,
            n_pre=n_pre,
            n_post=n_post,
            n_nan_dropped=n_nan_dropped,
            skipped_reason=skipped_reason,
            degenerate=False,
        )
        for prefix in prefixes
    ]


def _hypothesis_test(
    *,
    prefix: str,
    feature_name: str,
    author_id: str,
    raw_p: float,
    d: float,
    ci: tuple[float, float],
    n_pre: int,
    n_post: int,
    n_nan_dropped: int = 0,
    skipped_reason: str | None = None,
    degenerate: bool = False,
) -> HypothesisTest:
    """Single Welch / Mann–Whitney / KS row with shared effect size and CI (RF-SMELL-005)."""
    rp = float(raw_p)
    sp = _safe_pvalue(rp) if math.isfinite(rp) else float("nan")
    return HypothesisTest(
        test_name=f"{prefix}_{feature_name}",
        feature_name=feature_name,
        author_id=author_id,
        raw_p_value=sp,
        corrected_p_value=sp,
        effect_size_cohens_d=d,
        confidence_interval_95=ci,
        significant=False,
        n_pre=n_pre,
        n_post=n_post,
        n_nan_dropped=n_nan_dropped,
        skipped_reason=skipped_reason,
        degenerate=degenerate,
    )


def run_hypothesis_tests(
    feature_values: list[float],
    breakpoint_idx: int,
    feature_name: str,
    author_id: str,
    *,
    n_bootstrap: int = 1000,
    bootstrap_seed: int = 42,
    enable_ks_test: bool = False,
    hypothesis_min_segment_n: int = 10,
) -> list[HypothesisTest]:
    """Welch t and Mann–Whitney U at a candidate split index (KS opt-in).

    Phase 15 C1: KS is dropped from the default battery. Welch and Mann–Whitney
    already cover the location shifts the forensic analysis cares about, and
    KS overlaps Mann–Whitney enough that keeping it just inflates the BH FDR
    denominator with a correlated test (per-CP test count drops 3 → 2). Pass
    ``enable_ks_test=True`` to re-introduce the two-sample KS branch for
    replication runs that want distribution-shape detection.

    Phase 16 D2: NaN / non-finite values are dropped per segment before testing;
    insufficient finite mass after the drop yields explicit skipped rows with
    NaN *p* values rather than an empty list.
    """
    y = np.asarray(feature_values, dtype=float)
    n = int(y.size)
    if n < 4 or breakpoint_idx < 1 or breakpoint_idx >= n:
        return _skipped_hypothesis_battery(
            feature_name=feature_name,
            author_id=author_id,
            skipped_reason="invalid_breakpoint_or_short_series",
            n_pre=-1,
            n_post=-1,
            n_nan_dropped=0,
            enable_ks_test=enable_ks_test,
        )

    pre_all = y[:breakpoint_idx]
    post_all = y[breakpoint_idx:]
    pre_mask = np.isfinite(pre_all)
    post_mask = np.isfinite(post_all)
    n_drop_pre = int(pre_all.size - int(pre_mask.sum()))
    n_drop_post = int(post_all.size - int(post_mask.sum()))
    n_nan_dropped = n_drop_pre + n_drop_post
    if n_drop_pre or n_drop_post:
        logger.info(
            "hypothesis_tests: author=%s feature=%s dropped_nonfinite pre=%d post=%d",
            author_id,
            feature_name,
            n_drop_pre,
            n_drop_post,
        )

    pre = pre_all[pre_mask].astype(float).tolist()
    post = post_all[post_mask].astype(float).tolist()
    n_pre, n_post = len(pre), len(post)

    if n_pre < 2 or n_post < 2:
        return _skipped_hypothesis_battery(
            feature_name=feature_name,
            author_id=author_id,
            skipped_reason="insufficient_finite_values_per_segment",
            n_pre=n_pre,
            n_post=n_post,
            n_nan_dropped=n_nan_dropped,
            enable_ks_test=enable_ks_test,
        )

    if n_pre < hypothesis_min_segment_n or n_post < hypothesis_min_segment_n:
        return _skipped_hypothesis_battery(
            feature_name=feature_name,
            author_id=author_id,
            skipped_reason=f"insufficient_n_pre_or_post (min={hypothesis_min_segment_n})",
            n_pre=n_pre,
            n_post=n_post,
            n_nan_dropped=n_nan_dropped,
            enable_ks_test=enable_ks_test,
        )

    tests: list[HypothesisTest] = []

    _t_stat, p_welch = stats.ttest_ind(pre, post, equal_var=False)
    p_welch_f = float(p_welch)
    d, d_degenerate = _cohens_d_meta(pre, post)
    ci = bootstrap_ci(pre, post, n_bootstrap=n_bootstrap, seed=bootstrap_seed)
    welch_degenerate = (not math.isfinite(p_welch_f)) or d_degenerate
    tests.append(
        _hypothesis_test(
            prefix="welch_t",
            feature_name=feature_name,
            author_id=author_id,
            raw_p=p_welch_f,
            d=d,
            ci=ci,
            n_pre=n_pre,
            n_post=n_post,
            n_nan_dropped=n_nan_dropped,
            degenerate=welch_degenerate,
        )
    )

    try:
        _u_stat, p_mw = stats.mannwhitneyu(pre, post, alternative="two-sided")
    except ValueError:
        p_mw_f = float("nan")
        mw_degenerate = True
    else:
        p_mw_f = float(p_mw)
        mw_degenerate = d_degenerate
    if not mw_degenerate:
        mw_degenerate = not math.isfinite(p_mw_f)
    tests.append(
        _hypothesis_test(
            prefix="mann_whitney",
            feature_name=feature_name,
            author_id=author_id,
            raw_p=p_mw_f,
            d=d,
            ci=ci,
            n_pre=n_pre,
            n_post=n_post,
            n_nan_dropped=n_nan_dropped,
            degenerate=mw_degenerate,
        )
    )

    if enable_ks_test:
        _ks_stat, p_ks = stats.ks_2samp(pre, post)
        p_ks_f = float(p_ks)
        ks_deg = (not math.isfinite(p_ks_f)) or d_degenerate
        tests.append(
            _hypothesis_test(
                prefix="ks_2samp",
                feature_name=feature_name,
                author_id=author_id,
                raw_p=p_ks_f,
                d=d,
                ci=ci,
                n_pre=n_pre,
                n_post=n_post,
                n_nan_dropped=n_nan_dropped,
                degenerate=ks_deg,
            )
        )
    return tests


def apply_correction(
    tests: list[HypothesisTest],
    method: str = "benjamini_hochberg",
    alpha: float = 0.05,
) -> list[HypothesisTest]:
    """Assign Benjamini–Hochberg or Bonferroni adjusted *p* and significance (Phase 16 D4).

    Skipped rows (``skipped_reason`` set), degenerate rows, and non-finite raw
    *p* are excluded from the ranking step; their ``corrected_p_value`` is set
    to NaN and ``significant`` to False. The BH / Bonferroni denominator is
    ``len(rankable)`` rather than the full list length.
    """
    if not tests:
        return tests
    rank_idx = [i for i, t in enumerate(tests) if hypothesis_test_is_bh_rankable(t)]
    rankable = [tests[i] for i in rank_idx]
    if not rankable:
        return [
            t.model_copy(update={"corrected_p_value": float("nan"), "significant": False})
            for t in tests
        ]

    p_values = [t.raw_p_value for t in rankable]
    n_r = len(p_values)
    if method == "bonferroni":
        corrected = [min(float(p) * n_r, 1.0) for p in p_values]
    elif method == "benjamini_hochberg":
        order = sorted(range(n_r), key=lambda i: p_values[i])
        bh = [0.0] * n_r
        for rank, oi in enumerate(order, start=1):
            bh[oi] = min(float(p_values[oi]) * n_r / rank, 1.0)
        for k in range(n_r - 2, -1, -1):
            idx_k = order[k]
            idx_next = order[k + 1]
            bh[idx_k] = min(bh[idx_k], bh[idx_next])
        corrected = [min(c, 1.0) for c in bh]
    else:
        msg = f"Unknown correction method: {method!r}"
        raise ValueError(msg)

    corrected_rankable = [
        t.model_copy(update={"corrected_p_value": cp, "significant": cp < alpha})
        for t, cp in zip(rankable, corrected, strict=True)
    ]
    by_pos: dict[int, HypothesisTest] = dict(zip(rank_idx, corrected_rankable, strict=True))
    return [
        by_pos[i]
        if i in by_pos
        else t.model_copy(update={"corrected_p_value": float("nan"), "significant": False})
        for i, t in enumerate(tests)
    ]


def _bh_adjusted_pvalues(p_values: list[float]) -> list[float]:
    """Benjamini–Hochberg adjusted *p* in the same index order as ``p_values``."""
    n_r = len(p_values)
    order = sorted(range(n_r), key=lambda i: p_values[i])
    bh = [0.0] * n_r
    for rank, oi in enumerate(order, start=1):
        bh[oi] = min(float(p_values[oi]) * n_r / rank, 1.0)
    for k in range(n_r - 2, -1, -1):
        oi = order[k]
        oj = order[k + 1]
        bh[oi] = min(bh[oi], bh[oj])
    return [min(c, 1.0) for c in bh]


def _min_rankable_corrected_p(tests: list[HypothesisTest]) -> float | None:
    rankable_ps = [
        float(t.corrected_p_value)
        for t in tests
        if hypothesis_test_is_bh_rankable(t) and math.isfinite(float(t.corrected_p_value))
    ]
    return min(rankable_ps) if rankable_ps else None


def _cross_author_adjustments_for_family(
    fam: str,
    slug_map: dict[str, list[HypothesisTest]],
) -> dict[tuple[str, str], float]:
    entries: list[tuple[str, float]] = []
    for slug, ts in slug_map.items():
        m = _min_rankable_corrected_p(ts)
        if m is not None:
            entries.append((slug, m))
    out: dict[tuple[str, str], float] = {}
    n_r = len(entries)
    if n_r == 0:
        return out
    if n_r < 2:
        for slug, pmin in entries:
            out[(slug, fam)] = pmin
        return out
    slugs_order = [e[0] for e in entries]
    pvals = [e[1] for e in entries]
    bh_vals = _bh_adjusted_pvalues(pvals)
    for i, slug in enumerate(slugs_order):
        out[(slug, fam)] = bh_vals[i]
    return out


def apply_cross_author_correction(
    tests_by_slug: dict[str, list[HypothesisTest]],
) -> dict[str, list[HypothesisTest]]:
    """M-09 — second-pass BH on each family's across-author minima.

    For every stylometric family (see :func:`forensics.analysis.feature_families.family_for`),
    collects each author's minimum first-pass ``corrected_p_value`` among
    BH-rankable tests in that family, runs Benjamini–Hochberg across those
    author-level minima, then stamps ``cross_author_corrected_p`` on *all*
    hypothesis rows for that author × family with the adjusted value.

    Families with fewer than two contributing authors copy the lone minimum
    through unchanged (no cross-author inflation).
    """
    from forensics.analysis.feature_families import family_for

    inv_family: dict[str, dict[str, list[HypothesisTest]]] = defaultdict(lambda: defaultdict(list))
    for slug, tests in tests_by_slug.items():
        for t in tests:
            fam = family_for(t.feature_name)
            if fam == "unknown":
                continue
            inv_family[fam][slug].append(t)

    adjustments: dict[tuple[str, str], float] = {}
    for fam, slug_map in inv_family.items():
        adjustments.update(_cross_author_adjustments_for_family(fam, slug_map))

    out: dict[str, list[HypothesisTest]] = {}
    for slug, tests in tests_by_slug.items():
        new_tests: list[HypothesisTest] = []
        for t in tests:
            fam = family_for(t.feature_name)
            q = adjustments.get((slug, fam))
            new_tests.append(t.model_copy(update={"cross_author_corrected_p": q}))
        out[slug] = new_tests
    return out


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
