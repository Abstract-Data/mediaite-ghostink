"""Era bucketing for AI-marker change-point evidence."""

from __future__ import annotations

from datetime import date

from forensics.models.analysis import ChangePoint, EraClassification

__all__ = ["classify_ai_marker_era"]

ERA_BUCKETS: tuple[tuple[str, date | None, date | None], ...] = (
    ("pre_nov_2022", None, date(2022, 11, 1)),
    ("nov_2022_to_mar_2023", date(2022, 11, 1), date(2023, 3, 1)),
    ("mar_2023_to_dec_2023", date(2023, 3, 1), date(2024, 1, 1)),
    ("post_dec_2023", date(2024, 1, 1), None),
)


def _bucket_for(value: date) -> str:
    for name, start, end in ERA_BUCKETS:
        if start is not None and value < start:
            continue
        if end is not None and value >= end:
            continue
        return name
    return "post_dec_2023"


def classify_ai_marker_era(change_points: list[ChangePoint]) -> EraClassification:
    """Bucket gated ``ai_marker_frequency`` change-points into adoption eras."""
    counts = {name: 0 for name, _start, _end in ERA_BUCKETS}
    for cp in change_points:
        if cp.feature_name != "ai_marker_frequency":
            continue
        counts[_bucket_for(cp.timestamp.date())] += 1

    total = sum(counts.values())
    dominant = None
    if total:
        dominant = max(counts, key=lambda key: (counts[key], -list(counts).index(key)))
    return EraClassification(
        ai_marker_change_points_by_era=counts,
        dominant_era=dominant,
        total_ai_marker_change_points=total,
    )
