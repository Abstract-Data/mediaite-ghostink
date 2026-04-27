"""Shared datetime parsing for WordPress API strings and SQLite row values."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl


def parse_datetime(value: object, *, naive_as_utc: bool = False) -> datetime:
    """
    Parse ISO-like values from the DB or APIs.

    * ``naive_as_utc=False`` (default): matches legacy SQLite row parsing — naive
      datetimes are left naive except for ``Z`` normalization.
    * ``naive_as_utc=True``: WordPress-style strings where a naive instant is UTC.
    """
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    if len(text) == 10:
        return datetime.fromisoformat(f"{text}T00:00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None and naive_as_utc:
        return dt.replace(tzinfo=UTC)
    return dt


def parse_wp_datetime(value: str) -> datetime:
    """Parse WordPress ``date`` / ``modified`` fields as timezone-aware (UTC if naive)."""
    return parse_datetime(value, naive_as_utc=True)


def normalize_stored_datetime(value: datetime) -> datetime:
    """D-02 — canonical UTC instant for persistence comparisons (naive → UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def timestamps_from_frame(df: pl.DataFrame, col: str = "timestamp") -> list[datetime]:
    """Materialize a Polars timestamp column into a list of ``datetime`` objects.

    Centralizes the ``df[col].to_list()`` → ``[parse_datetime(t) for t in ...]``
    two-liner that used to repeat across the analysis stages (RF-DRY-003).
    """
    return [parse_datetime(t) for t in df[col].to_list()]
