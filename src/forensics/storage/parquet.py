"""Parquet persistence for feature tables (Phase 4)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from forensics.models.features import EmbeddingRecord, FeatureVector

_DICT_FIELDS = frozenset(
    {
        "function_word_distribution",
        "punctuation_profile",
        "pos_bigram_top30",
        "clause_initial_top10",
    },
)


def _serialize_record(rec: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in rec.items():
        if k in _DICT_FIELDS and isinstance(v, dict):
            out[k] = json.dumps(v, sort_keys=True)
        else:
            out[k] = v
    return out


def write_features(features: list[FeatureVector], output_path: Path) -> None:
    """Write feature vectors to Parquet (dict fields as JSON strings)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_serialize_record(f.to_flat_dict()) for f in features]
    pl.DataFrame(rows).write_parquet(output_path)


def scan_features(path: Path) -> pl.LazyFrame:
    """Lazy Parquet scan — prefer this over :func:`read_features` for new code.

    ``pl.LazyFrame`` lets downstream callers push filters/projections down
    before :meth:`.collect` materialises the frame.
    """
    return pl.scan_parquet(path)


def read_features(path: Path) -> pl.DataFrame:
    """Eagerly load a feature Parquet table.

    Prefer :func:`scan_features` for new code so predicate pushdown stays
    available; ``read_features`` remains for notebooks and tests that want a
    materialised frame.
    """
    return scan_features(path).collect()


def load_feature_frame_sorted(features_path: Path) -> pl.LazyFrame:
    """Return a ``LazyFrame`` for the feature Parquet, sorted by ``timestamp``.

    Returning a ``LazyFrame`` lets downstream callers push ``filter(...)``
    predicates (e.g. per-author slicing) into the scan before materialization
    (P2-PERF-002). Call ``.collect()`` at the boundary where a ``DataFrame`` is
    required. For the small number of eager callers, use
    :func:`load_feature_frame_sorted_eager`.
    """
    lf = scan_features(features_path)
    if "timestamp" not in lf.collect_schema().names():
        msg = f"features parquet missing timestamp: {features_path}"
        raise ValueError(msg)
    return lf.sort("timestamp")


def load_feature_frame_sorted_eager(features_path: Path) -> pl.DataFrame:
    """Eager convenience wrapper around :func:`load_feature_frame_sorted`."""
    return load_feature_frame_sorted(features_path).collect()


def write_embeddings_manifest(records: list[EmbeddingRecord], path: Path) -> None:
    """Atomically rewrite the embedding manifest JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r.model_dump(mode="json"), sort_keys=True) for r in records]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    tmp.replace(path)


def read_embeddings_manifest(path: Path) -> list[EmbeddingRecord]:
    if not path.is_file():
        return []
    out: list[EmbeddingRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(EmbeddingRecord.model_validate_json(line))
    return out


# Per-author batch file (Phase 5): many articles, one compressed NPZ on disk.
AUTHOR_EMBEDDING_BATCH_BASENAME = "batch.npz"

# NPZ keys: UTF-8 ids as int32 lengths + uint8 blob (no object dtype / no pickle on load).
EMBEDDING_BATCH_KEY_LENGTHS = "article_id_lengths"
EMBEDDING_BATCH_KEY_BYTES = "article_id_bytes"
EMBEDDING_BATCH_KEY_VECTORS = "vectors"


def _pack_article_ids_utf8(ids: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    encoded = [str(x).encode("utf-8") for x in ids]
    lengths = np.array([len(e) for e in encoded], dtype=np.int32)
    blob = b"".join(encoded)
    flat = np.frombuffer(blob, dtype=np.uint8).copy()
    return lengths, flat


def unpack_article_ids_from_embedding_batch(
    lengths: np.ndarray,
    flat: np.ndarray,
) -> list[str]:
    """Decode ``article_id_lengths`` + ``article_id_bytes`` from a secure batch NPZ."""
    lens = np.asarray(lengths, dtype=np.int64).ravel()
    buf = np.asarray(flat, dtype=np.uint8).ravel()
    expected = int(lens.sum())
    if expected != buf.size:
        msg = f"article_id lengths sum ({expected}) != bytes length ({buf.size})"
        raise ValueError(msg)
    data = buf.tobytes()
    pos = 0
    out: list[str] = []
    for ln in lens:
        n = int(ln)
        out.append(data[pos : pos + n].decode("utf-8"))
        pos += n
    return out


def write_author_embedding_batch(
    path: Path,
    article_ids: Sequence[str],
    vectors: np.ndarray,
) -> None:
    """Persist one author's embeddings as UTF-8 id packing + 2-D ``vectors`` (float32).

    On-disk arrays: ``article_id_lengths`` (int32), ``article_id_bytes`` (uint8),
    ``vectors`` (float32, 2-D). This avoids NumPy object arrays so archives load
    with ``np.load(..., allow_pickle=False)``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mat = np.asarray(vectors, dtype=np.float32)
    if mat.ndim != 2:
        msg = f"vectors must be 2-D, got shape {mat.shape}"
        raise ValueError(msg)
    ids = list(article_ids)
    if len(ids) != mat.shape[0]:
        msg = f"article_ids length ({len(ids)}) != vectors rows ({mat.shape[0]})"
        raise ValueError(msg)
    id_lengths, id_bytes = _pack_article_ids_utf8(ids)
    np.savez_compressed(
        path,
        **{
            EMBEDDING_BATCH_KEY_LENGTHS: id_lengths,
            EMBEDDING_BATCH_KEY_BYTES: id_bytes,
            EMBEDDING_BATCH_KEY_VECTORS: mat,
        },
    )
