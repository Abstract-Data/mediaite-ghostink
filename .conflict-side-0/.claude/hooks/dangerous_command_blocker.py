#!/usr/bin/env python3
from __future__ import annotations

import re

from _hook_utils import ask, deny, get_shell_command, read_payload

BLOCK_PATTERNS = [
    re.compile(r"\brm\s+-rf\s+/(?:\s|$)"),
    re.compile(r"\brm\s+-rf\s+~(?:\s|$)"),
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bmkfs(?:\.\w+)?\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r":\(\)\s*\{:\|:&\};:"),
]

ASK_PATTERNS = [
    re.compile(r"\bterraform\s+apply\b"),
    re.compile(r"\bkubectl\s+delete\b"),
    re.compile(r"\bwrangler\s+deploy\b"),
]


def main() -> None:
    payload = read_payload()
    command = get_shell_command(payload)
    if not command:
        return

    for pattern in BLOCK_PATTERNS:
        if pattern.search(command):
            deny(
                "Blocked a destructive shell command.",
                f"Dangerous command matched blocker pattern: {pattern.pattern}",
            )

    for pattern in ASK_PATTERNS:
        if pattern.search(command):
            ask(
                (
                    "This command may perform a destructive or production action. "
                    "Confirm before running."
                ),
                f"Command matched high-risk review pattern: {pattern.pattern}",
            )


if __name__ == "__main__":
    main()
