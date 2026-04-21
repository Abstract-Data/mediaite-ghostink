"""AI baseline corpus generation and chain-of-custody helpers (Phase 10)."""

from forensics.baseline.agent import (
    BaselineDeps,
    GeneratedArticle,
    generate_baseline_article,
    make_baseline_agent,
    run_generation_matrix,
)
from forensics.baseline.custody import (
    audit_scrape_timestamps,
    verify_raw_archive_integrity,
)
from forensics.baseline.features import extract_baseline_features
from forensics.baseline.generation import BASELINE_MODELS, BaselineGenerationConfig
from forensics.baseline.ollama_client import fetch_model_digests, preflight_check
from forensics.baseline.readme import generate_baseline_readme
from forensics.baseline.topics import get_topic_distribution
from forensics.baseline.word_sampling import sample_word_counts

__all__ = [
    "BASELINE_MODELS",
    "BaselineDeps",
    "BaselineGenerationConfig",
    "GeneratedArticle",
    "audit_scrape_timestamps",
    "extract_baseline_features",
    "fetch_model_digests",
    "generate_baseline_article",
    "generate_baseline_readme",
    "get_topic_distribution",
    "make_baseline_agent",
    "preflight_check",
    "run_generation_matrix",
    "sample_word_counts",
    "verify_raw_archive_integrity",
]
