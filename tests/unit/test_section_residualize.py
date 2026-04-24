"""Phase 15 Step J5 reference fixture: section-mix-only signal must NOT survive residualization.

J5 (section-residualize features) is gated on the Wave 4 J3 verdict and has
not yet shipped to ``forensics.analysis``. This module pre-stages the fixture
plus the assertion shape so the unit lands the moment J5 ships.

The happy / regression-pin tests prove the fixture is *valid*: an unadjusted
PELT call on a synthetic section-mix-only signal DOES emit a change-point.
The xfailed test is what flips green when J5 ships — it asserts that the
residualized PELT call DOES NOT emit a change-point on the same signal,
because residualization absorbs the section-driven mean shift.

Flip the xfail to a real call once
``src.forensics.analysis.section_residualize`` (or its equivalent) lands.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from forensics.analysis.changepoint import detect_pelt


def _section_mix_signal(
    *,
    n: int = 60,
    section_a_value: float = 0.30,
    section_b_value: float = 0.70,
    rng_seed: int = 7,
) -> np.ndarray:
    """Synthetic per-article series whose mean shift is entirely a section-mix artifact.

    First half is dominated by section "A" (value ~0.30), second half by
    section "B" (value ~0.70). Within each half the values are i.i.d. around
    the section mean. The author's underlying *style* is unchanged — the
    apparent change-point is a reporting-mix artifact, exactly the failure
    mode J5 is designed to absorb.
    """
    rng = np.random.default_rng(rng_seed)
    half = n // 2
    a_block = rng.normal(loc=section_a_value, scale=0.02, size=half)
    b_block = rng.normal(loc=section_b_value, scale=0.02, size=n - half)
    return np.concatenate([a_block, b_block])


def test_section_mix_signal_is_a_valid_fixture_for_pelt() -> None:
    """Happy path: unadjusted PELT on the synthetic series detects a change-point.

    If this test ever stops finding a CP, the fixture has degenerated and the
    xfailed J5 assertion below would pass trivially — defeating its purpose.
    """
    signal = _section_mix_signal()
    breaks = detect_pelt(signal, pen=1.0)
    assert breaks, "fixture must produce at least one PELT change-point pre-residualization"


def test_section_mix_break_lands_near_the_midpoint() -> None:
    """Edge case: PELT places the break inside the half-shift band, not at the edges.

    The synthetic signal flips at index n/2; PELT's L2 cost should put the
    break within a small window of that index. The window is wide on purpose
    — we want the fixture stable across the ``ruptures`` minor-version
    drift, not rigidly pinned to one breakpoint.
    """
    signal = _section_mix_signal()
    breaks = detect_pelt(signal, pen=1.0)
    midpoint = len(signal) // 2
    assert any(abs(b - midpoint) <= 5 for b in breaks), (
        f"expected a break near index {midpoint}, got {breaks}"
    )


def test_section_mix_change_point_count_regression_pin() -> None:
    """Regression pin: this fixture surfaces exactly one PELT break under ``pen=1.0``.

    Locks the count, not just "at least one", so a future PELT default flip
    (e.g. cost-model swap) surfaces here as a loud diff rather than a silent
    drift in the J5 fixture's interpretation.
    """
    signal = _section_mix_signal()
    breaks = detect_pelt(signal, pen=1.0)
    assert len(breaks) == 1, f"reference fixture pins to one break; got {breaks}"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "J5 section-residualize gated on Wave 4 J3 verdict; "
        "TODO: flip to real residualize call when "
        "forensics.analysis.section_residualize lands."
    ),
)
def test_section_residualize_suppresses_section_mix_only_change_point() -> None:
    """When J5 ships, residualizing should erase the section-mix CP entirely.

    Implementation pattern (post-J5):

        from forensics.analysis.section_residualize import residualize_by_section

        residualized = residualize_by_section(signal, sections)
        breaks = detect_pelt(residualized, pen=3.0)
        assert breaks == []

    Until then we assert the *opposite* on the unadjusted signal so the
    xfail registers (proving the fixture still has a section-driven CP that
    J5 will absorb).
    """
    spec = importlib.util.find_spec("forensics.analysis.section_residualize")
    if spec is None:
        # J5 not shipped — assert the inverse so xfail(strict=True) registers.
        signal = _section_mix_signal()
        breaks = detect_pelt(signal, pen=1.0)
        assert breaks == [], (
            "fixture currently has unsuppressed CPs (expected pre-J5); "
            "this test flips strict-pass when J5 lands and the assertion is rewritten"
        )
    else:  # pragma: no cover — exercised only post-J5
        from forensics.analysis.section_residualize import (
            residualize_by_section,  # type: ignore[import-not-found]
        )

        signal = _section_mix_signal()
        sections = ["A"] * (len(signal) // 2) + ["B"] * (len(signal) - len(signal) // 2)
        residualized = residualize_by_section(signal, sections)
        breaks = detect_pelt(np.asarray(residualized), pen=1.0)
        assert breaks == [], "J5 residualization should erase section-mix-only CP"
