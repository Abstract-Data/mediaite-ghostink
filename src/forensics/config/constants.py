"""Shared config defaults referenced from multiple nested settings models."""

from __future__ import annotations

# Survey + features must stay aligned (see ForensicsSettings._excluded_sections_match_survey).
DEFAULT_EXCLUDED_SECTIONS: frozenset[str] = frozenset({"sponsored", "partner-content", "crosspost"})
