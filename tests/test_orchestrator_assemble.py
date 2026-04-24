"""Light tests for :func:`forensics.analysis.orchestrator.assemble_analysis_result`."""

from __future__ import annotations

from datetime import UTC, datetime

from forensics.analysis.orchestrator import assemble_analysis_result
from forensics.config.settings import AnalysisConfig
from forensics.models.analysis import ChangePoint, DriftScores
from forensics.utils.provenance import compute_model_config_hash


def test_assemble_analysis_result_config_hash_matches_model_digest() -> None:
    cfg = AnalysisConfig()
    cp = ChangePoint(
        feature_name="lexical_ttr",
        author_id="author-1",
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        confidence=0.9,
        method="pelt",
        effect_size_cohens_d=0.4,
        direction="increase",
    )
    drift = DriftScores(
        author_id="author-1",
        baseline_centroid_similarity=0.5,
        ai_baseline_similarity=None,
        monthly_centroid_velocities=[0.1, 0.2],
        intra_period_variance_trend=[0.0, 0.01],
    )
    res = assemble_analysis_result(
        "author-1",
        [cp],
        [],
        drift,
        [],
        cfg,
    )
    assert res.author_id == "author-1"
    expected = compute_model_config_hash(cfg, length=16, round_trip=True)
    assert res.config_hash == expected
