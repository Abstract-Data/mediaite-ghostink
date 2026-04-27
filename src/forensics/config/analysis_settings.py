"""Nested analysis configuration (flat ``[analysis]`` TOML compatible).

``AnalysisConfig`` composes sub-models for maintainability. A
``model_validator(mode="before")`` lifts legacy flat keys so existing
``config.toml`` files load unchanged. Preregistration and
``compute_model_config_hash(settings.analysis)`` preserve the pre-nested JSON
shape (flat keys, sorted) via :mod:`forensics.utils.provenance`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ChangepointMethod = Literal["pelt", "bocpd", "chow", "cusum"]

# --- Sub-models (hash annotations live on the same field names as legacy flat layout) ---


class PeltConfig(BaseModel):
    """PELT and shared changepoint-method selection."""

    changepoint_methods: list[ChangepointMethod] = Field(
        default_factory=lambda: ["pelt", "bocpd"],
        json_schema_extra={"include_in_config_hash": True},
    )
    min_articles_for_period: int = Field(
        5,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    pelt_penalty: float = Field(
        5.0,
        gt=0.0,
        json_schema_extra={"include_in_config_hash": True},
    )
    pelt_cost_model: Literal["l2", "l1", "rbf"] = Field(
        "l1",
        json_schema_extra={"include_in_config_hash": True},
    )


class BocpdConfig(BaseModel):
    """BOCPD detection and MAP-reset stream post-processing."""

    bocpd_hazard_rate: float = Field(
        1 / 250.0,
        gt=0.0,
        le=1.0,
        json_schema_extra={"include_in_config_hash": True},
    )
    bocpd_hazard_auto: bool = Field(False, json_schema_extra={"include_in_config_hash": True})
    bocpd_expected_changes_per_author: int = Field(
        3,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    bocpd_detection_mode: Literal["p_r0_legacy", "map_reset"] = Field(
        "map_reset",
        json_schema_extra={"include_in_config_hash": True},
    )
    bocpd_map_drop_ratio: float = Field(
        0.5,
        gt=0.0,
        le=1.0,
        json_schema_extra={"include_in_config_hash": True},
    )
    bocpd_min_run_length: int = Field(5, ge=1, json_schema_extra={"include_in_config_hash": True})
    bocpd_reset_cooldown: int = Field(3, ge=0)
    bocpd_merge_window: int = Field(2, ge=0)
    bocpd_student_t: bool = Field(True, json_schema_extra={"include_in_config_hash": True})


class ConvergenceConfig(BaseModel):
    """Convergence window construction and gating."""

    convergence_window_days: int = Field(
        90,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    convergence_window_adaptive: bool = Field(
        False,
        json_schema_extra={"include_in_config_hash": True},
    )
    convergence_window_days_min: int = Field(
        30,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    convergence_window_days_max: int = Field(
        180,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    convergence_min_feature_ratio: float = Field(
        0.50,
        ge=0.0,
        le=1.0,
        json_schema_extra={"include_in_config_hash": True},
    )
    convergence_cp_source: Literal["raw", "section_adjusted"] = Field(
        "section_adjusted",
        json_schema_extra={"include_in_config_hash": True},
    )
    convergence_drift_only_pb_threshold: float = Field(
        0.3,
        ge=0.0,
        le=1.0,
        json_schema_extra={"include_in_config_hash": True},
    )
    convergence_perplexity_drop_ratio: float = 0.92
    convergence_burstiness_drop_ratio: float = 0.94
    convergence_use_permutation: bool = False
    convergence_permutation_iterations: int = Field(default=1000, ge=10, le=50_000)
    convergence_permutation_seed: int = 42


class ContentLdaConfig(BaseModel):
    """LDA and rolling content-LDA feature extraction."""

    lda_num_topics: int = 20
    lda_n_keywords: int = 10
    content_lda_n_components: int = 10
    content_lda_max_peer_documents: int = 48
    content_lda_max_iter: int = 15
    content_lda_max_features: int = 2000
    content_lda_max_df: float = 0.95
    content_lda_max_chars_per_document: int = 96_000
    content_lda_random_state: int = Field(42, json_schema_extra={"include_in_config_hash": True})


class HypothesisConfig(BaseModel):
    """Multiple testing, bootstrap, and evidence thresholds."""

    significance_threshold: float = Field(0.05, json_schema_extra={"include_in_config_hash": True})
    multiple_comparison_method: Literal["bonferroni", "benjamini_hochberg"] = Field(
        "benjamini_hochberg",
        json_schema_extra={"include_in_config_hash": True},
    )
    bootstrap_iterations: int = Field(
        1000,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    effect_size_threshold: float = Field(0.2, json_schema_extra={"include_in_config_hash": True})
    hypothesis_bootstrap_seed: int = Field(42, json_schema_extra={"include_in_config_hash": True})
    fdr_grouping: Literal["author", "family"] = Field(
        "family",
        json_schema_extra={"include_in_config_hash": True},
    )
    enable_cross_author_correction: bool = Field(
        False,
        json_schema_extra={"include_in_config_hash": True},
    )
    hypothesis_min_segment_n: int = Field(
        10,
        ge=2,
        json_schema_extra={"include_in_config_hash": True},
    )
    enable_ks_test: bool = Field(False, json_schema_extra={"include_in_config_hash": True})
    pipeline_b_mode: Literal["legacy", "percentile"] = Field(
        "percentile",
        json_schema_extra={"include_in_config_hash": True},
    )
    section_residualize_features: bool = Field(
        False,
        json_schema_extra={"include_in_config_hash": True},
    )


class EmbeddingStackConfig(BaseModel):
    """Embedding model pin, drift visualization, and extract-time limits."""

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_model_version: str = "v2.0"
    embedding_model_revision: str = Field(
        "main",
        json_schema_extra={"include_in_config_hash": True},
    )
    embedding_vector_dim: int = Field(384, ge=1, json_schema_extra={"include_in_config_hash": True})
    drift_umap_random_state: int = Field(42, json_schema_extra={"include_in_config_hash": True})
    baseline_embedding_count: int = 20
    baseline_embedding_count_sensitivity: list[int] = Field(default_factory=list)
    feature_extraction_max_failure_ratio: float = 0.25


# Flat TOML keys routed into each sub-model (single source for lift + test overrides).
_PELT_KEYS: frozenset[str] = frozenset(
    {"changepoint_methods", "min_articles_for_period", "pelt_penalty", "pelt_cost_model"},
)
_BOCPD_KEYS: frozenset[str] = frozenset(
    {
        "bocpd_hazard_rate",
        "bocpd_hazard_auto",
        "bocpd_expected_changes_per_author",
        "bocpd_detection_mode",
        "bocpd_map_drop_ratio",
        "bocpd_min_run_length",
        "bocpd_reset_cooldown",
        "bocpd_merge_window",
        "bocpd_student_t",
    },
)
_CONVERGENCE_KEYS: frozenset[str] = frozenset(
    {
        "convergence_window_days",
        "convergence_window_adaptive",
        "convergence_window_days_min",
        "convergence_window_days_max",
        "convergence_min_feature_ratio",
        "convergence_cp_source",
        "convergence_drift_only_pb_threshold",
        "convergence_perplexity_drop_ratio",
        "convergence_burstiness_drop_ratio",
        "convergence_use_permutation",
        "convergence_permutation_iterations",
        "convergence_permutation_seed",
    },
)
_CONTENT_LDA_KEYS: frozenset[str] = frozenset(
    {
        "lda_num_topics",
        "lda_n_keywords",
        "content_lda_n_components",
        "content_lda_max_peer_documents",
        "content_lda_max_iter",
        "content_lda_max_features",
        "content_lda_max_df",
        "content_lda_max_chars_per_document",
        "content_lda_random_state",
    },
)
_HYPOTHESIS_KEYS: frozenset[str] = frozenset(
    {
        "significance_threshold",
        "multiple_comparison_method",
        "bootstrap_iterations",
        "effect_size_threshold",
        "hypothesis_bootstrap_seed",
        "fdr_grouping",
        "enable_cross_author_correction",
        "hypothesis_min_segment_n",
        "enable_ks_test",
        "pipeline_b_mode",
        "section_residualize_features",
    },
)
_EMBEDDING_KEYS: frozenset[str] = frozenset(
    {
        "embedding_model",
        "embedding_model_version",
        "embedding_model_revision",
        "embedding_vector_dim",
        "drift_umap_random_state",
        "baseline_embedding_count",
        "baseline_embedding_count_sensitivity",
        "feature_extraction_max_failure_ratio",
    },
)

_GROUP_ATTRS: tuple[tuple[str, frozenset[str]], ...] = (
    ("pelt", _PELT_KEYS),
    ("bocpd", _BOCPD_KEYS),
    ("convergence", _CONVERGENCE_KEYS),
    ("content_lda", _CONTENT_LDA_KEYS),
    ("hypothesis", _HYPOTHESIS_KEYS),
    ("embedding", _EMBEDDING_KEYS),
)

_FLAT_TO_GROUP: dict[str, str] = {}
for _attr, keys in _GROUP_ATTRS:
    for _k in keys:
        _FLAT_TO_GROUP[_k] = _attr


def _lift_flat_analysis_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Move legacy flat ``[analysis]`` keys into nested sub-dicts for composition."""
    out = dict(data)
    for attr, keys in _GROUP_ATTRS:
        bucket: dict[str, Any] = {}
        existing = out.get(attr)
        if isinstance(existing, dict):
            bucket.update(existing)
        for k in keys:
            if k in out:
                bucket[k] = out.pop(k)
        if bucket:
            out[attr] = bucket
    return out


