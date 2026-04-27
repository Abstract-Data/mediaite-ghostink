#!/usr/bin/env python3
"""T-05 — assert minimum line coverage for newer ``forensics.analysis`` modules.

Reads ``coverage.json`` produced by ``pytest --cov-report=json:coverage.json``.
Run after the main test job so the file exists (CI and local full-suite runs).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Suffixes under ``src/forensics/analysis/`` tracked for punch-list visibility.
# Floors are set ~10 points below observed full-suite coverage (2026-04 baseline).
_ANALYSIS_MODULE_SUFFIXES: dict[str, float] = {
    "analysis/section_mix.py": 80.0,
    "analysis/section_contrast.py": 75.0,
    "analysis/permutation.py": 80.0,
    "analysis/era.py": 75.0,
}


def _percent_for_suffix(files: dict[str, dict], suffix: str) -> float | None:
    for path, meta in files.items():
        if path.replace("\\", "/").endswith(f"forensics/{suffix}"):
            return float(meta["summary"]["percent_covered"])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "coverage_json",
        nargs="?",
        default="coverage.json",
        type=Path,
        help="Path to coverage.py JSON report (default: ./coverage.json)",
    )
    args = parser.parse_args()
    path: Path = args.coverage_json
    if not path.is_file():
        print(
            f"skip: {path} not found (run full pytest with --cov-report=json first)",
            file=sys.stderr,
        )
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    files: dict[str, dict] = data.get("files", {})
    failures: list[str] = []
    print("forensics analysis module coverage (T-05):")
    for suffix, floor in sorted(_ANALYSIS_MODULE_SUFFIXES.items()):
        pct = _percent_for_suffix(files, suffix)
        if pct is None:
            failures.append(f"{suffix}: not present in coverage.json")
            print(f"  {suffix}: MISSING")
            continue
        print(f"  {suffix}: {pct:.1f}% (floor {floor:.1f}%)")
        if pct + 1e-6 < floor:
            failures.append(f"{suffix}: {pct:.1f}% < {floor:.1f}%")
    if failures:
        print("FAIL:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
