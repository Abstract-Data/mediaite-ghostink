"""JSONL export helpers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import weakref
from pathlib import Path
from typing import Any

from forensics.storage.json_io import ensure_parent
from forensics.storage.repository import Repository

_loop_jsonl_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


def _jsonl_append_lock_for_current_loop() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _loop_jsonl_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _loop_jsonl_locks[loop] = lock
    return lock


def append_jsonl(path: Path, record: dict[str, object]) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


async def append_jsonl_async(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON object to ``path``.

    Safe for concurrent async callers (per-event-loop lock + thread I/O).
    """
    ensure_parent(path)
    line = json.dumps(record, default=str) + "\n"

    def _write() -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    async with _jsonl_append_lock_for_current_loop():
        await asyncio.to_thread(_write)


def export_articles_jsonl(db_path: Path, output_path: Path, *, batch_size: int = 500) -> int:
    """Write all articles as JSON lines; returns number of records.

    Streams from SQLite so memory stays proportional to ``batch_size`` rather than
    corpus size.
    """
    ensure_parent(output_path)
    count = 0
    with Repository(db_path) as repo, output_path.open("w", encoding="utf-8") as handle:
        for article in repo.iter_all_articles(batch_size=batch_size):
            handle.write(json.dumps(article.model_dump(mode="json"), default=str) + "\n")
            count += 1
    _write_export_manifest(db_path, output_path, record_count=count)
    return count


def _sqlite_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_export_manifest(db_path: Path, output_path: Path, *, record_count: int) -> None:
    """D-06 — sidecar manifest with SQLite mtime + digest for export provenance."""
    manifest_path = output_path.with_name(output_path.name + ".manifest.json")
    st = db_path.stat()
    digest = _sqlite_sha256(db_path) if db_path.is_file() else ""
    payload = {
        "articles_db_path": str(db_path),
        "articles_db_mtime_ns": st.st_mtime_ns,
        "articles_db_sha256": digest,
        "export_record_count": record_count,
        "export_path": str(output_path),
    }
    ensure_parent(manifest_path)
    manifest_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
