"""Velocity acceleration helpers (N-05 — lives under ``utils`` to avoid import cycles)."""

from __future__ import annotations


def _signed_velocity_acceleration(velocities: list[float]) -> float | None:
    """Return the signed (late - early) / early velocity ratio, or ``None``."""
    if len(velocities) < 6:
        return None
    mid = len(velocities) // 2
    early = sum(velocities[:mid]) / max(mid, 1)
    late = sum(velocities[mid:]) / max(len(velocities) - mid, 1)
    if early <= 0:
        return None
    return (late - early) / early


def compute_velocity_acceleration(velocities: list[float]) -> float:
    """Return the (late - early) / early velocity ratio, clamped to ``[0, 1]``."""
    ratio = _signed_velocity_acceleration(velocities)
    if ratio is None:
        return 0.0
    return min(max(ratio, 0.0), 1.0)


def describe_velocity_acceleration_pct(velocities: list[float]) -> str | None:
    """Return a ``"increased by 42%"`` style phrase, or ``None`` when undefined."""
    ratio = _signed_velocity_acceleration(velocities)
    if ratio is None:
        return None
    pct = ratio * 100.0
    direction = "increased" if pct >= 0 else "decreased"
    return f"{direction} by {abs(pct):.0f}%"


__all__ = [
    "compute_velocity_acceleration",
    "describe_velocity_acceleration_pct",
]
