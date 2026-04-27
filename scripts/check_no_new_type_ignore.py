#!/usr/bin/env python3
"""Fail if the current branch introduces new ``# type: ignore`` lines under ``src/`` or ``tests/``.

Compares ``git diff <base_ref>...HEAD`` so only **added** lines are considered. Intended for
pull-request CI and local pre-push checks.

Usage:
    uv run python scripts/check_no_new_type_ignore.py [BASE_REF]

BASE_REF defaults to ``origin/main`` (fetch that ref before running locally).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import PurePosixPath

# Match mypy/pyright-style ignores on an added source line (not substring-only in strings).
_TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore(?:\[[^\]]+\])?")


def _run_git_diff(base_ref: str) -> str:
    proc = subprocess.run(
        ["git", "diff", f"{base_ref}...HEAD", "--", "src", "tests"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or f"git diff exited {proc.returncode}"
        print(f"error: {msg}", file=sys.stderr)
        sys.exit(2)
    return proc.stdout


def _violations(diff_text: str) -> list[tuple[str, str]]:
    """Return (path, line) for each added line containing a type: ignore in a .py file."""
    current_py: str | None = None
    hits: list[tuple[str, str]] = []
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path_part = raw[4:].strip()
            if path_part == "/dev/null":
                current_py = None
                continue
            # Normalize "b/path" from unified diff
            if path_part.startswith("b/"):
                path_part = path_part[2:]
            p = PurePosixPath(path_part)
            current_py = path_part if p.suffix == ".py" else None
            continue
        if current_py is None:
            continue
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        added = raw[1:]
        if _TYPE_IGNORE.search(added):
            hits.append((current_py, added.strip()))
    return hits


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    diff_text = _run_git_diff(base)
    hits = _violations(diff_text)
    if not hits:
        return 0
    print(
        "New ``# type: ignore`` (or ``type: ignore[...]``) lines were added under "
        f"``src/`` or ``tests/`` compared to {base!r}.",
        file=sys.stderr,
    )
    print(
        "Remove or replace with proper typing; document rare exceptions in an ADR.",
        file=sys.stderr,
    )
    for path, line in hits:
        print(f"  {path}: {line}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
