#!/usr/bin/env python3
from __future__ import annotations

from _hook_utils import deny, get_shell_command, read_payload, run_command


def main() -> None:
    payload = read_payload()
    command = get_shell_command(payload)
    if "git commit" not in command:
        return

    staged_files = run_command(["git", "diff", "--cached", "--name-only"])
    if staged_files.returncode != 0:
        return

    source_count = 0
    test_count = 0
    for path in [line.strip() for line in staged_files.stdout.splitlines() if line.strip()]:
        if path.startswith("src/") and path.endswith(".py"):
            source_count += 1
        if path.startswith("tests/") and path.endswith(".py"):
            test_count += 1

    if source_count > 3 and test_count == 0:
        deny(
            "Blocked commit: too many source changes without tests.",
            (
                "Tests-required gate blocked commit because more than 3 Python source files "
                f"were staged without test updates (source={source_count}, tests={test_count})."
            ),
        )


if __name__ == "__main__":
    main()
