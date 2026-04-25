"""Pydantic models for authors, articles, features, analysis, and reports.

Barrel of primary domain types; ``__all__`` matches the public model surface.
Import less common types from their defining modules when not listed.
"""

from forensics.models.analysis import (
    AnalysisResult,
    ChangePoint,
    ConvergenceWindow,
    DriftScores,
    EraClassification,
    HypothesisTest,
)
from forensics.models.article import Article
from forensics.models.author import Author, AuthorManifest
from forensics.models.features import EmbeddingRecord, FeatureVector
from forensics.models.report import FindingStrength, ReportManifest

__all__ = [
    "AnalysisResult",
    "Article",
    "Author",
    "AuthorManifest",
    "ChangePoint",
    "ConvergenceWindow",
    "DriftScores",
    "EmbeddingRecord",
    "EraClassification",
    "FeatureVector",
    "FindingStrength",
    "HypothesisTest",
    "ReportManifest",
]
