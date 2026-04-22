"""Storage backends: SQLite repository, exports, and future Parquet/DuckDB."""

from forensics.storage.export import append_jsonl, append_jsonl_async, export_articles_jsonl
from forensics.storage.repository import (
    Repository,
    UnfetchedArticle,
    UnfetchedUrl,
    init_db,
    insert_analysis_run,
)

__all__ = [
    "Repository",
    "UnfetchedArticle",
    "UnfetchedUrl",
    "append_jsonl",
    "append_jsonl_async",
    "export_articles_jsonl",
    "init_db",
    "insert_analysis_run",
]
