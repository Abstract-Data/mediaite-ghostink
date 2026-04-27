"""Phase 15 F0 — PELT kernel swap RBF → L2.

Pins the new default (``l2``), the regression-pinned change-point indices, and
the wiring from ``AnalysisConfig.pelt_cost_model`` through to
``analyze_author_feature_changepoints``. Per the H1 spec these tests cover:

* **Happy path:** synthetic mean-shift signal under L2 detects a CP near the
  true change.
* **Edge case:** empty / too-short / constant signals return ``[]`` cleanly
  under every supported cost model.
* **Regression-pin:** for fixed RNG seeds the L2 break indices are pinned to
  specific values so future kernel changes surface as test diffs rather than
  silent drift in the report.
* **Settings wiring:** the ``pelt_cost_model`` knob defaults to ``"l2"`` and
  reaches ``rpt.Pelt`` via ``analyze_author_feature_changepoints`` (asserted by
  monkeypatching the inner ``detect_pelt`` call).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from forensics.analysis.changepoint import (
    analyze_author_feature_changepoints,
    changepoints_from_pelt,
    detect_pelt,
)
from forensics.config.settings import AnalysisConfig, ForensicsSettings, ScrapingConfig


def test_l2_detects_synthetic_mean_shift() -> None:
    """L2 PELT recovers a synthetic mean shift near the true change point."""
    rng = np.random.default_rng(42)
    before = rng.normal(0.0, 0.3, 100)
    after = rng.normal(3.0, 0.3, 100)
    signal = np.concatenate([before, after])

    bps = detect_pelt(signal, pen=2.0, cost_model="l2")

    assert bps, "L2 PELT must detect at least one breakpoint on a clear mean shift"
    assert any(95 <= b <= 105 for b in bps), (
        f"expected a break within 5 samples of true CP=100, got {bps}"
    )


def test_l2_is_the_default_cost_model() -> None:
    """``detect_pelt`` defaults to L2 (Phase 15 F0 flip)."""
    rng = np.random.default_rng(11)
    signal = np.concatenate([rng.normal(0.0, 0.2, 60), rng.normal(2.0, 0.2, 60)])

    default_bps = detect_pelt(signal, pen=3.0)
    explicit_l2 = detect_pelt(signal, pen=3.0, cost_model="l2")

    assert default_bps == explicit_l2, (
        "default cost_model must be 'l2' (Phase 15 F0 default flip from 'rbf')"
    )


@pytest.mark.parametrize("cost_model", ["l2", "l1", "rbf"])
def test_short_signal_returns_empty(cost_model: str) -> None:
    """Signals shorter than ``min_size`` quorum return ``[]`` for every kernel."""
    assert detect_pelt(np.array([], dtype=float), cost_model=cost_model) == []
    assert detect_pelt(np.zeros(9, dtype=float), cost_model=cost_model) == []


def test_constant_signal_emits_no_breakpoints() -> None:
    """A flat constant signal under L2 yields no change points."""
    signal = np.full(200, 4.2, dtype=float)
    assert detect_pelt(signal, pen=3.0, cost_model="l2") == []


def test_nan_input_is_handled_without_raising() -> None:
    """NaNs are imputed upstream (C-02); ``detect_pelt`` requires finite input."""
    from forensics.analysis.changepoint import _impute_finite_feature_series

    rng = np.random.default_rng(0)
    signal = np.concatenate([rng.normal(0.0, 0.3, 50), rng.normal(2.0, 0.3, 50)])
    signal[10] = np.nan
    signal[60] = np.nan

    bps = detect_pelt(_impute_finite_feature_series(signal), pen=3.0, cost_model="l2")

    assert isinstance(bps, list)
    assert all(isinstance(b, int) for b in bps)


def test_l2_regression_pin_two_mean_shifts() -> None:
    """L2 break indices on a fixed-seed two-shift signal are pinned.

    Captured from the F0 implementation on 2026-04-24. Bumping these values
    must be a deliberate decision (kernel change, ruptures upgrade, etc.)
    rather than a silent drift.
    """
    rng = np.random.default_rng(1234)
    seg1 = rng.normal(0.0, 0.3, 80)
    seg2 = rng.normal(2.5, 0.3, 80)
    seg3 = rng.normal(0.5, 0.3, 80)
    signal = np.concatenate([seg1, seg2, seg3])

    assert detect_pelt(signal, pen=3.0, cost_model="l2") == [80, 160]
    assert detect_pelt(signal, pen=5.0, cost_model="l2") == [80, 160]


def test_l2_regression_pin_single_mean_shift() -> None:
    """Single-shift fixture pins to one break at the true index."""
    rng = np.random.default_rng(7)
    signal = np.concatenate([rng.normal(0.0, 0.5, 100), rng.normal(2.0, 0.5, 100)])
    assert detect_pelt(signal, pen=3.0, cost_model="l2") == [100]


def test_analysis_config_default_is_l1() -> None:
    """``AnalysisConfig`` defaults to ``l1`` (Phase 15 J6 std-scaled PELT path)."""
    assert AnalysisConfig().pelt.pelt_cost_model == "l1"


def _settings_with_cost_model(cost_model: str) -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(
            changepoint_methods=["pelt"],
            pelt_cost_model=cost_model,
        ),
    )


def _toy_feature_frame(n: int = 60) -> pl.DataFrame:
    """One PELT feature column long enough to exceed the ``len < 10`` guard."""
    rng = np.random.default_rng(2026)
    values = np.concatenate([rng.normal(0.0, 0.2, n // 2), rng.normal(2.0, 0.2, n - n // 2)])
    base = datetime(2024, 1, 1, tzinfo=UTC)
    timestamps = [base + timedelta(days=i) for i in range(n)]
    return pl.DataFrame({"timestamp": timestamps, "ttr": values})


def test_pelt_cost_model_setting_reaches_detect_pelt(monkeypatch: pytest.MonkeyPatch) -> None:
    """``analyze_author_feature_changepoints`` forwards the configured cost model."""
    captured: list[str] = []

    real_changepoints_from_pelt = changepoints_from_pelt

    def _spy(*args: object, **kwargs: object) -> list:
        captured.append(str(kwargs.get("cost_model", "<missing>")))
        return real_changepoints_from_pelt(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "forensics.analysis.changepoint.changepoints_from_pelt",
        _spy,
    )

    df = _toy_feature_frame()
    settings = _settings_with_cost_model("l1")

    analyze_author_feature_changepoints(df, author_id="author-1", settings=settings)

    assert captured, "expected analyze_author_feature_changepoints to call changepoints_from_pelt"
    assert all(cm == "l1" for cm in captured), (
        f"all forwarded cost_model values should match the setting; got {captured}"
    )
