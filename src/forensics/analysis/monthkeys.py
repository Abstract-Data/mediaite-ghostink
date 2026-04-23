"""``YYYY-MM`` month-key helpers shared across drift and convergence analysis.

Prior to this module, every consumer independently parsed ``"YYYY-MM"`` strings
via a local ``_month_key_to_range`` helper and paired ``intervals_overlap`` with
it to iterate month buckets overlapping an analysis window (see RF-DRY-003,
RF-SMELL-003). ``MonthKey`` names the contract; ``month_key_to_range`` and
``iter_months_in_window`` centralise the logic.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Iterator
from datetime import date
from typing import NewType

from forensics.analysis.utils import intervals_overlap

# NewType is a lightweight alias — values are still plain ``str`` at runtime but
# type-checkers will flag arbitrary strings being used where a ``MonthKey`` is
# expected. Build one with ``MonthKey("YYYY-MM")`` at creation sites.
MonthKey = NewType("MonthKey", str)


def month_key_to_range(key: MonthKey | str) -> tuple[date, date]:
    """Return ``(first_day, last_day)`` for the calendar month named by ``key``.

    ``key`` must be ``"YYYY-MM"``. Invalid keys raise ``ValueError``.
    """
    y_str, m_str = key.split("-", 1)
    y, mo = int(y_str), int(m_str)
    last = calendar.monthrange(y, mo)[1]
    return date(y, mo, 1), date(y, mo, last)


def iter_months_in_window(
    window_start: date,
    window_end: date,
    month_keys: Iterable[MonthKey | str],
) -> Iterator[tuple[str, date, date]]:
    """Yield ``(key, month_start, month_end)`` for each key overlapping the window.

    The output preserves the caller's input order. Use this when you need both
    the key itself (e.g. as a dict key) and its date range.
    """
    for key in month_keys:
        m0, m1 = month_key_to_range(key)
        if intervals_overlap(window_start, window_end, m0, m1):
            yield key, m0, m1


__all__ = ["MonthKey", "iter_months_in_window", "month_key_to_range"]
