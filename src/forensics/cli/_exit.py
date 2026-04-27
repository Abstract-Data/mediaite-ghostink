"""Semantic exit codes for the ``forensics`` CLI (agent-friendly contract)."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Stable process exit codes — see ``docs/EXIT_CODES.md``."""

    OK = 0
    GENERAL_ERROR = 1
    USAGE_ERROR = 2
    AUTH_OR_RESOURCE = 3
    TRANSIENT = 4
    CONFLICT = 5
