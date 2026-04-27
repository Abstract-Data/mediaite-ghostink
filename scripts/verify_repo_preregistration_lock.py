#!/usr/bin/env python3
"""Ensure the committed preregistration lock verifies as *ok* against repo ``config.toml``.

Used in CI (``.github/workflows/ci-quality.yml``) so merges cannot ship a lock that is
still a template, missing on disk, or out of sync with analysis thresholds in
``config.toml``.

Local (same check as CI):

    uv run python scripts/verify_repo_preregistration_lock.py

This always resolves settings from the repository root ``config.toml`` next to this
script's parent directory, ignoring ``FORENSICS_CONFIG_FILE``, so the gate matches what
CI evaluates after checkout.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from forensics.config import get_settings
from forensics.preregistration import verify_preregistration


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    lock = root / "data" / "preregistration" / "preregistration_lock.json"
    cfg = root / "config.toml"

    if not cfg.is_file():
        print(f"error: expected config at {cfg}", file=sys.stderr)
        return 1
    if not lock.is_file():
        print(f"error: missing committed lock at {lock}", file=sys.stderr)
        return 1

    os.environ["FORENSICS_CONFIG_FILE"] = str(cfg)

    get_settings.cache_clear()
    try:
        settings = get_settings()
        result = verify_preregistration(settings, lock_path=lock)
    finally:
        get_settings.cache_clear()

    if result.status != "ok":
        print(
            f"error: preregistration verify returned {result.status!r}: {result.message}",
            file=sys.stderr,
        )
        for diff in result.diffs[:50]:
            print(f"  diff: {diff}", file=sys.stderr)
        if len(result.diffs) > 50:
            print(f"  ... and {len(result.diffs) - 50} more diffs", file=sys.stderr)
        return 1

    print(result.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
