#!/usr/bin/env python3
"""Merge per-author embedding manifest shards into the canonical ``manifest.jsonl``.

Reads the current canonical manifest plus every ``data/embeddings/*_manifest.jsonl``
shard, dedupes by ``article_id`` (last-wins, matching ``read_embeddings_manifest``
semantics), writes the canonical manifest atomically, and removes shards.

Used by the parallel-extract workflow: each ``forensics extract --author <slug>``
writes ``<slug>_manifest.jsonl``; this script consolidates them once all
extracts complete, before ``forensics analyze`` consumes the canonical manifest.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from forensics.storage.parquet import read_embeddings_manifest, write_embeddings_manifest

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("merge_manifest")


def main() -> int:
    emb_dir = Path("data/embeddings")
    canonical = emb_dir / "manifest.jsonl"
    if not emb_dir.is_dir():
        print(f"error: {emb_dir} not found", file=sys.stderr)
        return 1

    by_id: dict[str, object] = {}
    if canonical.is_file():
        for rec in read_embeddings_manifest(canonical):
            by_id[rec.article_id] = rec
        log.info("merge: canonical manifest start = %d row(s)", len(by_id))

    shards = sorted(p for p in emb_dir.glob("*_manifest.jsonl") if p.name != "manifest.jsonl")
    for shard in shards:
        added = 0
        for rec in read_embeddings_manifest(shard):
            by_id[rec.article_id] = rec
            added += 1
        log.info("merge: %s contributed %d row(s)", shard.name, added)

    write_embeddings_manifest(list(by_id.values()), canonical)
    log.info(
        "merge: wrote canonical manifest with %d row(s) from %d shard(s)",
        len(by_id),
        len(shards),
    )

    for shard in shards:
        shard.unlink()
    if shards:
        log.info("merge: cleaned up %d shard file(s)", len(shards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