class AnalysisConfig(BaseModel):
    """Analysis-stage tunables (nested; flat TOML compatible)."""

    pelt: PeltConfig = Field(default_factory=PeltConfig)
    bocpd: BocpdConfig = Field(default_factory=BocpdConfig)
    convergence: ConvergenceConfig = Field(default_factory=ConvergenceConfig)
    content_lda: ContentLdaConfig = Field(default_factory=ContentLdaConfig)
    hypothesis: HypothesisConfig = Field(default_factory=HypothesisConfig)
    embedding: EmbeddingStackConfig = Field(default_factory=EmbeddingStackConfig)

    rolling_windows: list[int] = Field(default_factory=lambda: [30, 90])
    intra_variance_pairwise_max: int = 20
    ai_baseline_llm_temperature: float = 0.7
    analysis_min_word_count: int = Field(0, ge=0)
    section_min_articles: int = Field(50, ge=1)
    min_articles_per_section_for_residualize: int = Field(10, ge=1)
    max_workers: int | None = None
    feature_workers: int = 1

    @model_validator(mode="before")
    @classmethod
    def _lift_flat_toml(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        return _lift_flat_analysis_dict(data)


def apply_flat_analysis_overrides(analysis: AnalysisConfig, **kwargs: Any) -> AnalysisConfig:
    """Return a copy with legacy flat field names applied (tests and scripts).

    Unknown keys raise ``TypeError`` so typos fail loudly.
    """
    if not kwargs:
        return analysis
    buckets: dict[str, dict[str, Any]] = {attr: {} for attr, _ in _GROUP_ATTRS}
    top: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key in AnalysisConfig.model_fields and key not in _FLAT_TO_GROUP:
            top[key] = value
        elif key in _FLAT_TO_GROUP:
            buckets[_FLAT_TO_GROUP[key]][key] = value
        else:
            msg = f"Unknown analysis override field: {key!r}"
            raise TypeError(msg)
    update: dict[str, Any] = dict(top)
    for attr, _keys in _GROUP_ATTRS:
        b = buckets[attr]
        if not b:
            continue
        sub = getattr(analysis, attr)
        update[attr] = sub.model_copy(update=b)
    return analysis.model_copy(update=update)


__all__ = [
    "AnalysisConfig",
    "BocpdConfig",
    "ChangepointMethod",
    "ConvergenceConfig",
    "ContentLdaConfig",
    "EmbeddingStackConfig",
    "HypothesisConfig",
    "PeltConfig",
    "apply_flat_analysis_overrides",
]
