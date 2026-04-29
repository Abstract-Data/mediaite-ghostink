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

import argparse
import logging
import sys

from forensics.config import get_project_root
from forensics.models.features import EmbeddingRecord
from forensics.storage.parquet import read_embeddings_manifest, write_embeddings_manifest

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("merge_manifest")


def main(*, dry_run: bool = False) -> int:
    project_root = get_project_root()
    emb_dir = project_root / "data" / "embeddings"
    canonical = emb_dir / "manifest.jsonl"
    if not emb_dir.is_dir():
        print(f"error: {emb_dir} not found", file=sys.stderr)
        return 1

    by_id: dict[str, EmbeddingRecord] = {}
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

    if dry_run:
        log.info(
            "merge: would write canonical manifest with %d row(s) from %d shard(s)",
            len(by_id),
            len(shards),
        )
        if shards:
            shard_names = ", ".join(s.name for s in shards)
            log.info("merge: would clean up %d shard file(s): %s", len(shards), shard_names)
    else:
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
    parser = argparse.ArgumentParser(
        description="Merge embedding manifest shards into canonical manifest.jsonl",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview merge and cleanup without writing any files",
    )
    args = parser.parse_args()
    raise SystemExit(main(dry_run=args.dry_run))
