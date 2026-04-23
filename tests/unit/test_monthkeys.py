"""Unit tests for month-key helpers (B3 / RF-DRY-003 / RF-SMELL-003)."""

from __future__ import annotations

from datetime import date

import pytest

from forensics.analysis.monthkeys import iter_months_in_window, month_key_to_range


def test_month_key_to_range_january() -> None:
    assert month_key_to_range("2026-01") == (date(2026, 1, 1), date(2026, 1, 31))


def test_month_key_to_range_february_leap() -> None:
    assert month_key_to_range("2024-02") == (date(2024, 2, 1), date(2024, 2, 29))


def test_month_key_to_range_february_non_leap() -> None:
    assert month_key_to_range("2023-02") == (date(2023, 2, 1), date(2023, 2, 28))


def test_month_key_to_range_rejects_bad_format() -> None:
    with pytest.raises(ValueError):
        month_key_to_range("2026")


def test_iter_months_in_window_trivial() -> None:
    keys = ["2026-01", "2026-02", "2026-03"]
    out = list(iter_months_in_window(date(2026, 1, 15), date(2026, 2, 15), keys))
    assert [k for k, _, _ in out] == ["2026-01", "2026-02"]


def test_iter_months_in_window_preserves_input_order() -> None:
    # Deliberately out-of-order to confirm we don't sort.
    keys = ["2026-03", "2026-01", "2026-02"]
    out = list(iter_months_in_window(date(2026, 1, 1), date(2026, 3, 31), keys))
    assert [k for k, _, _ in out] == ["2026-03", "2026-01", "2026-02"]


def test_iter_months_in_window_empty_when_no_overlap() -> None:
    keys = ["2020-01", "2020-02"]
    out = list(iter_months_in_window(date(2026, 1, 1), date(2026, 12, 31), keys))
    assert out == []
