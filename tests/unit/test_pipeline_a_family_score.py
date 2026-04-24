"""Phase 15 B2 regression pin: family-grouped Pipeline A scoring.

Pins ``pipeline_a_score``, ``convergence_ratio``, and the sorted
``features_converging`` list to exact reference values for a hand-built CP
fixture. Any future change to the family registry, the per-family
representative rule, or the score aggregation must update these constants
deliberately — a silent drift fails this test loudly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from forensics.analysis.convergence import (
    FAMILY_COUNT,
    ConvergenceInput,
    compute_convergence_scores,
)
from forensics.models.analysis import ChangePoint


def _cp(
    feature_name: str,
    timestamp: datetime,
    confidence: float,
    effect_size: float,
) -> ChangePoint:
    return ChangePoint(
        feature_name=feature_name,
        author_id="regression-author",
        timestamp=timestamp,
        confidence=confidence,
        method="pelt",
        effect_size_cohens_d=effect_size,
        direction="increase",
    )


def test_pipeline_a_family_score_regression_pin() -> None:
    """Exact pin: hand-tuned CP list → reference score, ratio, and feature list."""
    base = datetime(2024, 6, 1, tzinfo=UTC)
    # Four families represented — lexical_richness (2 CPs, max = 0.72),
    # readability (1 CP, 0.40), sentence_structure (2 CPs, max = 0.42),
    # ai_markers (1 CP, 0.30). Expected: ratio 4/8, score mean(0.72,0.40,0.42,0.30).
    fixture_cps = [
        _cp("ttr", base, 0.9, 0.8),  # lexical_richness 0.72
        _cp("hapax_ratio", base + timedelta(days=1), 0.4, 0.3),  # lexical_richness 0.12
        _cp("flesch_kincaid", base + timedelta(days=2), 0.8, 0.5),  # readability 0.40
        _cp("sent_length_mean", base + timedelta(days=3), 0.7, 0.6),  # sentence_structure 0.42
        _cp("conjunction_freq", base + timedelta(days=4), 0.5, 0.5),  # sentence_structure 0.25
        _cp("ai_marker_frequency", base + timedelta(days=5), 0.6, 0.5),  # ai_markers 0.30
    ]

    result = compute_convergence_scores(
        ConvergenceInput.build(
            change_points=fixture_cps,
            centroid_velocities=[],
            baseline_similarity_curve=[],
            window_days=30,
            min_feature_ratio=4 / FAMILY_COUNT - 0.01,  # allow the 4/8 ratio to pass
            total_feature_count=len(fixture_cps),
        )
    )

    assert result, "regression fixture should emit exactly one convergence window"
    window = result[0]

    # --- REGRESSION CONSTANTS (pinned; change deliberately) ---
    expected_ratio = 4 / FAMILY_COUNT  # 0.5
    expected_score = (0.72 + 0.40 + 0.42 + 0.30) / 4.0  # 0.46
    expected_features = sorted(
        [
            "ttr",  # lexical_richness representative
            "flesch_kincaid",  # readability representative
            "sent_length_mean",  # sentence_structure representative
            "ai_marker_frequency",  # ai_markers representative
        ]
    )
    # ----------------------------------------------------------

    assert window.convergence_ratio == pytest.approx(expected_ratio)
    assert window.pipeline_a_score == pytest.approx(expected_score)
    assert sorted(window.features_converging) == expected_features
