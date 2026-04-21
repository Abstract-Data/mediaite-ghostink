"""Storage backends: SQLite repository, exports, and future Parquet/DuckDB."""

from forensics.storage.export import append_jsonl, export_articles_jsonl
from forensics.storage.repository import (
    Repository,
    UnfetchedArticle,
    UnfetchedUrl,
    init_db,
)

__all__ = [
    "Repository",
    "UnfetchedArticle",
    "UnfetchedUrl",
    "append_jsonl",
    "export_articles_jsonl",
    "init_db",
]
