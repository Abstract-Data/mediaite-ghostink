"""Parquet persistence for feature tables (Phase 4)."""

from __future__ import annotations

import json
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from forensics.models.features import EmbeddingRecord, FeatureVector
from forensics.storage.json_io import ensure_parent

_DICT_FIELDS = frozenset(
    {
        "function_word_distribution",
        "punctuation_profile",
        "pos_bigram_top30",
        "clause_initial_top10",
    },
)

# Phase 15 Step 0.3 — feature parquet schema bookkeeping. Writers stamp
# ``forensics.schema_version`` into parquet key/value metadata; the loader
# rejects parquets stamped with a lower version and demands a migration
# (see ``src/forensics/storage/migrations/002_feature_parquet_section.py``).
FEATURE_PARQUET_SCHEMA_METADATA_KEY = "forensics.schema_version"


class SchemaMigrationRequired(RuntimeError):
    """Raised when a feature parquet needs migration to the current schema.

    Operators resolve this by running ``forensics features migrate`` (see
    ``src/forensics/cli/migrate.py``). The message carries both the observed
    on-disk version and the version the current settings demand.
    """

    def __init__(self, path: Path, found: int | None, required: int) -> None:
        self.path = path
        self.found = found
        self.required = required
        found_str = "absent" if found is None else str(found)
        super().__init__(
            f"feature parquet at {path} requires schema migration: "
            f"found={found_str}, required={required}. "
            "Run `forensics features migrate` (see docs/RUNBOOK.md)."
        )


