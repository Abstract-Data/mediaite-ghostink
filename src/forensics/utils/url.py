"""URL helpers shared across ingest and analysis (Phase 15 Step J1 foundation).

The primary helper is :func:`section_from_url`, which derives a section tag
from the first path segment of a mediaite.com article URL. The regex-based
extraction is pinned here so feature extraction and the feature-parquet
migration apply byte-identical logic.
"""

from __future__ import annotations

import re

__all__ = ["section_from_url"]

_SECTION_RE = re.compile(r"^https?://(?:www\.)?mediaite\.com/([a-z0-9-]+)/", re.I)


def section_from_url(url: str | None) -> str:
    """Return the lowercased first path segment, or ``"unknown"`` if it can't be parsed.

    100% coverage against the current corpus; any new URL shape that fails the
    regex yields ``"unknown"`` (the feature-extraction stage emits a WARNING
    so the mismatch surfaces in logs).
    """
    if not url:
        return "unknown"
    match = _SECTION_RE.match(url)
    if not match:
        return "unknown"
    seg = match.group(1).lower()
    # D-07 — year-only first segments are not editorial sections.
    if len(seg) == 4 and seg.isdigit():
        return "unknown"
    return seg
