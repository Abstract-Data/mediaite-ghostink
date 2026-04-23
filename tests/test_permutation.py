"""Permutation-test tests (Phase 12 §5b)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from forensics.analysis.permutation import (
    PermutationResult,
    changepoint_permutation,
    permutation_test,
)
from forensics.config import get_settings


def test_permutation_random_data_high_pvalue() -> None:
    """Observed near the null mean → empirical p-value should be high."""
    rng = np.random.default_rng(42)
    null = rng.normal(loc=0.5, scale=0.05, size=1000)
    observed = 0.5

    result = permutation_test(observed, null, n_permutations=1000)

    assert isinstance(result, PermutationResult)
    assert result.p_value > 0.2
    assert result.n_permutations == 1000
    assert abs(result.null_mean - 0.5) < 0.01


def test_permutation_strong_effect_low_pvalue() -> None:
    """Observed far above the null distribution → p-value near zero."""
    rng = np.random.default_rng(0)
    null = rng.normal(loc=0.2, scale=0.05, size=1000)
    observed = 0.95

    result = permutation_test(observed, null, n_permutations=1000)

    assert result.p_value < 0.01
    assert result.observed == 0.95


def test_permutation_deterministic_with_seed() -> None:
    """Same seed + same inputs → identical result."""
    rng1 = np.random.default_rng(42)
    series1 = rng1.standard_normal(200)
    cps = [30, 40, 50, 60]

    a = changepoint_permutation(series1, cps, n_permutations=500, seed=123)
    b = changepoint_permutation(series1, cps, n_permutations=500, seed=123)

    assert a.p_value == b.p_value
    assert a.observed == b.observed
    assert a.null_mean == b.null_mean
    assert a.null_std == b.null_std


def test_permutation_different_seed_diverges() -> None:
    """Different seeds produce different null distributions (sanity check)."""
    rng = np.random.default_rng(0)
    series = rng.standard_normal(200)
    cps = [30, 40, 50, 60]

    a = changepoint_permutation(series, cps, n_permutations=500, seed=1)
    b = changepoint_permutation(series, cps, n_permutations=500, seed=2)

    # Observed is deterministic from the inputs; nulls should differ.
    assert a.observed == b.observed
    assert (a.null_mean != b.null_mean) or (a.null_std != b.null_std)


def test_permutation_empty_changepoints() -> None:
    """Empty change-points → sentinel p-value 1.0 and zero observed."""
    series = np.zeros(100)
    result = changepoint_permutation(series, [], n_permutations=100, seed=42)

    assert result.p_value == 1.0
    assert result.observed == 0.0
    assert result.n_permutations == 0


def test_permutation_clustered_changepoints_low_pvalue() -> None:
    """Densely clustered change-points produce a low empirical p-value."""
    rng = np.random.default_rng(7)
    series = rng.standard_normal(500)
    # All ten change-points packed into a 20-sample window → heavy clustering.
    cps = list(range(100, 120, 2))

    result = changepoint_permutation(series, cps, n_permutations=1000, seed=42, window=25)

    assert result.p_value < 0.05
    assert result.observed > result.null_mean


def test_permutation_test_handles_empty_null() -> None:
    """Empty null distribution returns the documented sentinel."""
    result = permutation_test(0.5, [], n_permutations=100)

    assert result.p_value == 1.0
    assert result.null_mean == 0.0
    assert result.null_std == 0.0


def test_analysis_config_convergence_permutation_defaults(
    forensics_config_path: Path,
) -> None:
    """``AnalysisConfig`` exposes permutation knobs with safe defaults."""
    s = get_settings()
    assert s.analysis.convergence_use_permutation is False
    assert s.analysis.convergence_permutation_iterations == 1000
    assert s.analysis.convergence_permutation_seed == 42


def test_analysis_config_convergence_permutation_env_override(
    forensics_config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nested ``FORENSICS_ANALYSIS__*`` env vars override TOML defaults."""
    monkeypatch.setenv("FORENSICS_ANALYSIS__CONVERGENCE_USE_PERMUTATION", "true")
    monkeypatch.setenv("FORENSICS_ANALYSIS__CONVERGENCE_PERMUTATION_ITERATIONS", "50")
    monkeypatch.setenv("FORENSICS_ANALYSIS__CONVERGENCE_PERMUTATION_SEED", "7")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.analysis.convergence_use_permutation is True
        assert s.analysis.convergence_permutation_iterations == 50
        assert s.analysis.convergence_permutation_seed == 7
    finally:
        for key in (
            "FORENSICS_ANALYSIS__CONVERGENCE_USE_PERMUTATION",
            "FORENSICS_ANALYSIS__CONVERGENCE_PERMUTATION_ITERATIONS",
            "FORENSICS_ANALYSIS__CONVERGENCE_PERMUTATION_SEED",
        ):
            monkeypatch.delenv(key, raising=False)
        get_settings.cache_clear()
