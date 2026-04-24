"""Phase 15 Step 0.4 — analysis config-hash enumeration guard.

Each field decorated with ``json_schema_extra={"include_in_config_hash": True}``
MUST contribute to the hash; any field without the annotation must NOT change
the hash when flipped. This test enforces both directions so accidental
inclusion / exclusion fails fast.
"""

from __future__ import annotations

from typing import Any

import pytest

from forensics.config.settings import AnalysisConfig, FeaturesConfig
from forensics.utils.provenance import (
    _collect_hash_enumerated_fields,
    compute_model_config_hash,
)

# Fields that MUST invalidate the cache when they change (authoritative list —
# mirror of the ``json_schema_extra`` annotations in ``settings.py``).
_EXPECTED_HASH_FIELDS_ANALYSIS: set[str] = {
    "pelt_cost_model",
    "bocpd_detection_mode",
    "bocpd_map_drop_ratio",
    "bocpd_min_run_length",
    "bocpd_student_t",
    "convergence_min_feature_ratio",
    "convergence_cp_source",
    "fdr_grouping",
    "enable_ks_test",
    "pipeline_b_mode",
    "section_residualize_features",
    "changepoint_methods",
    "bootstrap_iterations",
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
}

# Alternate values used when flipping each field.
_FLIP_VALUES: dict[str, Any] = {
    "pelt_cost_model": "rbf",
    "bocpd_detection_mode": "p_r0_legacy",
    "bocpd_map_drop_ratio": 0.75,
    "bocpd_min_run_length": 9,
    "bocpd_student_t": False,
    "convergence_min_feature_ratio": 0.8,
    "convergence_cp_source": "raw",
    "fdr_grouping": "author",
    "enable_ks_test": True,
    "pipeline_b_mode": "percentile",
    "section_residualize_features": True,
    "changepoint_methods": ["pelt"],
    "bootstrap_iterations": 2500,
    "significance_threshold": 0.01,
    "effect_size_threshold": 0.25,
    "multiple_comparison_method": "bonferroni",
    "max_workers": 4,
    "feature_workers": 3,
    "section_min_articles": 200,
    "min_articles_per_section_for_residualize": 25,
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
