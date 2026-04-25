"""Deterministic scoring helpers for AI-marker calibration."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MarkerCalibrationScore:
    """Summary of how well AI-marker frequency separates labeled examples."""

    human_mean: float
    ai_mean: float
    separation: float
    passes_threshold: bool


def score_marker_discrimination(
    human_frequencies: list[float],
    ai_frequencies: list[float],
    *,
    minimum_separation: float = 0.05,
) -> MarkerCalibrationScore:
    """Measure whether marker frequency is higher in labeled AI controls."""
    human = np.asarray(human_frequencies, dtype=float)
    ai = np.asarray(ai_frequencies, dtype=float)
    human = human[np.isfinite(human)]
    ai = ai[np.isfinite(ai)]
    human_mean = float(np.mean(human)) if human.size else 0.0
    ai_mean = float(np.mean(ai)) if ai.size else 0.0
    separation = ai_mean - human_mean
    return MarkerCalibrationScore(
        human_mean=human_mean,
        ai_mean=ai_mean,
        separation=separation,
        passes_threshold=separation >= minimum_separation,
    )
