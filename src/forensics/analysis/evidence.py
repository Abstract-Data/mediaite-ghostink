"""Shared evidence gates for confirmatory analysis outputs."""

from __future__ import annotations

from collections.abc import Iterable

from forensics.config.settings import AnalysisConfig
from forensics.models.analysis import ChangePoint

MIN_EVIDENCE_CONFIDENCE = 0.9


def filter_evidence_change_points(
    change_points: Iterable[ChangePoint],
    analysis_cfg: AnalysisConfig,
    *,
    min_confidence: float = MIN_EVIDENCE_CONFIDENCE,
) -> list[ChangePoint]:
    """Keep only change-points strong enough to count as confirmatory evidence."""
    return [
        cp
        for cp in change_points
        if cp.confidence >= min_confidence
        and abs(cp.effect_size_cohens_d) >= analysis_cfg.effect_size_threshold
    ]
