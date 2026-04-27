"""Guard: ``include_in_config_hash`` fields match the analysis config hash enumerator."""

from __future__ import annotations

from typing import Any

import pytest

from forensics.config.settings import AnalysisConfig, FeaturesConfig, ForensicsSettings
from forensics.utils.provenance import (
    _collect_hash_enumerated_fields,
    compute_analysis_config_hash,
    compute_config_hash,
    compute_model_config_hash,
)

# Mirror ``json_schema_extra`` on ``AnalysisConfig`` (must match provenance enumerator).
_EXPECTED_HASH_FIELDS_ANALYSIS: set[str] = {
    "pelt_penalty",
    "pelt_cost_model",
    "bocpd_detection_mode",
    "bocpd_map_drop_ratio",
    "bocpd_min_run_length",
    "bocpd_hazard_rate",
    "bocpd_hazard_auto",
    "bocpd_expected_changes_per_author",
    "bocpd_student_t",
    "convergence_min_feature_ratio",
    "convergence_cp_source",
    "convergence_drift_only_pb_threshold",
    "convergence_window_days",
    "convergence_window_adaptive",
    "convergence_window_days_min",
    "convergence_window_days_max",
    "fdr_grouping",
    "enable_cross_author_correction",
    "hypothesis_min_segment_n",
    "enable_ks_test",
    "pipeline_b_mode",
    "section_residualize_features",
    "changepoint_methods",
    "bootstrap_iterations",
    "min_articles_for_period",
    "embedding_model_revision",
    "embedding_vector_dim",
    "content_lda_random_state",
    "drift_umap_random_state",
    "hypothesis_bootstrap_seed",
    "significance_threshold",
    "effect_size_threshold",
    "multiple_comparison_method",
}

# Fields on ``AnalysisConfig`` that must NOT alter the hash when flipped.
_EXPECTED_NON_HASH_FIELDS_ANALYSIS: set[str] = {
    "max_workers",
    "feature_workers",
    "section_min_articles",
    "min_articles_per_section_for_residualize",
    "baseline_embedding_count_sensitivity",
    "analysis_min_word_count",
}

# Alternate values used when flipping each field.
_FLIP_VALUES: dict[str, Any] = {
    "pelt_penalty": 6.0,
    "pelt_cost_model": "rbf",
    "bocpd_detection_mode": "p_r0_legacy",
    "bocpd_map_drop_ratio": 0.75,
    "bocpd_hazard_rate": 0.01,
    "bocpd_hazard_auto": True,
    "bocpd_expected_changes_per_author": 5,
    "bocpd_min_run_length": 9,
    "bocpd_student_t": False,
    "convergence_min_feature_ratio": 0.8,
    "convergence_cp_source": "raw",
    "convergence_drift_only_pb_threshold": 0.7,
    "convergence_window_days": 120,
    "convergence_window_adaptive": True,
    "convergence_window_days_min": 45,
    "convergence_window_days_max": 200,
    "fdr_grouping": "author",
    "enable_cross_author_correction": True,
    "hypothesis_min_segment_n": 12,
    "enable_ks_test": True,
    "pipeline_b_mode": "percentile",
    "section_residualize_features": True,
    "changepoint_methods": ["pelt"],
    "min_articles_for_period": 12,
    "embedding_model_revision": "0000000000000000000000000000000000000000",
    "embedding_vector_dim": 512,
    "content_lda_random_state": 7,
    "drift_umap_random_state": 11,
    "hypothesis_bootstrap_seed": 99,
    "bootstrap_iterations": 2500,
    "significance_threshold": 0.01,
    "effect_size_threshold": 0.25,
    "multiple_comparison_method": "bonferroni",
    "max_workers": 4,
    "feature_workers": 3,
    "section_min_articles": 200,
    "min_articles_per_section_for_residualize": 25,
    "baseline_embedding_count_sensitivity": [15, 25],
    "analysis_min_word_count": 100,
}


def test_enumerated_fields_match_expected() -> None:
    enumerated = _collect_hash_enumerated_fields(AnalysisConfig())
    assert enumerated is not None
    assert enumerated == _EXPECTED_HASH_FIELDS_ANALYSIS


@pytest.mark.parametrize("field", sorted(_EXPECTED_HASH_FIELDS_ANALYSIS))
def test_flipping_hash_field_changes_hash(field: str) -> None:
    base = AnalysisConfig()
    base_hash = compute_model_config_hash(base)
    flipped = base.model_copy(update={field: _FLIP_VALUES[field]})
    assert compute_model_config_hash(flipped) != base_hash, (
        f"flipping {field!r} must change the analysis config hash"
    )


@pytest.mark.parametrize("field", sorted(_EXPECTED_NON_HASH_FIELDS_ANALYSIS))
def test_flipping_non_hash_field_does_not_change_hash(field: str) -> None:
    base = AnalysisConfig()
    base_hash = compute_model_config_hash(base)
    flipped = base.model_copy(update={field: _FLIP_VALUES[field]})
    assert compute_model_config_hash(flipped) == base_hash, (
        f"flipping {field!r} must NOT change the analysis config hash"
    )


def test_features_config_hash_enumeration() -> None:
    """``FeaturesConfig.feature_parquet_schema_version`` participates in its own hash."""
    base = FeaturesConfig()
    base_hash = compute_model_config_hash(base)
    flipped = base.model_copy(update={"feature_parquet_schema_version": 3})
    assert compute_model_config_hash(flipped) != base_hash


def test_compute_analysis_config_hash_matches_nested_model_dump() -> None:
    """T-04 — ``compute_analysis_config_hash`` stays aligned with the analysis model hash."""
    settings = ForensicsSettings()
    assert compute_analysis_config_hash(settings) == compute_model_config_hash(
        settings.analysis,
        length=16,
        round_trip=True,
    )


def test_pipeline_config_hash_invalidates_when_scraping_hash_field_changes() -> None:
    """T-04 — full-settings fingerprint must move when a scraping hash knob flips."""
    settings = ForensicsSettings()
    base = compute_config_hash(settings)
    other_threshold = 1 if settings.scraping.simhash_threshold != 1 else 2
    flipped = settings.model_copy(
        update={
            "scraping": settings.scraping.model_copy(update={"simhash_threshold": other_threshold})
        }
    )
    assert flipped.scraping.simhash_threshold == other_threshold
    assert compute_config_hash(flipped) != base
