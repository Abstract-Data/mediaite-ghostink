"""Unit tests for ``compute_convergence_scores``.

Covers the public API in ``forensics.analysis.convergence``:

* empty-input guards,
* single change-point detection,
* multi-feature alignment inside the window,
* no-alignment when change points fall outside the window,
* graceful handling of ``total_feature_count=0`` / empty feature list.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from forensics.analysis.convergence import ConvergenceInput, compute_convergence_scores
from forensics.models.analysis import ChangePoint


def _cp(
    feature_name: str,
    timestamp: datetime,
    *,
    confidence: float = 0.9,
    effect_size: float = 0.8,
    direction: str = "increase",
) -> ChangePoint:
    return ChangePoint(
        feature_name=feature_name,
        author_id="author-1",
        timestamp=timestamp,
        confidence=confidence,
        method="pelt",
        effect_size_cohens_d=effect_size,
        direction=direction,  # type: ignore[arg-type]
    )


def test_no_changepoints_returns_empty() -> None:
    """With no change points and no auxiliary signals, the result is empty."""
    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=[],
            centroid_velocities=[],
            baseline_similarity_curve=[],
            total_feature_count=5,
        )
    )
    assert result == []


def test_single_changepoint_single_feature_emits_window() -> None:
    """A lone change point with total=1 yields a window centred on the CP date."""
    cp_time = datetime(2024, 3, 15, tzinfo=UTC)
    cps = [_cp("ttr", cp_time)]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=90,
            total_feature_count=1,
        )
    )

    assert len(result) == 1
    window = result[0]
    assert window.start_date == cp_time.date()
    assert window.end_date == cp_time.date() + timedelta(days=90)
    assert window.features_converging == ["ttr"]
    assert window.convergence_ratio == pytest.approx(1.0)


def test_multi_feature_alignment_within_window_detected() -> None:
    """Multiple change points across features inside the window trigger convergence."""
    base = datetime(2024, 6, 1, tzinfo=UTC)
    feature_names = ["ttr", "mattr", "hapax_ratio", "yules_k", "simpsons_d"]
    cps = [_cp(name, base + timedelta(days=i * 3)) for i, name in enumerate(feature_names)]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=30,
            min_feature_ratio=0.6,
            total_feature_count=5,
        )
    )

    assert result, "expected at least one convergence window"
    first = result[0]
    assert first.start_date == base.date()
    assert first.convergence_ratio == pytest.approx(1.0)
    assert sorted(first.features_converging) == sorted(feature_names)


def test_changepoints_outside_window_no_convergence() -> None:
    """Change points separated by more than ``window_days`` should not converge."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    cps = [
        _cp("ttr", base),
        _cp("mattr", base + timedelta(days=200)),
        _cp("hapax_ratio", base + timedelta(days=400)),
        _cp("yules_k", base + timedelta(days=600)),
        _cp("simpsons_d", base + timedelta(days=800)),
    ]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=30,
            min_feature_ratio=0.6,
            total_feature_count=5,
        )
    )

    assert result == []


def test_empty_feature_total_returns_empty() -> None:
    """``total_feature_count=0`` must short-circuit without a ZeroDivisionError."""
    cp_time = datetime(2024, 2, 1, tzinfo=UTC)
    cps = [_cp("ttr", cp_time), _cp("mattr", cp_time + timedelta(days=2))]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            total_feature_count=0,
        )
    )

    assert result == []


def test_fully_empty_inputs_graceful() -> None:
    """All-empty inputs (no CPs, no velocities, no curve, zero total) do not crash."""
    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=[],
            centroid_velocities=[],
            baseline_similarity_curve=[],
            total_feature_count=0,
        )
    )
    assert result == []
