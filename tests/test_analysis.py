"""Phase 5: change-point detection, time-series helpers, and statistics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from forensics.analysis.changepoint import (
    PELT_FEATURE_COLUMNS,
    analyze_author_feature_changepoints,
    cohens_d,
    detect_bocpd,
    detect_pelt,
    find_convergence_windows,
)
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
    n = 250
    ramp = np.linspace(0.0, 2.0, n)
    noise = np.random.default_rng(0).normal(0.0, 0.05, n)
    signal = ramp + noise
    raw = detect_bocpd(signal, hazard_rate=1 / 40.0, threshold=0.02)
    probs_second = [p for t, p in raw if t > n // 2]
    probs_first = [p for t, p in raw if t <= n // 2]
    assert probs_second, f"expected BOCPD detections in second half, got {raw[:10]}"
    assert max(probs_second) >= max(probs_first or [0.0])


def test_cohens_d_calculation() -> None:
    rng = np.random.default_rng(1)
    a = rng.normal(0.0, 1.0, 80)
    b = rng.normal(2.0, 1.0, 80)
    d = cohens_d(a, b)
    assert 1.2 < d < 2.2


def test_convergence_window() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    names = [f"f{i}" for i in range(5)]
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
    wins = find_convergence_windows(cps, window_days=30, min_features=0.6, total_features=8)
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
            ArticleEmbedding(
                published_at=dt, embedding=np.ones(4, dtype=np.float32) * float(i)
            )
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
        pairs.append(
            ArticleEmbedding(published_at=base + timedelta(days=i), embedding=b + noise)
        )
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
