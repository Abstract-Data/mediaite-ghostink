"""Legacy flat ``[analysis]`` TOML ↔ nested :class:`AnalysisConfig` bridge.

Keeps flat-key routing, bucket lifting, and ``_FLAT_TO_GROUP`` in one place so
``analysis_settings`` stays focused on Pydantic models. Changing grouping here
affects ``model_validator`` lift and :func:`apply_flat_analysis_overrides` in
``analysis_settings``; provenance hashing stays governed by ADR-016 / ADR-017.
"""

from __future__ import annotations

from typing import Any

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
