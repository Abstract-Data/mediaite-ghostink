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
