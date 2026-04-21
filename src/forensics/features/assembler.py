"""Assemble ``FeatureVector`` from extractor dict outputs (DRY for baseline vs main pipeline)."""

from __future__ import annotations

from datetime import datetime

from forensics.models.article import Article
from forensics.models.features import (
    ContentFeatures,
    FeatureVector,
    LexicalFeatures,
    PosShapeFeatures,
    ProductivityFeatures,
    ReadabilityFeatures,
    StructuralFeatures,
)


def build_feature_vector_from_extractors(
    article: Article,
    *,
    lex: dict[str, object],
    struct: dict[str, object],
    cont: dict[str, object],
    prod: dict[str, object],
    read: dict[str, object],
    pos: dict[str, object],
    timestamp: datetime | None = None,
) -> FeatureVector:
    """Build a nested ``FeatureVector`` from per-family extractor dicts."""
    ts = timestamp if timestamp is not None else article.published_date
    return FeatureVector(
        article_id=article.id,
        author_id=article.author_id,
        timestamp=ts,
        lexical=LexicalFeatures.model_validate(lex),
        structural=StructuralFeatures.model_validate(struct),
        content=ContentFeatures.model_validate(cont),
        productivity=ProductivityFeatures.model_validate(prod),
        readability=ReadabilityFeatures.model_validate(read),
        pos=PosShapeFeatures(
            pos_bigram_top30=pos["pos_bigram_top30"],  # type: ignore[arg-type]
            clause_initial_entropy=float(pos["clause_initial_entropy"]),
            clause_initial_top10=pos["clause_initial_top10"],  # type: ignore[arg-type]
            dep_depth_mean=float(pos["dep_depth_mean"]),
            dep_depth_std=float(pos["dep_depth_std"]),
            dep_depth_max=float(pos["dep_depth_max"]),
        ),
    )
