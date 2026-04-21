#!/usr/bin/env python3
from __future__ import annotations

from _hook_utils import append_log, extract_paths, read_payload, run_command


def main() -> None:
    payload = read_payload()
    paths = [path for path in extract_paths(payload) if path.endswith(".py")]
    touched_src = [path for path in paths if path.startswith("src/")]
    if not touched_src:
        return

    result = run_command(["uv", "run", "pytest", "tests/unit", "-q", "--maxfail=1"])
    status = "pass" if result.returncode == 0 else "fail"
    append_log("post_edit_tests.log", f"status={status} files={','.join(sorted(set(touched_src)))}")


if __name__ == "__main__":
    main()
