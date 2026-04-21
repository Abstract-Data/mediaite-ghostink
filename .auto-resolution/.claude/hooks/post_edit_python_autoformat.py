#!/usr/bin/env python3
from __future__ import annotations

from _hook_utils import extract_paths, read_payload, run_command


def main() -> None:
    payload = read_payload()
    paths = [
        path
        for path in extract_paths(payload)
        if path.endswith(".py") and path.startswith(("src/", "tests/"))
    ]
    if not paths:
        return
    run_command(["uv", "run", "ruff", "format", *sorted(set(paths))])


if __name__ == "__main__":
    main()
