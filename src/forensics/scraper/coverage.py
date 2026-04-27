"""D-03 — scrape coverage summary from ``scrape_errors.jsonl``."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from forensics.storage.json_io import write_json_artifact

_AUTHOR_FROM_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"author=([\w-]+)"),
    re.compile(r"slug_not_in_manifest:([\w-]+)"),
    re.compile(r"^([\w-]+):\s"),
)


def write_scrape_coverage_summary(
    errors_path: Path,
    output_path: Path,
) -> Path | None:
    """Summarize line counts and top error kinds; returns ``output_path`` or ``None`` if no file."""
    if not errors_path.is_file():
        return None
    kinds: Counter[str] = Counter()
    n = 0
    for line in errors_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        n += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            kinds["json_decode_error"] += 1
            continue
        err = rec.get("error") or rec.get("message") or rec.get("kind") or "unknown"
        kinds[str(err)[:200]] += 1
    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "errors_path": str(errors_path),
        "line_count": n,
        "top_errors": kinds.most_common(50),
    }
    write_json_artifact(output_path, payload)
    return output_path


def write_crawl_summary_json(
    errors_path: Path,
    output_path: Path,
) -> Path | None:
    """L-04 — per-author error counts + global totals; written next to ``scrape_errors.jsonl``."""
    if not errors_path.is_file():
        return None
    by_author: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    n = 0
    for line in errors_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        n += 1
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            kinds["json_decode_error"] += 1
            by_author["_unparsed"] += 1
            continue
        err = str(rec.get("error") or rec.get("message") or rec.get("kind") or "unknown")
        kinds[err[:200]] += 1
        slug: str | None = None
        if isinstance(rec.get("author_slug"), str):
            slug = rec["author_slug"]
        if slug is None:
            for pat in _AUTHOR_FROM_ERROR_PATTERNS:
                m = pat.search(err)
                if m:
                    slug = m.group(1)
                    break
        by_author[slug or "_unknown"] += 1
    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "errors_path": str(errors_path),
        "line_count": n,
        "errors_by_author_slug": dict(sorted(by_author.items())),
        "top_errors": kinds.most_common(50),
    }
    write_json_artifact(output_path, payload)
    return output_path
