"""Unit tests for :func:`compute_volume_ramp_flag` (legacy counts, degenerate rows)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from forensics.models.analysis import HypothesisTest
from forensics.models.report import VolumeRampFlag, compute_volume_ramp_flag


def _ht(
    *,
    n_pre: int = 10,
    n_post: int = 10,
    degenerate: bool = False,
    feature: str = "ttr",
    test_name: str = "welch",
) -> HypothesisTest:
    return HypothesisTest(
        test_name=test_name,
        feature_name=feature,
        author_id="slug",
        raw_p_value=0.01,
        corrected_p_value=0.02,
        effect_size_cohens_d=0.2,
        confidence_interval_95=(0.0, 0.4),
        significant=True,
        n_pre=n_pre,
        n_post=n_post,
        degenerate=degenerate,
    )


def test_empty_list_unknown() -> None:
    assert compute_volume_ramp_flag([]) == (VolumeRampFlag.UNKNOWN, None)


def test_all_degenerate_unknown() -> None:
    rows = [_ht(n_pre=100, n_post=100, degenerate=True) for _ in range(3)]
    assert compute_volume_ramp_flag(rows) == (VolumeRampFlag.UNKNOWN, None)


def test_legacy_n_pre_minus_one_skipped_next_usable() -> None:
    """``n_pre == -1`` must not divide — second row supplies ratio."""
    rows = [
        _ht(n_pre=-1, n_post=50, test_name="legacy"),
        _ht(n_pre=10, n_post=30, test_name="good"),
    ]
    flag, ratio = compute_volume_ramp_flag(rows)
    assert flag == VolumeRampFlag.GROWTH
    assert ratio == pytest.approx(3.0)


def test_legacy_n_post_minus_one_skipped() -> None:
    rows = [
        _ht(n_pre=10, n_post=-1, test_name="bad"),
        _ht(n_pre=10, n_post=4, test_name="good"),
    ]
    flag, ratio = compute_volume_ramp_flag(rows)
    assert flag == VolumeRampFlag.DECLINE
    assert ratio == pytest.approx(0.4)


def test_n_pre_zero_skipped_no_division_by_zero() -> None:
    rows = [
        _ht(n_pre=0, n_post=100, test_name="zero_pre"),
        _ht(n_pre=10, n_post=10, test_name="fallback"),
    ]
    flag, ratio = compute_volume_ramp_flag(rows)
    assert flag == VolumeRampFlag.STABLE
    assert ratio == pytest.approx(1.0)


def test_n_pre_negative_below_minus_one_invalid_for_pydantic() -> None:
    """Model only allows ``n_pre >= -1``; -2 is rejected at construction."""
    with pytest.raises(ValidationError):
        HypothesisTest(
            test_name="x",
            feature_name="ttr",
            author_id="a",
            raw_p_value=0.1,
            corrected_p_value=0.1,
            effect_size_cohens_d=0.1,
            confidence_interval_95=(0.0, 0.2),
            significant=False,
            n_pre=-2,
            n_post=10,
        )


def test_first_non_degenerate_wins_when_second_has_different_ratio() -> None:
    rows = [
        _ht(n_pre=10, n_post=10, test_name="first", degenerate=False),
        _ht(n_pre=10, n_post=100, test_name="second", degenerate=False),
    ]
    flag, ratio = compute_volume_ramp_flag(rows)
    assert flag == VolumeRampFlag.STABLE
    assert ratio == pytest.approx(1.0)


def test_degenerate_first_row_second_supplies_ratio() -> None:
    rows = [
        _ht(n_pre=10, n_post=50, degenerate=True),
        _ht(n_pre=10, n_post=30),
    ]
    flag, ratio = compute_volume_ramp_flag(rows)
    assert flag == VolumeRampFlag.GROWTH
    assert ratio == pytest.approx(3.0)


def test_ratio_bands_decline_below_half() -> None:
    flag, ratio = compute_volume_ramp_flag([_ht(n_pre=10, n_post=4)])
    assert flag == VolumeRampFlag.DECLINE
    assert ratio == pytest.approx(0.4)


def test_ratio_bands_stable_at_half() -> None:
    flag, ratio = compute_volume_ramp_flag([_ht(n_pre=10, n_post=5)])
    assert flag == VolumeRampFlag.STABLE
    assert ratio == pytest.approx(0.5)


def test_ratio_bands_stable_at_two() -> None:
    flag, ratio = compute_volume_ramp_flag([_ht(n_pre=10, n_post=20)])
    assert flag == VolumeRampFlag.STABLE
    assert ratio == pytest.approx(2.0)


def test_ratio_bands_growth_just_above_two() -> None:
    flag, ratio = compute_volume_ramp_flag([_ht(n_pre=10, n_post=21)])
    assert flag == VolumeRampFlag.GROWTH
    assert ratio == pytest.approx(2.1)


def test_ratio_bands_growth_at_five() -> None:
    flag, ratio = compute_volume_ramp_flag([_ht(n_pre=10, n_post=50)])
    assert flag == VolumeRampFlag.GROWTH
    assert ratio == pytest.approx(5.0)


def test_ratio_bands_ramp_above_five() -> None:
    flag, ratio = compute_volume_ramp_flag([_ht(n_pre=10, n_post=51)])
    assert flag == VolumeRampFlag.RAMP
    assert ratio == pytest.approx(5.1)


def test_n_post_zero_ratio_zero_is_decline() -> None:
    flag, ratio = compute_volume_ramp_flag([_ht(n_pre=10, n_post=0)])
    assert flag == VolumeRampFlag.DECLINE
    assert ratio == pytest.approx(0.0)
