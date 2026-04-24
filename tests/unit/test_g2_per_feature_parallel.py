"""Phase 15 G2 — opportunistic per-feature parallelism tests.

When ``settings.analysis.feature_workers > 1`` the per-feature loop in
:func:`forensics.analysis.changepoint.analyze_author_feature_changepoints`
dispatches each feature to a ``ThreadPoolExecutor``. Output ordering is
preserved (results are collected by feature name and walked in
``PELT_FEATURE_COLUMNS`` order) so the parallel and serial paths must be
byte-identical for the same fixture.

Coverage targets (≥ 3 tests per H1 spec):

* parity: ``feature_workers=1`` vs ``feature_workers=2`` produce
  byte-identical CP output (same feature_name order, same timestamps,
  same effect sizes / methods).
* parity at higher concurrency: ``feature_workers=4`` matches the serial
  path on a multi-feature fixture.
* over-provision: a single-feature fixture with ``feature_workers=4`` does
  not crash (``ThreadPoolExecutor`` caps at the actual task count).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

from forensics.analysis.changepoint import (
    PELT_FEATURE_COLUMNS,
    analyze_author_feature_changepoints,
)
from forensics.config.settings import AnalysisConfig, ForensicsSettings, ScrapingConfig


def _settings(*, feature_workers: int, methods: list[str] | None = None) -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(
            changepoint_methods=methods or ["pelt"],
            feature_workers=feature_workers,
        ),
    )


def _multi_feature_frame(
    *,
    n: int = 80,
    seed: int = 2026,
    features: tuple[str, ...] = (
        "ttr",
        "mattr",
        "flesch_kincaid",
        "sent_length_mean",
        "first_person_ratio",
    ),
) -> pl.DataFrame:
    """Build a fixture with several PELT features each carrying a clear mean shift."""
    rng = np.random.default_rng(seed)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for i in range(n):
        row: dict[str, object] = {"timestamp": base + timedelta(days=i)}
        for f_idx, feature in enumerate(features):
            # Deterministic mean shift halfway through, with feature-specific magnitude
            # so each feature produces a real CP without being identical to its peers.
            shift = (1.5 + 0.3 * f_idx) if i >= n // 2 else 0.0
            row[feature] = float(shift + rng.normal(0.0, 0.3))
        rows.append(row)
    return pl.DataFrame(rows)


def _serialise_cps(cps: list) -> list[tuple]:
    """Project ChangePoints onto a comparable tuple (order matters)."""
    return [
        (
            cp.feature_name,
            cp.author_id,
            cp.timestamp.isoformat(),
            cp.method,
            round(float(cp.effect_size_cohens_d), 9),
            cp.direction,
        )
        for cp in cps
    ]


# ---------------------------------------------------------------------------
# Parity: feature_workers=1 vs feature_workers=2 byte-identical
# ---------------------------------------------------------------------------


def test_feature_workers_two_matches_serial_byte_identical() -> None:
    """The opt-in parallel path produces the same CP list as the serial baseline."""
    df = _multi_feature_frame()
    serial = analyze_author_feature_changepoints(
        df, author_id="author-parity", settings=_settings(feature_workers=1)
    )
    parallel = analyze_author_feature_changepoints(
        df, author_id="author-parity", settings=_settings(feature_workers=2)
    )
    assert _serialise_cps(serial) == _serialise_cps(parallel)
    # Sanity: the fixture really does emit CPs (otherwise parity is trivially true).
    assert serial, "fixture should produce at least one PELT changepoint"


def test_feature_workers_four_matches_serial_byte_identical() -> None:
    """Higher concurrency still matches the serial baseline."""
    df = _multi_feature_frame(seed=99)
    serial = analyze_author_feature_changepoints(
        df, author_id="author-parity4", settings=_settings(feature_workers=1)
    )
    parallel = analyze_author_feature_changepoints(
        df, author_id="author-parity4", settings=_settings(feature_workers=4)
    )
    assert _serialise_cps(serial) == _serialise_cps(parallel)


# ---------------------------------------------------------------------------
# Edge case: single-feature fixture with over-provisioned workers
# ---------------------------------------------------------------------------


def test_single_feature_with_overprovisioned_workers_does_not_crash() -> None:
    """1 feature + ``feature_workers=4`` is harmless (executor caps at task count)."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    rng = np.random.default_rng(7)
    n = 80
    signal = np.concatenate([rng.normal(0.0, 0.3, n // 2), rng.normal(2.0, 0.3, n // 2)])
    df = pl.DataFrame(
        {
            "timestamp": [base + timedelta(days=i) for i in range(n)],
            "ttr": signal,
        }
    )
    cps = analyze_author_feature_changepoints(
        df, author_id="author-overprov", settings=_settings(feature_workers=4)
    )
    # Sanity: the lone feature still produces a CP.
    assert cps, "single-feature fixture should still emit a changepoint"
    assert all(cp.feature_name == "ttr" for cp in cps)


# ---------------------------------------------------------------------------
# Edge case: bocpd path also parallel-safe
# ---------------------------------------------------------------------------


def test_bocpd_path_parity_under_parallelism() -> None:
    """BOCPD-only run is byte-identical between serial and parallel paths."""
    df = _multi_feature_frame(seed=314)
    serial = analyze_author_feature_changepoints(
        df,
        author_id="author-bocpd",
        settings=_settings(feature_workers=1, methods=["bocpd"]),
    )
    parallel = analyze_author_feature_changepoints(
        df,
        author_id="author-bocpd",
        settings=_settings(feature_workers=3, methods=["bocpd"]),
    )
    assert _serialise_cps(serial) == _serialise_cps(parallel)


# ---------------------------------------------------------------------------
# Sanity: PELT_FEATURE_COLUMNS is the canonical ordering source
# ---------------------------------------------------------------------------


def test_output_walks_pelt_feature_columns_order() -> None:
    """CP feature_names appear in PELT_FEATURE_COLUMNS order (no scheduler races)."""
    df = _multi_feature_frame()
    cps = analyze_author_feature_changepoints(
        df, author_id="author-order", settings=_settings(feature_workers=4)
    )
    seen_features = [cp.feature_name for cp in cps]
    # All features in seen_features must respect the registry order. We allow
    # repeats (one feature can emit multiple CPs).
    last_idx = -1
    for name in seen_features:
        idx = PELT_FEATURE_COLUMNS.index(name)
        assert idx >= last_idx, f"{name!r} appeared out of PELT order"
        last_idx = idx
