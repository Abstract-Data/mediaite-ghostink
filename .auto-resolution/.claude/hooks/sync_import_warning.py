#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from _hook_utils import append_log, extract_paths, read_payload

SYNC_IMPORT_MARKERS = ("requests", "subprocess", "time.sleep", "httpx.Client")


def main() -> None:
    payload = read_payload()
    paths = [path for path in extract_paths(payload) if path.endswith(".py")]
    api_paths = [path for path in paths if "/api/" in path or path.startswith("src/api/")]
    if not api_paths:
        return

    for rel_path in api_paths:
        path = Path(rel_path)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if any(marker in content for marker in SYNC_IMPORT_MARKERS):
            append_log(
                "sync_import_warnings.log",
                f"path={rel_path} warning=possible-sync-io-in-api-route",
            )


if __name__ == "__main__":
    main()
