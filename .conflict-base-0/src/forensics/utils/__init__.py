"""Shared utilities for text, hashing, and timestamps."""

from datetime import UTC, datetime

from forensics.utils.datetime import parse_datetime, parse_wp_datetime
from forensics.utils.hashing import content_hash, simhash
from forensics.utils.text import clean_text, normalize_whitespace, word_count


def utc_now_iso() -> str:
    """Return an ISO timestamp in UTC."""
    return datetime.now(UTC).isoformat()


__all__ = [
    "clean_text",
    "content_hash",
    "normalize_whitespace",
    "parse_datetime",
    "parse_wp_datetime",
    "simhash",
    "utc_now_iso",
    "word_count",
]
