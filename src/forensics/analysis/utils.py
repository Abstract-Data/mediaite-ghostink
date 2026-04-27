"""Analysis-shared helpers.

Cross-stage helpers (``intervals_overlap``, ``closed_interval_contains``,
``load_feature_frame_for_author``, ``resolve_author_rows``) have been hoisted
to :mod:`forensics.paths` to avoid a cross-stage import from ``features/`` back
into ``analysis/`` (see RF-ARCH-001).

.. deprecated:: Phase 13 (Run 7, RF-ARCH-001 G2)
   In-tree callers have been migrated to import directly from
   :mod:`forensics.paths`. These re-exports remain for one release cycle
   to avoid breaking external consumers; new code must import from
   ``forensics.paths``. They will be removed in a future release.
"""

from __future__ import annotations

from typing import NamedTuple

# DEPRECATED re-exports — import from forensics.paths directly (RF-ARCH-001 / G2).
from forensics.paths import (
    closed_interval_contains,
    intervals_overlap,
    load_feature_frame_for_author,
    resolve_author_rows,
)
from forensics.utils.velocity_metrics import (
    compute_velocity_acceleration,
    describe_velocity_acceleration_pct,
)


class MonthlyLabeledVelocity(NamedTuple):
    """Month key (``YYYY-MM``) with embedding drift velocity (RF-SMELL-006)."""

    month: str
    velocity: float


def pair_months_with_velocities(
    monthly: list[tuple[str, object]],
    velocities: list[float],
) -> list[MonthlyLabeledVelocity]:
    """Pair each velocity with the month label of the *later* of the two centroids.

    ``monthly`` is a list of ``(YYYY-MM, centroid_vector)`` tuples ordered by
    time. ``velocities[i]`` measures the cosine distance between month ``i``
    and month ``i+1``, so we label it with ``monthly[i + 1][0]``.
    """
    return [
        MonthlyLabeledVelocity(monthly[i + 1][0], velocities[i])
        for i in range(min(len(velocities), max(len(monthly) - 1, 0)))
    ]


__all__ = [
    "MonthlyLabeledVelocity",
    "closed_interval_contains",
    "compute_velocity_acceleration",
    "describe_velocity_acceleration_pct",
    "intervals_overlap",
    "load_feature_frame_for_author",
    "pair_months_with_velocities",
    "resolve_author_rows",
]
