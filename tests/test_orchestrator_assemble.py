"""Light tests for :func:`forensics.analysis.orchestrator.assemble_analysis_result`."""

from __future__ import annotations

from datetime import UTC, date, datetime

from forensics.analysis.orchestrator import assemble_analysis_result
from forensics.config.settings import AnalysisConfig, AuthorConfig, ForensicsSettings
from forensics.models.analysis import ChangePoint, DriftScores
from forensics.utils.provenance import compute_analysis_config_hash


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
    author = AuthorConfig(
        name="Fixture",
        slug="fixture-author",
        outlet="mediaite.com",
        role="control",
        archive_url="https://www.mediaite.com/author/fixture-author/",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2021, 1, 1),
    )
    settings = ForensicsSettings(authors=[author], analysis=cfg)
    res = assemble_analysis_result(
        "author-1",
        [cp],
        [],
        drift,
        [],
        settings,
    )
    assert res.author_id == "author-1"
    expected = compute_analysis_config_hash(settings)
    assert res.config_hash == expected
