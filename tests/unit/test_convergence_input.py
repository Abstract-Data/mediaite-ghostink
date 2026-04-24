"""Unit tests for ``ConvergenceInput`` factories (B1 migration)."""

from __future__ import annotations

from datetime import UTC, datetime

from forensics.analysis.convergence import ConvergenceInput
from forensics.config import get_settings
from forensics.models.analysis import ChangePoint


def _cp() -> ChangePoint:
    return ChangePoint(
        feature_name="ttr",
        author_id="author-1",
        timestamp=datetime(2024, 1, 15, tzinfo=UTC),
        confidence=0.9,
        method="pelt",
        effect_size_cohens_d=0.8,
        direction="increase",
    )


def test_from_settings_pulls_permutation_knobs_from_analysis() -> None:
    """``from_settings`` should copy permutation knobs from ``settings.analysis``."""
    get_settings.cache_clear()
    settings = get_settings()
    input_ = ConvergenceInput.from_settings(
        [_cp()],
        [],
        [],
        settings,
    )

    ac = settings.analysis
    assert input_.use_permutation is ac.convergence_use_permutation
    assert input_.n_permutations == ac.convergence_permutation_iterations
    assert input_.permutation_seed == ac.convergence_permutation_seed
    assert input_.window_days == ac.convergence_window_days
    assert input_.min_feature_ratio == ac.convergence_min_feature_ratio
    assert input_.settings is settings


def test_from_settings_passes_through_optional_signals() -> None:
    """Optional AI curve / probability trajectory arguments flow through unchanged."""
    get_settings.cache_clear()
    settings = get_settings()
    ai_curve = [("2024-01", 0.1)]
    input_ = ConvergenceInput.from_settings(
        [_cp()],
        [],
        [],
        settings,
        ai_convergence_curve=ai_curve,
    )
    assert input_.ai_convergence_curve == ai_curve
    assert input_.probability_trajectory is None


def test_build_applies_explicit_overrides_when_no_settings() -> None:
    """``ConvergenceInput.build`` should honour explicit defaults when settings is None."""
    input_ = ConvergenceInput.build(
        [_cp()],
        [],
        [],
        window_days=45,
        min_feature_ratio=0.75,
        total_feature_count=12,
        use_permutation=True,
        n_permutations=250,
        permutation_seed=7,
    )
    assert input_.window_days == 45
    assert input_.min_feature_ratio == 0.75
    assert input_.total_feature_count == 12
    assert input_.use_permutation is True
    assert input_.n_permutations == 250
    assert input_.permutation_seed == 7
