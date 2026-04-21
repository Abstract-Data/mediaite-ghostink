"""Feature vectors and embedding references."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class FeatureVector(BaseModel):
    """Per-article computed linguistic and productivity features."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    article_id: str
    author_id: str
    timestamp: datetime
    ttr: float = 0.0
    mattr: float = 0.0
    hapax_ratio: float = 0.0
    yules_k: float = 0.0
    simpsons_d: float = 0.0
    ai_marker_frequency: float = 0.0
    function_word_distribution: dict[str, float] = Field(default_factory=dict)
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
    flesch_kincaid: float = 0.0
    coleman_liau: float = 0.0
    gunning_fog: float = 0.0
    smog: float = 0.0
    bigram_entropy: float = 0.0
    trigram_entropy: float = 0.0
    self_similarity_30d: float = 0.0
    self_similarity_90d: float = 0.0
    topic_diversity_score: float = 0.0
    formula_opening_score: float = 0.0
    formula_closing_score: float = 0.0
    first_person_ratio: float = 0.0
    hedging_frequency: float = 0.0
    days_since_last_article: float = 0.0
    rolling_7d_count: int = 0
    rolling_30d_count: int = 0


class EmbeddingRecord(BaseModel):
    """Pointer to persisted embedding vectors for an article."""

    article_id: str
    author_id: str
    timestamp: datetime
    model_name: str
    embedding_path: str
    embedding_dim: int
