"""Phase 5: change-point detection, time-series helpers, and statistics."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

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
    from forensics.analysis.drift import compute_monthly_centroids

    stamps = [
        datetime(2024, 1, 5, tzinfo=UTC),
        datetime(2024, 1, 25, tzinfo=UTC),
        datetime(2024, 2, 3, tzinfo=UTC),
        datetime(2024, 2, 18, tzinfo=UTC),
        datetime(2024, 3, 1, tzinfo=UTC),
        datetime(2024, 3, 22, tzinfo=UTC),
    ]
    pairs: list[tuple[datetime, np.ndarray]] = []
    for i, dt in enumerate(stamps):
        pairs.append((dt, np.ones(4, dtype=np.float32) * float(i)))
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
    from forensics.analysis.drift import compute_baseline_similarity_curve

    base = datetime(2024, 1, 1, tzinfo=UTC)
    e = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    pairs = [(base + timedelta(days=i), e.copy()) for i in range(5)]
    curve = compute_baseline_similarity_curve(pairs, baseline_count=3)
    assert len(curve) == 5
    assert all(abs(s - 1.0) < 1e-5 for _, s in curve)


def test_baseline_similarity_drift() -> None:
    from forensics.analysis.drift import compute_baseline_similarity_curve

    base = datetime(2024, 1, 1, tzinfo=UTC)
    b = np.array([1.0, 0.0], dtype=np.float32)
    pairs = []
    for i in range(10):
        noise = np.array([0.0, float(i) * 0.2], dtype=np.float32)
        pairs.append((base + timedelta(days=i), b + noise))
    curve = compute_baseline_similarity_curve(pairs, baseline_count=3)
    assert curve[0][1] >= curve[-1][1]


def test_intra_variance_uniform() -> None:
    from forensics.analysis.drift import compute_intra_period_variance

    base = datetime(2024, 3, 1, tzinfo=UTC)
    v = np.ones(5, dtype=np.float32)
    pairs = [(base, v), (base + timedelta(days=1), v.copy()), (base + timedelta(days=2), v.copy())]
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


# --- Phase 7: convergence, statistics, comparison ---


def test_convergence_scoring() -> None:
    from forensics.analysis.convergence import compute_convergence_scores
    from forensics.models.analysis import ChangePoint

    base = datetime(2024, 1, 10, tzinfo=UTC)
    names = [f"f{i}" for i in range(5)]
    cps = [
        ChangePoint(
            feature_name=names[i],
            author_id="a1",
            timestamp=base + timedelta(days=i * 3),
            confidence=0.9,
            method="pelt",
            effect_size_cohens_d=0.9,
            direction="increase",
        )
        for i in range(4)
    ]
    vels = [(f"2024-0{i}", 0.5 + i * 0.4) for i in range(1, 5)]
    sim_curve = [(base + timedelta(days=d), 1.0 - 0.02 * d) for d in range(0, 120, 7)]
    wins = compute_convergence_scores(
        cps,
        vels,
        sim_curve,
        window_days=90,
        min_feature_ratio=0.6,
        total_feature_count=5,
    )
    assert wins, "expected convergence window when 4/5 features align"


def test_convergence_below_threshold() -> None:
    from forensics.analysis.convergence import compute_convergence_scores
    from forensics.models.analysis import ChangePoint

    base = datetime(2024, 1, 10, tzinfo=UTC)
    names = [f"f{i}" for i in range(5)]
    cps = [
        ChangePoint(
            feature_name=names[i],
            author_id="a1",
            timestamp=base + timedelta(days=i * 3),
            confidence=0.5,
            method="pelt",
            effect_size_cohens_d=0.2,
            direction="increase",
        )
        for i in range(2)
    ]
    wins = compute_convergence_scores(
        cps,
        [],
        [],
        window_days=90,
        min_feature_ratio=0.6,
        total_feature_count=5,
    )
    assert wins == []


def test_welch_t_significant() -> None:
    from scipy import stats

    rng = np.random.default_rng(11)
    pre = rng.normal(0.0, 0.4, 60)
    post = rng.normal(2.5, 0.4, 60)
    t_stat, p_val = stats.ttest_ind(pre, post, equal_var=False)
    assert p_val < 0.05
    assert abs(float(t_stat)) > 1.0


def test_welch_t_null() -> None:
    from scipy import stats

    rng = np.random.default_rng(12)
    pre = rng.normal(0.0, 1.0, 80)
    post = rng.normal(0.05, 1.0, 80)
    _t, p_val = stats.ttest_ind(pre, post, equal_var=False)
    assert p_val > 0.05


def test_cohens_d_large() -> None:
    from forensics.analysis.statistics import cohens_d

    rng = np.random.default_rng(13)
    d = cohens_d(rng.normal(0, 0.2, 100).tolist(), rng.normal(3.0, 0.2, 100).tolist())
    assert d > 0.8


def test_cohens_d_negligible() -> None:
    from forensics.analysis.statistics import cohens_d

    rng = np.random.default_rng(14)
    x = rng.normal(1.0, 0.5, 200)
    d = cohens_d(x.tolist(), (x + 0.02).tolist())
    assert abs(d) < 0.2


def test_bootstrap_ci_contains_true_diff() -> None:
    from forensics.analysis.statistics import bootstrap_ci

    rng = np.random.default_rng(15)
    g1 = rng.normal(0.0, 0.3, 80)
    g2 = rng.normal(2.0, 0.3, 80)
    lo, hi = bootstrap_ci(g1.tolist(), g2.tolist(), n_bootstrap=800, seed=0)
    true_diff = 2.0
    assert lo <= true_diff <= hi


def test_bonferroni_correction() -> None:
    from forensics.analysis.statistics import apply_correction
    from forensics.models.analysis import HypothesisTest

    tests = [
        HypothesisTest(
            test_name=f"t{i}",
            feature_name="f",
            author_id="a",
            raw_p_value=0.0004,
            corrected_p_value=0.0004,
            effect_size_cohens_d=1.0,
            confidence_interval_95=(0.0, 0.0),
            significant=False,
        )
        for i in range(100)
    ]
    apply_correction(tests, method="bonferroni", alpha=0.05)
    assert tests[0].corrected_p_value < 0.05
    tests2 = [
        HypothesisTest(
            test_name=f"t{i}",
            feature_name="f",
            author_id="a",
            raw_p_value=0.0006,
            corrected_p_value=0.0006,
            effect_size_cohens_d=1.0,
            confidence_interval_95=(0.0, 0.0),
            significant=False,
        )
        for i in range(100)
    ]
    apply_correction(tests2, method="bonferroni", alpha=0.05)
    assert tests2[0].corrected_p_value > 0.05


def test_benjamini_hochberg() -> None:
    from forensics.analysis.statistics import apply_correction
    from forensics.models.analysis import HypothesisTest

    raw_ps = [0.01, 0.02, 0.06, 0.04]
    tests = [
        HypothesisTest(
            test_name=f"t{i}",
            feature_name="f",
            author_id="a",
            raw_p_value=p,
            corrected_p_value=p,
            effect_size_cohens_d=0.6,
            confidence_interval_95=(0.0, 0.0),
            significant=False,
        )
        for i, p in enumerate(raw_ps)
    ]
    apply_correction(tests, method="benjamini_hochberg", alpha=0.05)
    assert all(t.corrected_p_value >= t.raw_p_value for t in tests)


def test_control_comparison_editorial() -> None:
    from datetime import date

    from forensics.analysis.comparison import compute_signal_attribution
    from forensics.models.analysis import ConvergenceWindow

    tw = [
        ConvergenceWindow(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 1),
            features_converging=["a"],
            convergence_ratio=0.7,
            pipeline_a_score=0.8,
            pipeline_b_score=0.8,
        )
    ]
    cw = {
        "c1": [
            ConvergenceWindow(
                start_date=date(2024, 1, 15),
                end_date=date(2024, 2, 15),
                features_converging=["a"],
                convergence_ratio=0.7,
                pipeline_a_score=0.8,
                pipeline_b_score=0.8,
            )
        ],
        "c2": [
            ConvergenceWindow(
                start_date=date(2024, 1, 20),
                end_date=date(2024, 2, 20),
                features_converging=["a"],
                convergence_ratio=0.7,
                pipeline_a_score=0.8,
                pipeline_b_score=0.8,
            )
        ],
    }
    s = compute_signal_attribution(tw, cw)
    assert s < 0.4


def test_control_comparison_author_specific() -> None:
    from datetime import date

    from forensics.analysis.comparison import compute_signal_attribution
    from forensics.models.analysis import ConvergenceWindow

    tw = [
        ConvergenceWindow(
            start_date=date(2024, 6, 1),
            end_date=date(2024, 8, 1),
            features_converging=["a"],
            convergence_ratio=0.7,
            pipeline_a_score=0.8,
            pipeline_b_score=0.8,
        )
    ]
    cw = {
        "c1": [
            ConvergenceWindow(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                features_converging=["b"],
                convergence_ratio=0.2,
                pipeline_a_score=0.1,
                pipeline_b_score=0.1,
            )
        ],
    }
    s = compute_signal_attribution(tw, cw)
    assert s > 0.7


def test_analysis_result_serialization() -> None:
    from datetime import date

    from forensics.models.analysis import (
        AnalysisResult,
        ChangePoint,
        ConvergenceWindow,
        HypothesisTest,
    )

    cp = ChangePoint(
        feature_name="ttr",
        author_id="aid",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        confidence=0.5,
        method="pelt",
        effect_size_cohens_d=0.5,
        direction="increase",
    )
    win = ConvergenceWindow(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 1),
        features_converging=["ttr"],
        convergence_ratio=0.2,
        pipeline_a_score=0.3,
        pipeline_b_score=0.4,
        pipeline_c_score=None,
    )
    ht = HypothesisTest(
        test_name="welch_t_ttr",
        feature_name="ttr",
        author_id="aid",
        raw_p_value=0.01,
        corrected_p_value=0.02,
        effect_size_cohens_d=0.6,
        confidence_interval_95=(-0.1, 0.5),
        significant=True,
    )
    ar = AnalysisResult(
        author_id="aid",
        run_timestamp=datetime.now(UTC),
        config_hash="abc123",
        change_points=[cp],
        convergence_windows=[win],
        drift_scores=None,
        hypothesis_tests=[ht],
    )
    raw = ar.model_dump(mode="json")
    ar2 = AnalysisResult.model_validate(raw)
    assert ar2.author_id == ar.author_id
    assert len(ar2.hypothesis_tests) == 1


@pytest.mark.asyncio
async def test_full_analysis_integration(tmp_path: Path) -> None:
    import polars as pl

    from forensics.analysis.orchestrator import run_full_analysis
    from forensics.config.settings import (
        AnalysisConfig,
        AuthorConfig,
        ForensicsSettings,
        ScrapingConfig,
    )
    from forensics.models.author import Author
    from forensics.storage.repository import Repository, init_db

    db_path = tmp_path / "articles.db"
    init_db(db_path)
    auth = Author(
        name="Test",
        slug="test-author",
        outlet="x",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2024, 1, 1),
        archive_url="https://example.com",
    )
    with Repository(db_path) as repo:
        repo.upsert_author(auth)

    n = 50
    base = datetime(2024, 1, 1, tzinfo=UTC)
    rows: dict = {
        "article_id": [f"a{i}" for i in range(n)],
        "author_id": [auth.id] * n,
        "timestamp": [base + timedelta(days=i) for i in range(n)],
    }
    for col in PELT_FEATURE_COLUMNS:
        rows[col] = np.linspace(0.0, 1.0, n) + np.random.default_rng(20).normal(0, 0.05, n)
    feat_dir = tmp_path / "features"
    feat_dir.mkdir()
    pl.DataFrame(rows).write_parquet(feat_dir / f"{auth.slug}.parquet")

    settings = ForensicsSettings(
        authors=[
            AuthorConfig(
                name=auth.name,
                slug=auth.slug,
                role="target",
                archive_url=auth.archive_url,
                baseline_start=auth.baseline_start,
                baseline_end=auth.baseline_end,
            )
        ],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(changepoint_methods=["pelt"]),
    )

    out = await run_full_analysis(
        db_path,
        feat_dir,
        tmp_path / "embeddings",
        settings,
        project_root=tmp_path,
        author_slug=auth.slug,
    )
    assert auth.slug in out
    assert (tmp_path / "data" / "analysis" / f"{auth.slug}_result.json").is_file()


def test_effect_size_filter() -> None:
    from forensics.analysis.statistics import apply_correction, filter_by_effect_size
    from forensics.models.analysis import HypothesisTest

    t = HypothesisTest(
        test_name="welch_t_x",
        feature_name="x",
        author_id="a",
        raw_p_value=0.01,
        corrected_p_value=0.01,
        effect_size_cohens_d=0.3,
        confidence_interval_95=(0.0, 0.0),
        significant=False,
    )
    apply_correction([t], method="bonferroni", alpha=0.05)
    filter_by_effect_size([t], min_d=0.5, alpha=0.05)
    assert not t.significant


def test_finding_strength_strong() -> None:
    from datetime import date

    from forensics.models.analysis import ConvergenceWindow, HypothesisTest
    from forensics.models.report import FindingStrength, classify_finding_strength

    win = ConvergenceWindow(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 1),
        features_converging=["a", "b", "c"],
        convergence_ratio=0.8,
        pipeline_a_score=0.9,
        pipeline_b_score=0.9,
        pipeline_c_score=0.6,
    )
    tests = [
        HypothesisTest(
            test_name=f"w{i}",
            feature_name=f"f{i}",
            author_id="a",
            raw_p_value=0.001,
            corrected_p_value=0.005,
            effect_size_cohens_d=0.9,
            confidence_interval_95=(0.0, 0.0),
            significant=True,
        )
        for i in range(3)
    ]
    ctrl = {"editorial_vs_author_signal": 0.85}
    assert classify_finding_strength(win, tests, ctrl) == FindingStrength.STRONG


def test_finding_strength_moderate() -> None:
    from datetime import date

    from forensics.models.analysis import ConvergenceWindow, HypothesisTest
    from forensics.models.report import FindingStrength, classify_finding_strength

    win = ConvergenceWindow(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 1),
        features_converging=["a", "b"],
        convergence_ratio=0.5,
        pipeline_a_score=0.4,
        pipeline_b_score=0.4,
    )
    tests = [
        HypothesisTest(
            test_name="w1",
            feature_name="f1",
            author_id="a",
            raw_p_value=0.02,
            corrected_p_value=0.03,
            effect_size_cohens_d=0.6,
            confidence_interval_95=(0.0, 0.0),
            significant=True,
        ),
        HypothesisTest(
            test_name="w2",
            feature_name="f2",
            author_id="a",
            raw_p_value=0.02,
            corrected_p_value=0.03,
            effect_size_cohens_d=0.55,
            confidence_interval_95=(0.0, 0.0),
            significant=True,
        ),
    ]
    assert (
        classify_finding_strength(win, tests, {"editorial_vs_author_signal": 0.1})
        == FindingStrength.MODERATE
    )


def test_finding_strength_weak() -> None:
    from datetime import date

    from forensics.models.analysis import ConvergenceWindow, HypothesisTest
    from forensics.models.report import FindingStrength, classify_finding_strength

    win = ConvergenceWindow(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 1),
        features_converging=["a"],
        convergence_ratio=0.2,
        pipeline_a_score=0.2,
        pipeline_b_score=0.2,
    )
    tests = [
        HypothesisTest(
            test_name="w1",
            feature_name="f1",
            author_id="a",
            raw_p_value=0.02,
            corrected_p_value=0.03,
            effect_size_cohens_d=0.6,
            confidence_interval_95=(0.0, 0.0),
            significant=True,
        ),
    ]
    assert classify_finding_strength(win, tests, {}) == FindingStrength.WEAK


def test_finding_strength_none() -> None:
    from datetime import date

    from forensics.models.analysis import ConvergenceWindow, HypothesisTest
    from forensics.models.report import FindingStrength, classify_finding_strength

    win = ConvergenceWindow(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 1),
        features_converging=[],
        convergence_ratio=0.0,
        pipeline_a_score=0.0,
        pipeline_b_score=0.0,
    )
    tests = [
        HypothesisTest(
            test_name="w1",
            feature_name="f1",
            author_id="a",
            raw_p_value=0.5,
            corrected_p_value=0.9,
            effect_size_cohens_d=0.1,
            confidence_interval_95=(0.0, 0.0),
            significant=False,
        ),
    ]
    assert classify_finding_strength(win, tests, {}) == FindingStrength.NONE


def test_apply_correction_empty_and_bad_method() -> None:
    from forensics.analysis.statistics import apply_correction
    from forensics.models.analysis import HypothesisTest

    assert apply_correction([], method="benjamini_hochberg") == []
    t = HypothesisTest(
        test_name="x",
        feature_name="f",
        author_id="a",
        raw_p_value=0.1,
        corrected_p_value=0.1,
        effect_size_cohens_d=0.0,
        confidence_interval_95=(0.0, 0.0),
        significant=False,
    )
    with pytest.raises(ValueError, match="Unknown correction"):
        apply_correction([t], method="not_a_method")  # type: ignore[arg-type]


def test_compare_target_to_controls_minimal(tmp_path: Path) -> None:
    from forensics.analysis.comparison import compare_target_to_controls
    from forensics.config.settings import (
        AnalysisConfig,
        AuthorConfig,
        ForensicsSettings,
        ScrapingConfig,
    )
    from forensics.models.author import Author
    from forensics.storage.repository import Repository, init_db

    db = tmp_path / "db.sqlite"
    init_db(db)
    tgt = Author(
        name="T",
        slug="target-a",
        outlet="o",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2024, 1, 1),
        archive_url="https://example.com",
    )
    ctl = Author(
        name="C",
        slug="control-a",
        outlet="o",
        role="control",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2024, 1, 1),
        archive_url="https://example.com",
    )
    with Repository(db) as repo:
        repo.upsert_author(tgt)
        repo.upsert_author(ctl)

    n = 30
    base = datetime(2024, 1, 1, tzinfo=UTC)
    feat_dir = tmp_path / "features"
    feat_dir.mkdir()
    rows_t = {
        "article_id": [f"t{i}" for i in range(n)],
        "author_id": [tgt.id] * n,
        "timestamp": [base + timedelta(days=i) for i in range(n)],
    }
    rows_c = {
        "article_id": [f"c{i}" for i in range(n)],
        "author_id": [ctl.id] * n,
        "timestamp": [base + timedelta(days=i) for i in range(n)],
    }
    for col in ("ttr", "mattr", "hapax_ratio"):
        rows_t[col] = np.random.default_rng(1).normal(1.0, 0.1, n)
        rows_c[col] = np.random.default_rng(2).normal(0.5, 0.1, n)
    pl.DataFrame(rows_t).write_parquet(feat_dir / f"{tgt.slug}.parquet")
    pl.DataFrame(rows_c).write_parquet(feat_dir / f"{ctl.slug}.parquet")

    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()
    settings = ForensicsSettings(
        authors=[
            AuthorConfig(
                name=tgt.name,
                slug=tgt.slug,
                role="target",
                archive_url=tgt.archive_url,
                baseline_start=tgt.baseline_start,
                baseline_end=tgt.baseline_end,
            ),
            AuthorConfig(
                name=ctl.name,
                slug=ctl.slug,
                role="control",
                archive_url=ctl.archive_url,
                baseline_start=ctl.baseline_start,
                baseline_end=ctl.baseline_end,
            ),
        ],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(changepoint_methods=["pelt"]),
    )
    out = compare_target_to_controls(
        tgt.slug,
        [ctl.slug],
        feat_dir,
        db,
        settings=settings,
        analysis_dir=analysis_dir,
        embeddings_dir=tmp_path / "emb",
        project_root=tmp_path,
    )
    assert "feature_comparisons" in out
    assert "editorial_vs_author_signal" in out


def test_pipeline_c_integration() -> None:

    from forensics.analysis.convergence import ProbabilityTrajectory, compute_convergence_scores
    from forensics.models.analysis import ChangePoint, HypothesisTest
    from forensics.models.report import FindingStrength, classify_finding_strength

    base = datetime(2024, 2, 1, tzinfo=UTC)
    cps = [
        ChangePoint(
            feature_name="ttr",
            author_id="a",
            timestamp=base,
            confidence=0.95,
            method="pelt",
            effect_size_cohens_d=1.0,
            direction="increase",
        )
    ]
    traj = ProbabilityTrajectory(
        monthly_perplexity=[("2024-01", 50.0), ("2024-02", 35.0), ("2024-03", 30.0)],
        monthly_burstiness=[("2024-01", 2.0), ("2024-02", 1.0), ("2024-03", 0.8)],
        monthly_binoculars=None,
    )
    wins = compute_convergence_scores(
        cps,
        [("2024-02", 0.9), ("2024-03", 0.95)],
        [(base + timedelta(days=i), 1.0 - 0.01 * i) for i in range(40)],
        probability_trajectory=traj,
        total_feature_count=1,
        min_feature_ratio=0.5,
    )
    assert wins and wins[0].pipeline_c_score is not None and wins[0].pipeline_c_score > 0
    strong_tests = [
        HypothesisTest(
            test_name=f"w{i}",
            feature_name=f"f{i}",
            author_id="a",
            raw_p_value=0.001,
            corrected_p_value=0.005,
            effect_size_cohens_d=0.9,
            confidence_interval_95=(0.0, 0.0),
            significant=True,
        )
        for i in range(3)
    ]
    st = classify_finding_strength(
        wins[0],
        strong_tests,
        {"editorial_vs_author_signal": 0.9},
        probability_features_available=True,
    )
    assert st == FindingStrength.STRONG
