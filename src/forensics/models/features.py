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
    """Per-article computed linguistic and productivity features (nested by family)."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    article_id: str
    author_id: str
    timestamp: datetime
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
        lex_f = {f: flat.pop(f) for f in LexicalFeatures.model_fields if f in flat}
        str_f = {f: flat.pop(f) for f in StructuralFeatures.model_fields if f in flat}
        read_f = {f: flat.pop(f) for f in ReadabilityFeatures.model_fields if f in flat}
        cont_f = {f: flat.pop(f) for f in ContentFeatures.model_fields if f in flat}
        prod_f = {f: flat.pop(f) for f in ProductivityFeatures.model_fields if f in flat}
        pos_f = {f: flat.pop(f) for f in PosShapeFeatures.model_fields if f in flat}
        out.update(flat)
        if lex_f:
            out["lexical"] = lex_f
        if str_f:
            out["structural"] = str_f
        if read_f:
            out["readability"] = read_f
        if cont_f:
            out["content"] = cont_f
        if prod_f:
            out["productivity"] = prod_f
        if pos_f:
            out["pos"] = pos_f
        return out

    def to_flat_dict(self) -> dict[str, Any]:
        """Serialize to one dict matching legacy Parquet column names (JSON-friendly)."""
        return {
            "id": self.id,
            "article_id": self.article_id,
            "author_id": self.author_id,
            "timestamp": self.timestamp.isoformat(),
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
