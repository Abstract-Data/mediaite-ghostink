"""Assemble ``FeatureVector`` from extractor dict outputs (DRY for baseline vs main pipeline)."""

from __future__ import annotations

import logging
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
from forensics.utils.url import section_from_url

logger = logging.getLogger(__name__)


def _derive_section(article: Article) -> str:
    """Derive ``section`` from ``article.url`` (Phase 15 Step J1).

    Logs a WARNING when the regex falls through to ``"unknown"`` so future
    URL-shape changes surface in routine pipeline runs (per the J1 spec).
    """
    url_str = str(article.url)
    section = section_from_url(url_str)
    if section == "unknown":
        logger.warning(
            "section_from_url returned 'unknown' for article %s (url=%r)",
            article.id,
            url_str,
        )
    return section


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
        section=_derive_section(article),
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
