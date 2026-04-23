#!/usr/bin/env python3
"""PostToolUse hook — Merge-Conflict Artifact Blocker

Blocks git commits that include staged paths matching merge-conflict
resolution artifacts.  These directories are written by automated merge
tools (GitButler, Claude migrations, etc.) and must never be tracked.

Severity: BLOCKER
Ported from: v0-quorum-report-redesign-concep/.husky/pre-commit
"""
from __future__ import annotations

import re

from _hook_utils import deny, get_shell_command, read_payload, run_command

# Patterns that indicate merge-conflict or migration artifacts.
ARTIFACT_RE = re.compile(
    r"^("
    r"\.auto-resolution/"
    r"|\.conflict-base-\d+/"
    r"|\.conflict-side-\d+/"
    r"|\.conflict-files$"
    r"|\.claude-migration/"
    r")"
)


def main() -> None:
    payload = read_payload()
    command = get_shell_command(payload)
    if "git commit" not in command:
        return

    staged = run_command(["git", "diff", "--cached", "--name-only", "--diff-filter=AM"])
    if staged.returncode != 0:
        return

    violations = [
        path
        for line in staged.stdout.splitlines()
        if (path := line.strip()) and ARTIFACT_RE.search(path)
    ]

    if violations:
        file_list = "\n".join(f"  - {v}" for v in violations[:10])
        deny(
            "Blocked commit: merge-conflict artifacts are staged.",
            (
                "Merge-conflict artifact blocker found staged paths that must not be "
                f"tracked ({len(violations)} match(es)):\n{file_list}\n\n"
                "Remove these paths with `git reset HEAD <path>` and delete them "
                "before committing."
            ),
        )


if __name__ == "__main__":
    main()
