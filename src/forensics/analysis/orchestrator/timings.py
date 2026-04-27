"""Timing dataclasses/helpers for analysis orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class AnalysisTimings:
    """Per-stage wall-clock seconds captured during ``run_full_analysis``.

    ``per_author`` maps ``slug → {stage_name: seconds}`` so the bench script
    can emit non-zero per-stage timings instead of only ``total``. ``compare``
    is a single newsroom-wide bucket because the comparison stage runs once
    per target outside the per-author loop.
    """

    per_author: dict[str, dict[str, float]] = field(default_factory=dict)
    compare: float = 0.0
    total: float = 0.0


class _StageTimer:
    """Context-manager-free stopwatch that no-ops when ``sink is None``.

    ``record(stage_name)`` writes the wall-clock since the last call (or
    since construction) into ``sink[stage_name]`` and resets the clock. Used
    by ``_run_per_author_analysis`` to thread per-stage timings through to
    the bench script without polluting the call site with branchy
    ``if stage_timings is not None:`` guards.
    """

    __slots__ = ("_sink", "_t")

    def __init__(self, sink: dict[str, float] | None) -> None:
        self._sink = sink
        self._t = time.perf_counter()

    def record(self, stage: str) -> None:
        if self._sink is None:
            return
        now = time.perf_counter()
        self._sink[stage] = now - self._t
        self._t = now
