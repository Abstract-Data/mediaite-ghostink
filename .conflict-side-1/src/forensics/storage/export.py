"""JSONL export helpers."""

from __future__ import annotations

import json
from pathlib import Path

from forensics.storage.repository import Repository


def append_jsonl(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def export_articles_jsonl(db_path: Path, output_path: Path) -> int:
    """Write all articles as JSON lines; returns number of records."""
    articles = Repository(db_path).get_all_articles()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for article in articles:
            handle.write(json.dumps(article.model_dump(mode="json"), default=str) + "\n")
            count += 1
    return count
