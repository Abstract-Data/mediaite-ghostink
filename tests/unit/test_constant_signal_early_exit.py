"""Phase 15 F3 — early-exit on constant signals in changepoint analysis.

A flat (or numerically-flat) feature series cannot produce meaningful
change-points. PELT will return ``[]`` regardless, but BOCPD's
variance-normalization divides by the seed-window variance — when that
variance is ~zero, the floor (1e-12) keeps the call from raising but produces
unstable / meaningless predictives. F3 short-circuits both detectors when
``np.std(series) < 1e-9`` and logs at DEBUG so audits can see what was
skipped.

Per the H1 spec these tests cover:

* **Edge case (constant zero):** a literal ``np.zeros`` series returns ``[]``
  cleanly with no exception and no division-by-zero.
* **Edge case (near-constant):** a series with ``std < 1e-9`` but not literally
  zero is also skipped, and the DEBUG log line is emitted.
* **Negative test:** a non-constant series is *not* skipped — both PELT and
  BOCPD see it and the per-feature loop continues normally.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from forensics.analysis.changepoint import analyze_author_feature_changepoints
from forensics.config.settings import AnalysisConfig, ForensicsSettings, ScrapingConfig


def _settings(methods: list[str] | None = None) -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(
            changepoint_methods=methods or ["pelt", "bocpd"],
        ),
    )


def _frame(values: np.ndarray, *, column: str = "ttr") -> pl.DataFrame:
    """One PELT feature column long enough to clear the ``len < 10`` guard."""
    n = len(values)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    timestamps = [base + timedelta(days=i) for i in range(n)]
    return pl.DataFrame({"timestamp": timestamps, column: values})


# ---------------------------------------------------------------------------
# Edge case: constant zero
# ---------------------------------------------------------------------------


def test_constant_zero_series_returns_empty_cleanly() -> None:
    """A literal ``np.zeros`` series yields ``[]`` with no exception, no NaN."""
    df = _frame(np.zeros(60, dtype=float))
    cps = analyze_author_feature_changepoints(df, author_id="author-1", settings=_settings())
    assert cps == []


# ---------------------------------------------------------------------------
# Edge case: near-constant (std < 1e-9 but not literally zero) + DEBUG log
# ---------------------------------------------------------------------------


def test_near_constant_series_is_skipped_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Series with ``std < 1e-9`` is skipped and a DEBUG audit line is emitted."""
    base = np.full(60, 0.4, dtype=float)
    base[5] += 1e-12  # std ~ 1.3e-13, well below the 1e-9 threshold
    assert float(np.std(base)) < 1e-9
    df = _frame(base)

    with caplog.at_level(logging.DEBUG, logger="forensics.analysis.changepoint"):
        cps = analyze_author_feature_changepoints(
            df, author_id="author-debug", settings=_settings()
        )

    assert cps == []
    matched = [
        rec
        for rec in caplog.records
        if "constant signal" in rec.getMessage()
        and "author-debug" in rec.getMessage()
        and "ttr" in rec.getMessage()
    ]
    if not matched:
        seen = [r.getMessage() for r in caplog.records]
        msg = f"expected DEBUG log for skipped constant signal; got {seen}"
        raise AssertionError(msg)
    assert all(rec.levelno == logging.DEBUG for rec in matched)


# ---------------------------------------------------------------------------
# Negative test: non-constant series is NOT skipped
# ---------------------------------------------------------------------------


def test_non_constant_series_is_not_skipped() -> None:
    """A clear mean-shift series produces at least one PELT change-point."""
    rng = np.random.default_rng(42)
    signal = np.concatenate([rng.normal(0.0, 0.3, 60), rng.normal(2.5, 0.3, 60)])
    df = _frame(signal)

    cps = analyze_author_feature_changepoints(
        df,
        author_id="author-shift",
        settings=_settings(methods=["pelt"]),
    )

    assert cps, "non-constant mean-shift series must produce at least one change-point"
    assert all(cp.feature_name == "ttr" for cp in cps)
