"""Parquet persistence for feature tables (Phase 4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def read_features(path: Path) -> pl.DataFrame:
    """Load a feature Parquet table."""
    return pl.read_parquet(path)


def load_feature_frame_sorted(features_path: Path) -> pl.DataFrame:
    """Load features Parquet, require ``timestamp``, return rows sorted by time.

    Uses a ``LazyFrame`` scan so the planner can push the sort down and defer the
    materialization — callers that filter/slice downstream get the benefit.
    """
    lf = pl.scan_parquet(features_path)
    if "timestamp" not in lf.collect_schema().names():
        msg = f"features parquet missing timestamp: {features_path}"
        raise ValueError(msg)
    return lf.sort("timestamp").collect()


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
