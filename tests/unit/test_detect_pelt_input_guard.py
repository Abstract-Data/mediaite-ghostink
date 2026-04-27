"""Non-finite inputs: ``detect_pelt`` rejects; public wrappers impute or raise cleanly."""

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


def test_detect_pelt_raises_on_nonfinite_without_imputation() -> None:
    y = np.concatenate([np.linspace(0.0, 1.0, 15), np.linspace(2.0, 3.0, 15)])
    y[10] = np.nan
    with pytest.raises(ValueError, match="finite"):
        detect_pelt(y, pen=2.0, cost_model="l2")


def test_changepoints_from_pelt_succeeds_after_internal_imputation() -> None:
    rng = np.random.default_rng(7)
    y = rng.normal(0.0, 0.2, 120)
    y[40] = np.nan
    y[80] = np.inf
    base = datetime(2024, 1, 1, tzinfo=UTC)
    ts = [base + timedelta(days=i) for i in range(120)]
    cps = changepoints_from_pelt("ttr", "author-x", y, ts, pen=3.0, cost_model="l2")
    assert isinstance(cps, list)
    assert all(hasattr(cp, "feature_name") for cp in cps)


def test_analyze_author_feature_changepoints_handles_nonfinite_column() -> None:
    rng = np.random.default_rng(11)
    n = 60
    values = np.concatenate([rng.normal(0.0, 0.2, n // 2), rng.normal(2.0, 0.2, n - n // 2)])
    values[5] = np.nan
    values[22] = np.inf
    base = datetime(2024, 1, 1, tzinfo=UTC)
    timestamps = [base + timedelta(days=i) for i in range(n)]
    df = pl.DataFrame({"timestamp": timestamps, "ttr": values})
    settings = ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(changepoint_methods=["pelt"], pelt_cost_model="l2"),
    )
    out = analyze_author_feature_changepoints(df, author_id="author-1", settings=settings)
    assert isinstance(out, list)
