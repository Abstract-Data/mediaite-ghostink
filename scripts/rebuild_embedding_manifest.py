"""Rebuild ``data/embeddings/manifest.jsonl`` from on-disk ``batch.npz`` files.

Recovery utility for inconsistent manifest state — e.g., when an extract run
crashed mid-write and only flushed a subset of authors. The packed batch files
are authoritative (they hold both vectors and article IDs); the manifest is
derivable from them plus ``data/articles.db``.

Usage::

    uv run python scripts/rebuild_embedding_manifest.py [--dry-run]

The previous manifest is renamed to ``manifest.jsonl.broken`` before the new
one is written.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

logger = logging.getLogger("rebuild_embedding_manifest")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from forensics.config import get_settings  # noqa: E402
from forensics.storage.parquet import (  # noqa: E402
    EMBEDDING_BATCH_KEY_BYTES,
    EMBEDDING_BATCH_KEY_LENGTHS,
    EMBEDDING_BATCH_KEY_VECTORS,
    unpack_article_ids_from_embedding_batch,
)
from forensics.storage.repository import Repository  # noqa: E402


def _load_packed_batch(npz_path: Path) -> tuple[list[str], np.ndarray] | None:
    z = np.load(npz_path, allow_pickle=False)
    keys = frozenset(z.files)
    if not (
        EMBEDDING_BATCH_KEY_LENGTHS in keys
        and EMBEDDING_BATCH_KEY_BYTES in keys
        and EMBEDDING_BATCH_KEY_VECTORS in keys
    ):
        logger.warning("skip non-packed batch: %s", npz_path)
        return None
    ids = unpack_article_ids_from_embedding_batch(
        z[EMBEDDING_BATCH_KEY_LENGTHS],
        z[EMBEDDING_BATCH_KEY_BYTES],
    )
    mat = np.asarray(z[EMBEDDING_BATCH_KEY_VECTORS], dtype=np.float32)
    if mat.ndim != 2 or mat.shape[0] != len(ids):
        logger.warning("shape mismatch in %s: ids=%d, mat=%s", npz_path, len(ids), mat.shape)
        return None
    return ids, mat


def main(argv: list[str] | None = None) -> int:  # noqa: C901
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only; do not write")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    settings = get_settings()
    embeddings_dir = PROJECT_ROOT / "data" / "embeddings"
    db_path = PROJECT_ROOT / "data" / "articles.db"
    manifest_path = embeddings_dir / "manifest.jsonl"

    if not embeddings_dir.is_dir():
        logger.error("embeddings dir missing: %s", embeddings_dir)
        return 1
    if not db_path.is_file():
        logger.error("articles.db missing: %s", db_path)
        return 1

    model_name = settings.analysis.embedding_model
    model_version = settings.analysis.embedding_model_version

    # Build (article_id -> (author_id, published_date)) lookup once.
    article_meta: dict[str, tuple[str, str]] = {}
    with Repository(db_path) as repo:
        conn = repo._conn  # type: ignore[attr-defined]
        for row in conn.execute("SELECT id, author_id, published_date FROM articles"):
            article_meta[row[0]] = (row[1], row[2])
    logger.info("loaded %d article metadata rows from db", len(article_meta))

    new_records: list[dict[str, object]] = []
    per_author_counts: dict[str, int] = {}
    skipped_unknown: int = 0

    for author_dir in sorted(embeddings_dir.iterdir()):
        if not author_dir.is_dir():
            continue
        slug = author_dir.name
        npz_path = author_dir / "batch.npz"
        if not npz_path.is_file():
            continue
        loaded = _load_packed_batch(npz_path)
        if loaded is None:
            continue
        ids, mat = loaded
        emb_dim = int(mat.shape[1])
        rel_path = npz_path.relative_to(PROJECT_ROOT).as_posix()
        kept = 0
        for article_id in ids:
            meta = article_meta.get(article_id)
            if meta is None:
                skipped_unknown += 1
                continue
            author_id, published_date = meta
            new_records.append(
                {
                    "article_id": article_id,
                    "author_id": author_id,
                    "timestamp": published_date,
                    "model_name": model_name,
                    "model_version": model_version,
                    "model_revision": "",
                    "embedding_path": rel_path,
                    "embedding_dim": emb_dim,
                }
            )
            kept += 1
        per_author_counts[slug] = kept
        logger.info("  %s: %d entries (batch shape=%s)", slug, kept, mat.shape)

    logger.info(
        "rebuilt manifest: %d total entries across %d authors (skipped %d ids unknown to db)",
        len(new_records),
        len(per_author_counts),
        skipped_unknown,
    )

    if args.dry_run:
        logger.info("dry-run; not writing")
        return 0

    if manifest_path.is_file():
        broken_path = manifest_path.with_suffix(".jsonl.broken")
        manifest_path.replace(broken_path)
        logger.info("renamed previous manifest to %s", broken_path.name)

    with manifest_path.open("w", encoding="utf-8") as f:
        for rec in new_records:
            f.write(json.dumps(rec) + "\n")
    logger.info("wrote %s", manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
