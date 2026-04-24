"""Feature vectors and embedding references."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class LexicalFeatures(BaseModel):
    """Lexical / token distribution statistics."""

    ttr: float = 0.0
    mattr: float = 0.0
    hapax_ratio: float = 0.0
    yules_k: float = 0.0
    simpsons_d: float = 0.0
    ai_marker_frequency: float = 0.0
    function_word_distribution: dict[str, float] = Field(default_factory=dict)


class StructuralFeatures(BaseModel):
    """Sentence and paragraph shape statistics."""

    sent_length_mean: float = 0.0
    sent_length_median: float = 0.0
    sent_length_std: float = 0.0
    sent_length_skewness: float = 0.0
    subordinate_clause_depth: float = 0.0
    conjunction_freq: float = 0.0
    passive_voice_ratio: float = 0.0
    sentences_per_paragraph: float = 0.0
    paragraph_length_variance: float = 0.0
    punctuation_profile: dict[str, float] = Field(default_factory=dict)


class ReadabilityFeatures(BaseModel):
    """Readability indices."""

    flesch_kincaid: float = 0.0
    coleman_liau: float = 0.0
    gunning_fog: float = 0.0
    smog: float = 0.0


class ContentFeatures(BaseModel):
    """Entropy and self-similarity style signals.

    ``self_similarity_30d`` / ``self_similarity_90d`` are ``None`` for
    early-career articles whose peer window is smaller than the minimum
    threshold enforced in :mod:`forensics.features.content`.
    """

    bigram_entropy: float = 0.0
    trigram_entropy: float = 0.0
    self_similarity_30d: float | None = None
    self_similarity_90d: float | None = None
    topic_diversity_score: float = 0.0
    formula_opening_score: float = 0.0
    formula_closing_score: float = 0.0


class ProductivityFeatures(BaseModel):
    """Publication cadence and voice signals."""

    first_person_ratio: float = 0.0
    hedging_frequency: float = 0.0
    days_since_last_article: float = 0.0
    rolling_7d_count: int = 0
    rolling_30d_count: int = 0


class PosShapeFeatures(BaseModel):
    """POS n-grams and dependency depth (spaCy-derived)."""

    pos_bigram_top30: dict[str, float] = Field(default_factory=dict)
    clause_initial_entropy: float = 0.0
    clause_initial_top10: dict[str, float] = Field(default_factory=dict)
    dep_depth_mean: float = 0.0
    dep_depth_std: float = 0.0
    dep_depth_max: float = 0.0


def _nested_keys() -> frozenset[str]:
    return frozenset(
        {
            "lexical",
            "structural",
            "readability",
            "content",
            "productivity",
            "pos",
        }
    )


_FLAT_DICT_FIELDS: frozenset[str] = frozenset(
    {
        "function_word_distribution",
        "punctuation_profile",
        "pos_bigram_top30",
        "clause_initial_top10",
    }
)


_FAMILIES: tuple[tuple[type[BaseModel], str], ...] = (
    (LexicalFeatures, "lexical"),
    (StructuralFeatures, "structural"),
    (ReadabilityFeatures, "readability"),
    (ContentFeatures, "content"),
    (ProductivityFeatures, "productivity"),
    (PosShapeFeatures, "pos"),
)


def _is_scalar_annotation(annotation: Any) -> bool:
    """True when ``annotation`` is ``float``/``int`` (optionally ``| None``)."""
    import types
    from typing import Union, get_args, get_origin

    if annotation is float or annotation is int:
        return True
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        members = [a for a in get_args(annotation) if a is not type(None)]
        return all(m is float or m is int for m in members)
    return False


def count_scalar_features() -> int:
    """Total number of scalar feature columns across every feature family.

    ``_TOTAL_SCALAR_FEATURES`` in the survey scoring module is derived from
    this (P3-MAINT-001): adding or removing a ``float``/``int`` field on any
    of the ``_FAMILIES`` models bumps the count automatically. Dict- and
    list-typed fields are intentionally excluded because they do not
    participate in the per-feature PELT sweep.
    """
    total = 0
    for family_cls, _key in _FAMILIES:
        for field_info in family_cls.model_fields.values():
            if _is_scalar_annotation(field_info.annotation):
                total += 1
    return total


def _maybe_decode_dict_field(value: Any) -> Any:
    """Round-trip compat: Parquet stores dict fields as JSON strings; decode on read."""
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return value


class FeatureVector(BaseModel):
    """Per-article computed linguistic and productivity features (nested by family).

    The ``section`` column (Phase 15 Step J1) is the URL-derived first path
    segment for the article (e.g. ``"politics"``, ``"opinion"``, ``"sponsored"``).
    Default is ``"unknown"`` so legacy callers and tests that build
    ``FeatureVector`` without supplying the URL still validate; populated
    callers go through :func:`forensics.utils.url.section_from_url`.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    article_id: str
    author_id: str
    timestamp: datetime
    section: str = "unknown"
    lexical: LexicalFeatures = Field(default_factory=LexicalFeatures)
    structural: StructuralFeatures = Field(default_factory=StructuralFeatures)
    readability: ReadabilityFeatures = Field(default_factory=ReadabilityFeatures)
    content: ContentFeatures = Field(default_factory=ContentFeatures)
    productivity: ProductivityFeatures = Field(default_factory=ProductivityFeatures)
    pos: PosShapeFeatures = Field(default_factory=PosShapeFeatures)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_flat_payload(cls, data: Any) -> Any:
        """Allow construction from legacy flat dicts / kwargs (Parquet row, tests)."""
        if not isinstance(data, dict):
            return data
        if any(k in data for k in _nested_keys()):
            return data
        flat = dict(data)
        for dict_field in _FLAT_DICT_FIELDS:
            if dict_field in flat:
                flat[dict_field] = _maybe_decode_dict_field(flat[dict_field])
        out: dict[str, Any] = {}
        buckets: dict[str, dict[str, Any]] = {
            key: {f: flat.pop(f) for f in family_cls.model_fields if f in flat}
            for family_cls, key in _FAMILIES
        }
        out.update(flat)
        for key, bucket in buckets.items():
            if bucket:
                out[key] = bucket
        return out

    def to_flat_dict(self) -> dict[str, Any]:
        """Serialize to one dict matching legacy Parquet column names (JSON-friendly)."""
        return {
            "id": self.id,
            "article_id": self.article_id,
            "author_id": self.author_id,
            "timestamp": self.timestamp.isoformat(),
            "section": self.section,
            **self.lexical.model_dump(mode="json"),
            **self.structural.model_dump(mode="json"),
            **self.readability.model_dump(mode="json"),
            **self.content.model_dump(mode="json"),
            **self.productivity.model_dump(mode="json"),
            **self.pos.model_dump(mode="json"),
        }


class EmbeddingRecord(BaseModel):
    """Pointer to persisted embedding vectors for an article."""

    article_id: str
    author_id: str
    timestamp: datetime
    model_name: str
    model_version: str
    embedding_path: str
    embedding_dim: int
