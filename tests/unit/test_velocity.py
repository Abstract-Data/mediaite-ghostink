"""Unit tests for shared velocity helpers (B2 / RF-DRY-002)."""

from __future__ import annotations

import numpy as np
import pytest

from forensics.analysis.utils import (
    compute_velocity_acceleration,
    describe_velocity_acceleration_pct,
    pair_months_with_velocities,
)


def test_pair_months_with_velocities_basic() -> None:
    monthly = [("2026-01", np.zeros(3)), ("2026-02", np.zeros(3)), ("2026-03", np.zeros(3))]
    vels = [0.4, 0.7]
    assert pair_months_with_velocities(monthly, vels) == [("2026-02", 0.4), ("2026-03", 0.7)]


def test_pair_months_with_velocities_handles_short_vels() -> None:
    monthly = [("2026-01", np.zeros(3)), ("2026-02", np.zeros(3)), ("2026-03", np.zeros(3))]
    # Only 1 velocity even though there are 3 months — should not over-index.
    assert pair_months_with_velocities(monthly, [0.4]) == [("2026-02", 0.4)]


def test_pair_months_with_velocities_handles_empty_monthly() -> None:
    assert pair_months_with_velocities([], [0.4, 0.5]) == []


def test_compute_velocity_acceleration_requires_six_points() -> None:
    assert compute_velocity_acceleration([1.0, 1.0, 1.0, 1.0, 1.0]) == 0.0


def test_compute_velocity_acceleration_clamps_to_unit_interval() -> None:
    # Strong acceleration — ratio would be 10 without clamp.
    vels = [0.1, 0.1, 0.1, 1.1, 1.1, 1.1]
    assert compute_velocity_acceleration(vels) == 1.0


def test_compute_velocity_acceleration_returns_zero_for_zero_early() -> None:
    vels = [0.0, 0.0, 0.0, 0.5, 0.5, 0.5]
    assert compute_velocity_acceleration(vels) == 0.0


def test_compute_velocity_acceleration_mid_range() -> None:
    vels = [0.2, 0.2, 0.2, 0.3, 0.3, 0.3]
    # early=0.2, late=0.3, ratio=0.5 (subject to float rounding).
    assert compute_velocity_acceleration(vels) == pytest.approx(0.5, abs=1e-9)


def test_describe_velocity_acceleration_pct_none_when_undefined() -> None:
    assert describe_velocity_acceleration_pct([0.0] * 3) is None
    assert describe_velocity_acceleration_pct([0.0] * 6) is None


def test_describe_velocity_acceleration_pct_phrases_increase() -> None:
    assert describe_velocity_acceleration_pct([0.2] * 3 + [0.3] * 3) == "increased by 50%"


def test_describe_velocity_acceleration_pct_phrases_decrease() -> None:
    assert describe_velocity_acceleration_pct([0.4] * 3 + [0.2] * 3) == "decreased by 50%"
