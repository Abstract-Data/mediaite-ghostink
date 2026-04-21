#!/usr/bin/env python3
from __future__ import annotations

import re

from _hook_utils import deny, get_shell_command, is_probably_binary, read_payload, run_command

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|PGP) PRIVATE KEY-----"),
    re.compile(r"\b(?:api|secret|token|password)[\w-]*\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]


def main() -> None:
    payload = read_payload()
    command = get_shell_command(payload)
    if "git commit" not in command:
        return

    staged_files = run_command(["git", "diff", "--cached", "--name-only"])
    if staged_files.returncode != 0:
        return

    for path in [line.strip() for line in staged_files.stdout.splitlines() if line.strip()]:
        if is_probably_binary(path):
            continue
        staged_blob = run_command(["git", "show", f":{path}"])
        if staged_blob.returncode != 0:
            continue
        content = staged_blob.stdout
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                deny(
                    "Blocked commit due to potential secret in staged files.",
                    f"Secret scanner matched `{pattern.pattern}` in staged file `{path}`.",
                )


if __name__ == "__main__":
    main()
