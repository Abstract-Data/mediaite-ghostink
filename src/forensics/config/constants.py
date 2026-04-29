"""Shared config defaults referenced from multiple nested settings models."""

from __future__ import annotations

from typing import Any

# Pydantic Field(json_schema_extra=...) — marks fields included in preregistration/config hash.
CONFIG_HASH_EXTRA: dict[str, Any] = {"include_in_config_hash": True}

# Survey owns excluded_sections; ForensicsSettings mirrors into features (see settings.py).
DEFAULT_EXCLUDED_SECTIONS: frozenset[str] = frozenset({"sponsored", "partner-content", "crosspost"})
