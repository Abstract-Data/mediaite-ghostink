"""Phase 5: change-point detection, time-series helpers, and statistics."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest
from scipy.special import logsumexp

from forensics.analysis.changepoint import (
    PELT_FEATURE_COLUMNS,
    analyze_author_feature_changepoints,
    cohens_d,
    detect_bocpd,
    detect_pelt,
)
from forensics.analysis.convergence import ConvergenceInput, compute_convergence_scores
from forensics.analysis.timeseries import (
    chow_test,
    compute_rolling_stats,
    cusum_test,
    stl_decompose,
)
from forensics.config.settings import AnalysisConfig, ForensicsSettings, ScrapingConfig
from forensics.models.analysis import ChangePoint


def _minimal_settings(methods: list[str]) -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(changepoint_methods=methods),
    )


def test_pelt_synthetic_mean_shift() -> None:
    rng = np.random.default_rng(42)
    before = rng.normal(0.0, 0.3, 100)
    after = rng.normal(3.0, 0.3, 100)
    signal = np.concatenate([before, after])
    bps = detect_pelt(signal, pen=2.0)
    assert bps, "expected at least one breakpoint"
    assert any(95 <= b <= 105 for b in bps), f"break near index 100, got {bps}"


def test_pelt_no_change() -> None:
    signal = np.ones(200, dtype=float) * 4.2
    bps = detect_pelt(signal, pen=10.0)
    assert bps == []


def test_bocpd_gradual_shift() -> None:
    """Phase 15 A: legacy ``p_r0_legacy`` mode preserved for replication.

    The MAP-reset rule is exercised in ``tests/unit/test_bocpd_semantics.py``;
    this test pins the historical low-threshold-on-``P(r=0)`` behavior so the
    rollback flag remains a true byte-for-byte fallback.
    """
    n = 250
    ramp = np.linspace(0.0, 2.0, n)
    noise = np.random.default_rng(0).normal(0.0, 0.05, n)
    signal = ramp + noise
    raw = detect_bocpd(
        signal,
        hazard_rate=1 / 40.0,
        mode="p_r0_legacy",
        threshold=0.02,
        student_t=False,
    )
    probs_second = [p for t, p in raw if t > n // 2]
    probs_first = [p for t, p in raw if t <= n // 2]
    assert probs_second, f"expected BOCPD detections in second half, got {raw[:10]}"
    assert max(probs_second) >= max(probs_first or [0.0])


def _detect_bocpd_scalar_reference(
    signal: np.ndarray,
    hazard_rate: float = 1 / 250.0,
    threshold: float = 0.5,
) -> list[tuple[int, float]]:
    """O(n²) reference matching :func:`detect_bocpd` inner segment loop (for parity tests)."""
    x = np.asarray(signal, dtype=float).ravel()
    n = len(x)
    if n < 6:
        return []

    sigma2 = float(np.var(x[: min(80, n)]))
    if sigma2 < 1e-12:
        sigma2 = 1e-12
    inv_sig2 = 1.0 / sigma2
    mu0 = float(np.mean(x[: min(10, n)]))
    v0 = sigma2 * 4.0
    inv_v0 = 1.0 / v0
    log_h = float(np.log(hazard_rate))
    log_1mh = float(np.log(max(1e-12, 1.0 - hazard_rate)))

    log_pi = np.array([0.0])
    changepoints: list[tuple[int, float]] = []
    cumsum = np.concatenate((np.zeros(1, dtype=float), np.cumsum(x, dtype=float)))

    for t in range(1, n):
        xt = x[t]
        max_s = t
        log_pi = np.asarray(log_pi, dtype=float)
        if log_pi.size < max_s:
            log_pi = np.concatenate([log_pi, np.full(max_s - log_pi.size, -np.inf)])

        log_preds = np.empty(max_s, dtype=float)
        for s in range(1, max_s + 1):
            sum_s = float(cumsum[t] - cumsum[t - s])
            length = float(s)
            inv_v = inv_v0 + length * inv_sig2
            m = (inv_v0 * mu0 + inv_sig2 * sum_s) / inv_v
            var_pred = 1.0 / inv_v + sigma2
            log_preds[s - 1] = -0.5 * (np.log(2 * np.pi * var_pred) + (xt - m) ** 2 / var_pred)

        log_evidence = logsumexp(log_pi[:max_s] + log_preds)
        log_pi_new = np.full(t + 1, -np.inf)
        log_pi_new[0] = log_h + log_evidence
        log_pi_new[1 : t + 1] = log_1mh + log_pi[:t] + log_preds[:t]
        log_pi_new -= logsumexp(log_pi_new)
        log_pi = log_pi_new

        p_cp = float(np.exp(log_pi_new[0]))
        if p_cp >= threshold:
            changepoints.append((t, p_cp))

    return changepoints


@pytest.mark.parametrize("seed", [0, 1, 2, 42])
def test_bocpd_vectorized_matches_reference(seed: int) -> None:
    """Vectorized BOCPD parity vs. the O(n²) scalar reference.

    Pinned to ``mode="p_r0_legacy"`` and ``student_t=False`` because the
    reference implements exactly the Normal-known-σ² + ``P(r=0)`` threshold
    path. The new MAP-reset / Student-t paths are covered by the dedicated
    semantics suite under ``tests/unit/test_bocpd_semantics.py``.
    """
    rng = np.random.default_rng(seed)
    for n in (24, 48, 80):
        signal = rng.normal(0.0, 1.0, n).astype(float)
        for hazard in (1 / 80.0, 1 / 250.0):
            for th in (0.15, 0.5):
                got = detect_bocpd(
                    signal,
                    hazard_rate=hazard,
                    mode="p_r0_legacy",
                    threshold=th,
                    student_t=False,
                )
                ref = _detect_bocpd_scalar_reference(signal, hazard_rate=hazard, threshold=th)
                assert got == ref, f"mismatch seed={seed} n={n} h={hazard} th={th}"


@pytest.mark.slow
def test_bocpd_long_signal_runs_quickly() -> None:
    """Vectorized BOCPD stays practical on longer series (skipped in default CI; no O(n²) ref)."""
    rng = np.random.default_rng(99)
    n = 4000
    signal = rng.normal(0.0, 0.5, n)
    t0 = time.perf_counter()
    out = detect_bocpd(
        signal,
        hazard_rate=1 / 500.0,
        mode="p_r0_legacy",
        threshold=0.55,
        student_t=False,
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"BOCPD too slow: {elapsed:.2f}s for n={n}"
    assert isinstance(out, list)


def test_cohens_d_calculation() -> None:
    rng = np.random.default_rng(1)
    a = rng.normal(0.0, 1.0, 80)
    b = rng.normal(2.0, 1.0, 80)
    d = cohens_d(a, b)
    assert 1.2 < d < 2.2


def test_convergence_window() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    # Phase 15 B2: feature names must belong to the FEATURE_FAMILIES registry.
    # Pick one feature per distinct family so ratio = 5/8 clears min_feature_ratio=0.6.
    names = [
        "ttr",  # lexical_richness
        "flesch_kincaid",  # readability
        "sent_length_mean",  # sentence_structure
        "bigram_entropy",  # entropy
        "self_similarity_30d",  # self_similarity
    ]
    cps = [
        ChangePoint(
            feature_name=names[i],
            author_id="a1",
            timestamp=base + timedelta(days=i * 5),
            confidence=0.9,
            method="pelt",
            effect_size_cohens_d=0.8,
            direction="increase",
        )
        for i in range(5)
    ]
    wins = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=30,
            min_feature_ratio=0.6,
            total_feature_count=8,
        )
    )
    assert wins
    assert len(wins[0].features_converging) == 5


def test_chow_test_significant() -> None:
    t = np.arange(120, dtype=float)
    y = np.concatenate([0.1 * t[:60], 10.0 + 0.5 * (t[60:] - 60)])
    f_stat, p_val = chow_test(y.tolist(), 60)
    assert p_val < 0.05
    assert f_stat > 1.0


def test_chow_test_null() -> None:
    rng = np.random.default_rng(3)
    y = rng.normal(0.0, 1.0, 100).tolist()
    _f, p_val = chow_test(y, 50)
    assert p_val > 0.01


def test_cusum_persistent_shift() -> None:
    y = np.concatenate([np.zeros(40), np.ones(40) * 5.0]).tolist()
    hits = cusum_test(y, threshold=2.0)
    assert hits
    assert hits[0][0] >= 35


def test_rolling_stats_output_shape() -> None:
    base = datetime(2024, 6, 1, tzinfo=UTC)
    ts = [base + timedelta(days=i) for i in range(15)]
    vals = list(range(15))
    out = compute_rolling_stats(ts, vals, windows=[5, 7])
    assert len(out[5]["mean"]) == 15
    assert len(out[7]["std"]) == 15


def test_stl_decomposition() -> None:
    n = 120
    t = np.arange(n, dtype=float)
    trend = 0.02 * t
    seasonal = 2.0 * np.sin(2 * np.pi * t / 30.0)
    y = (trend + seasonal).tolist()
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = [base + timedelta(days=int(i)) for i in range(n)]
    comp = stl_decompose(ts, y, period=30)
    recon = np.array(comp["trend"]) + np.array(comp["seasonal"]) + np.array(comp["residual"])
    corr = np.corrcoef(np.array(y), recon)[0, 1]
    assert corr > 0.85


def test_analyze_author_feature_changepoints_runs() -> None:
    n = 40
    base = datetime(2023, 1, 1, tzinfo=UTC)
    rows = {
        "article_id": [f"art{i}" for i in range(n)],
        "author_id": ["auth1"] * n,
        "timestamp": [base + timedelta(days=i) for i in range(n)],
    }
    for col in PELT_FEATURE_COLUMNS:
        rows[col] = np.linspace(1.0, 2.0, n) + np.random.default_rng(4).normal(0, 0.02, n)
    df = pl.DataFrame(rows)
    settings = _minimal_settings(["pelt"])
    cps = analyze_author_feature_changepoints(df, author_id="auth1", settings=settings)
    assert isinstance(cps, list)


@pytest.mark.parametrize("fname", ["get_rolling_feature_comparison", "get_monthly_feature_stats"])
def test_duckdb_queries_importable(fname: str) -> None:
    mod = __import__("forensics.storage.duckdb_queries", fromlist=[fname])
    assert callable(getattr(mod, fname))


def test_analysis_stub_modules_importable() -> None:
    import forensics.analysis.comparison  # noqa: F401
    import forensics.analysis.convergence  # noqa: F401
    import forensics.analysis.drift  # noqa: F401
    import forensics.analysis.orchestrator  # noqa: F401
    import forensics.analysis.statistics  # noqa: F401


# --- Phase 6: embedding drift ---


def test_monthly_centroids() -> None:
    from forensics.analysis.drift import ArticleEmbedding, compute_monthly_centroids

    stamps = [
        datetime(2024, 1, 5, tzinfo=UTC),
        datetime(2024, 1, 25, tzinfo=UTC),
        datetime(2024, 2, 3, tzinfo=UTC),
        datetime(2024, 2, 18, tzinfo=UTC),
        datetime(2024, 3, 1, tzinfo=UTC),
        datetime(2024, 3, 22, tzinfo=UTC),
    ]
    pairs: list[ArticleEmbedding] = []
    for i, dt in enumerate(stamps):
        pairs.append(
            ArticleEmbedding(published_at=dt, embedding=np.ones(4, dtype=np.float32) * float(i))
        )
    out = compute_monthly_centroids(pairs)
    assert len(out) == 3
    for _m, c in out:
        assert c.shape == (4,)


def test_centroid_velocity_stationary() -> None:
    from forensics.analysis.drift import track_centroid_velocity

    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    cents = [("2024-01", v.copy()), ("2024-02", v.copy()), ("2024-03", v.copy())]
    vel = track_centroid_velocity(cents)
    assert len(vel) == 2
    assert all(abs(x) < 1e-6 for x in vel)


def test_centroid_velocity_drift() -> None:
    from forensics.analysis.drift import track_centroid_velocity

    cents = [
        ("2024-01", np.array([1.0, 0.0, 0.0], dtype=np.float32)),
        ("2024-02", np.array([1.0, 0.3, 0.0], dtype=np.float32)),
        ("2024-03", np.array([1.0, 0.9, 0.0], dtype=np.float32)),
    ]
    vel = track_centroid_velocity(cents)
    assert len(vel) == 2
    assert vel[1] > vel[0]


def test_baseline_similarity_stable() -> None:
    from forensics.analysis.drift import ArticleEmbedding, compute_baseline_similarity_curve

    base = datetime(2024, 1, 1, tzinfo=UTC)
    e = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    pairs = [
        ArticleEmbedding(published_at=base + timedelta(days=i), embedding=e.copy())
        for i in range(5)
    ]
    curve = compute_baseline_similarity_curve(pairs, baseline_count=3)
    assert len(curve) == 5
    assert all(abs(s - 1.0) < 1e-5 for _, s in curve)


def test_baseline_similarity_drift() -> None:
    from forensics.analysis.drift import ArticleEmbedding, compute_baseline_similarity_curve

    base = datetime(2024, 1, 1, tzinfo=UTC)
    b = np.array([1.0, 0.0], dtype=np.float32)
    pairs = []
    for i in range(10):
        noise = np.array([0.0, float(i) * 0.2], dtype=np.float32)
        pairs.append(ArticleEmbedding(published_at=base + timedelta(days=i), embedding=b + noise))
    curve = compute_baseline_similarity_curve(pairs, baseline_count=3)
    assert curve[0][1] >= curve[-1][1]


def test_intra_variance_uniform() -> None:
    from forensics.analysis.drift import ArticleEmbedding, compute_intra_period_variance

    base = datetime(2024, 3, 1, tzinfo=UTC)
    v = np.ones(5, dtype=np.float32)
    pairs = [
        ArticleEmbedding(published_at=base, embedding=v),
        ArticleEmbedding(published_at=base + timedelta(days=1), embedding=v.copy()),
        ArticleEmbedding(published_at=base + timedelta(days=2), embedding=v.copy()),
    ]
    out = compute_intra_period_variance(pairs, period="month")
    assert out[0][0] == "2024-03"
    assert out[0][1] == 0.0


def test_ai_convergence_signal() -> None:
    from forensics.analysis.drift import compute_ai_convergence

    ai = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    ai_emb = [ai, ai + 0.01]
    months = []
    for k in range(4):
        t = 0.2 * k
        c = np.array([0.0, 1.0, 0.0], dtype=np.float64) * (1 - t) + ai * t
        months.append((f"2024-0{k + 1}", c))
    conv = compute_ai_convergence(months, ai_emb)
    sims = [s for _, s in conv]
    assert sims[-1] > sims[0]


def test_ai_convergence_null() -> None:
    from forensics.analysis.drift import compute_ai_convergence

    rng = np.random.default_rng(42)
    ai = rng.normal(size=6)
    ai_emb = [ai, ai + 0.01]
    months = [(f"2024-{i:02d}", rng.normal(size=6)) for i in range(1, 7)]
    conv = compute_ai_convergence(months, ai_emb)
    assert len(conv) == 6


def test_umap_output_shape() -> None:
    from forensics.analysis.drift import generate_umap_projection

    rng = np.random.default_rng(7)
    cents = [(f"2024-{i:02d}", rng.normal(size=12).astype(np.float32)) for i in range(1, 6)]
    out = generate_umap_projection({"a1": cents})
    assert "a1" in out["projections"]
    assert len(out["projections"]["a1"]) == 5
    for row in out["projections"]["a1"]:
        assert "x" in row and "y" in row


def test_drift_scores_assembly() -> None:
    from forensics.analysis.drift import compute_drift_scores

    base = datetime(2024, 1, 1, tzinfo=UTC)
    curve = [(base + timedelta(days=i), 1.0 - 0.01 * i) for i in range(3)]
    ai_c = [("2024-01", 0.1), ("2024-02", 0.5)]
    ds = compute_drift_scores(
        "author-1",
        curve,
        ai_c,
        [0.01, 0.02],
        [("2024-01", 0.3), ("2024-02", 0.2)],
    )
    assert ds.author_id == "author-1"
    assert abs(ds.baseline_centroid_similarity - curve[-1][1]) < 1e-9
    assert ds.ai_baseline_similarity == 0.5
    assert ds.monthly_centroid_velocities == [0.01, 0.02]
    assert ds.intra_period_variance_trend == [0.3, 0.2]


def test_drift_scores_ai_baseline_none_when_no_convergence() -> None:
    """Without an AI baseline, ai_baseline_similarity must be None — not 0.0.

    Distinguishes "no measurement" from a real zero convergence reading.
    """
    from forensics.analysis.drift import compute_drift_scores

    base = datetime(2024, 1, 1, tzinfo=UTC)
    curve = [(base + timedelta(days=i), 1.0 - 0.01 * i) for i in range(3)]

    ds_none = compute_drift_scores(
        "author-1",
        curve,
        None,
        [0.01, 0.02],
        [("2024-01", 0.3)],
    )
    assert ds_none.ai_baseline_similarity is None

    ds_empty = compute_drift_scores(
        "author-1",
        curve,
        [],
        [0.01, 0.02],
        [("2024-01", 0.3)],
    )
    assert ds_empty.ai_baseline_similarity is None


def test_extract_lda_topic_keywords_runs() -> None:
    from forensics.baseline.topics import extract_lda_topic_keywords

    texts = [
        "The senate voted today on climate policy and energy reform.",
        "Congress debates healthcare funding and hospital budgets this week.",
        "The president spoke about foreign policy and trade agreements abroad.",
        "Local elections saw high turnout in the school board race downtown.",
        "Stocks rose as investors weighed inflation data and interest rates.",
        "The governor announced infrastructure spending for roads and bridges.",
        "Scientists published findings on vaccines and public health outcomes.",
        "The team won the championship after a strong defensive performance.",
    ] * 3
    topics = extract_lda_topic_keywords(texts, num_topics=4, n_keywords=5, random_state=0)
    assert topics
    assert all(len(kws) == 5 for _tid, kws, _s in topics)
