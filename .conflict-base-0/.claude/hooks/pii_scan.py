#!/usr/bin/env python3
from __future__ import annotations

import re

from _hook_utils import ask, get_shell_command, read_payload

PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
]

LOGGING_CONTEXT = re.compile(
    r"\b(echo|printf|logger|print\(|console\.log|curl|httpx)\b",
    re.IGNORECASE,
)


def main() -> None:
    payload = read_payload()
    command = get_shell_command(payload)
    if not command or not LOGGING_CONTEXT.search(command):
        return

    for pattern in PII_PATTERNS:
        if pattern.search(command):
            ask(
                "Potential PII detected in command text. Confirm before running.",
                f"PII scan matched `{pattern.pattern}` in command: {command}",
            )


if __name__ == "__main__":
    main()