def _read_parquet_schema_version(path: Path) -> int | None:
    """Return the ``forensics.schema_version`` stamped in parquet metadata, or None."""
    try:
        import pyarrow.parquet as pq
    except ImportError:  # pragma: no cover — pyarrow ships with polars
        return None
    try:
        meta = pq.read_metadata(path)
    except (OSError, ValueError):
        return None
    kv = meta.metadata or {}
    raw = kv.get(FEATURE_PARQUET_SCHEMA_METADATA_KEY.encode())
    if raw is None:
        return None
    try:
        return int(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except (TypeError, ValueError):
        return None


def merge_parquet_metadata(path: Path, extra: dict[str, str]) -> None:
    """Merge string key/value pairs into Parquet Arrow schema metadata (N-04).

    Used after :func:`write_parquet_atomic` to attach non-schema version tags
    such as ``forensics.ai_marker_list_version`` without bumping the integer
    ``forensics.schema_version`` contract.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError:  # pragma: no cover
        return
    try:
        table = pq.read_table(path)
    except (OSError, ValueError):
        return
    meta = dict(table.schema.metadata or {})
    for k, v in extra.items():
        meta[k.encode("utf-8")] = str(v).encode("utf-8")
    table = table.replace_schema_metadata(meta)
    pq.write_table(table, path)


def _stamp_parquet_schema_version(path: Path, version: int) -> None:
    """Rewrite ``path`` preserving data but adding our schema-version key.

    Parquet metadata is immutable in-place, so we round-trip the file through
    pyarrow to attach the key. Called from :func:`write_parquet_atomic` and
    :func:`write_features` after the initial Polars write.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError:  # pragma: no cover
        return
    try:
        table = pq.read_table(path)
    except (OSError, ValueError):
        return
    existing = dict(table.schema.metadata or {})
    existing[FEATURE_PARQUET_SCHEMA_METADATA_KEY.encode()] = str(version).encode()
    new_schema = table.schema.with_metadata(existing)
    table = table.replace_schema_metadata(new_schema.metadata)
    pq.write_table(table, path)


def _serialize_record(rec: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in rec.items():
        if k in _DICT_FIELDS and isinstance(v, dict):
            out[k] = json.dumps(v, sort_keys=True)
        else:
            out[k] = v
    return out


def write_parquet_atomic(
    path: Path,
    frame: pl.DataFrame | list[dict[str, Any]],
    *,
    stamp_feature_schema: bool = True,
) -> None:
    """Write a Polars frame (or list of dicts) to Parquet, mkdir'ing parent dirs.

    Thin wrapper around ``pl.DataFrame.write_parquet`` that removes the
    ``path.parent.mkdir(parents=True, exist_ok=True)`` ceremony from callers
    (RF-DRY-004 / G1). Accepts an existing frame or a list of row dicts.

    When ``stamp_feature_schema`` is True (the default, Phase 15 Step 0.3) the
    current ``feature_parquet_schema_version`` is written into parquet
    key/value metadata so downstream readers can detect out-of-date files and
    demand a migration. The extra round-trip is cheap; opt out only for
    unit-level tests that deliberately need an unstamped parquet.
    """
    ensure_parent(path)
    df = frame if isinstance(frame, pl.DataFrame) else pl.DataFrame(frame)
    df.write_parquet(path)
    if stamp_feature_schema:
        # Import here to avoid a module-load circular with settings.
        from forensics.config import get_settings

        version = get_settings().features.feature_parquet_schema_version
        _stamp_parquet_schema_version(path, version)


def save_numpy_atomic(path: Path, array: np.ndarray) -> None:
    """``np.save`` with mkdir on the parent directory (RF-DRY-004 / G1)."""
    ensure_parent(path)
    np.save(path, array)


def save_numpy_compressed_atomic(path: Path, **arrays: np.ndarray) -> None:
    """``np.savez_compressed`` with mkdir on the parent directory (RF-DRY-004 / G1)."""
    ensure_parent(path)
    np.savez_compressed(path, **arrays)


def write_features(features: list[FeatureVector], output_path: Path) -> None:
    """Write feature vectors to Parquet (dict fields as JSON strings).

    Schema includes the ``section: pl.Utf8`` column derived from the article
    URL via :func:`forensics.utils.url.section_from_url` (Phase 15 Step J1);
    legacy parquets without this column are upgraded by
    ``forensics features migrate``.

    ``write_parquet_atomic`` stamps the current
    ``feature_parquet_schema_version`` into parquet key/value metadata
    automatically (Phase 15 Step 0.3). N-04 stamps ``ai_marker_list_version``
    alongside without forcing a parquet schema migration.
    """
    from forensics.features.lexical import AI_MARKER_LIST_VERSION

    rows = [_serialize_record(f.to_flat_dict()) for f in features]
    write_parquet_atomic(output_path, rows)
    merge_parquet_metadata(
        output_path,
        {"forensics.ai_marker_list_version": AI_MARKER_LIST_VERSION},
    )


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

    .. deprecated:: 0.2
        Use :func:`scan_features` and call :meth:`~polars.LazyFrame.collect` at
        the boundary where a ``DataFrame`` is required (RF-DEAD-004).
    """
    warnings.warn(
        "read_features() is deprecated; use scan_features(path).collect()",
        DeprecationWarning,
        stacklevel=2,
    )
    return scan_features(path).collect()


def load_feature_frame_sorted(features_path: Path) -> pl.LazyFrame:
    """Return a ``LazyFrame`` for the feature Parquet, sorted by ``timestamp``.

    Returning a ``LazyFrame`` lets downstream callers push ``filter(...)``
    predicates (e.g. per-author slicing) into the scan before materialization
    (P2-PERF-002). Call ``.collect()`` at the boundary where a ``DataFrame`` is
    required. For the small number of eager callers, use
    :func:`load_feature_frame_sorted_eager`.

    Raises :class:`SchemaMigrationRequired` when the parquet's stamped
    ``forensics.schema_version`` is absent or below
    ``settings.features.feature_parquet_schema_version`` (Phase 15 Step 0.3).
    """
    # Import here so this module is safe to import before config is wired.
    from forensics.config import get_settings

    required = get_settings().features.feature_parquet_schema_version
    found = _read_parquet_schema_version(features_path)
    if found is None or found < required:
        raise SchemaMigrationRequired(features_path, found, required)
    lf = scan_features(features_path)
    schema_names = lf.collect_schema().names()
    if "timestamp" not in schema_names:
        msg = f"features parquet missing timestamp: {features_path}"
        raise ValueError(msg)
    # C-01 — tie-break equal timestamps so changepoint / hypothesis ordering is stable.
    if "article_id" in schema_names:
        return lf.sort(["timestamp", "article_id"])
    return lf.sort("timestamp")


def load_feature_frame_sorted_eager(features_path: Path) -> pl.DataFrame:
    """Eager convenience wrapper around :func:`load_feature_frame_sorted`."""
    return load_feature_frame_sorted(features_path).collect()


def write_embeddings_manifest(records: list[EmbeddingRecord], path: Path) -> None:
    """Atomically rewrite the embedding manifest JSONL."""
    ensure_parent(path)
    lines = [json.dumps(r.model_dump(mode="json"), sort_keys=True) for r in records]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    tmp.replace(path)


def read_embeddings_manifest(path: Path) -> list[EmbeddingRecord]:
    """D-05 — last row wins per ``article_id`` when the manifest contains duplicates."""
    if not path.is_file():
        return []
    by_id: dict[str, EmbeddingRecord] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = EmbeddingRecord.model_validate_json(line)
        by_id[rec.article_id] = rec
    return list(by_id.values())


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
    ensure_parent(path)
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
