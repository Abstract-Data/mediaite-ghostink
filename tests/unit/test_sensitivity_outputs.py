"""Section-residualized sensitivity artifact tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from forensics.analysis.orchestrator import _run_section_residualized_sensitivity
from forensics.config.settings import AnalysisConfig, ForensicsSettings
from forensics.models.analysis import AnalysisResult, ChangePoint
from forensics.paths import AnalysisArtifactPaths


def _cp() -> ChangePoint:
    return ChangePoint(
        feature_name="ai_marker_frequency",
        author_id="author-1",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        confidence=0.95,
        method="pelt",
        effect_size_cohens_d=0.8,
        direction="increase",
    )


def test_section_residualized_sensitivity_writes_separate_summary(tmp_path, monkeypatch) -> None:
    paths = AnalysisArtifactPaths.from_layout(
        tmp_path,
        tmp_path / "articles.db",
        tmp_path / "features",
        tmp_path / "embeddings",
    )
    primary = AnalysisResult(
        author_id="author-1",
        run_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        config_hash="primary",
        change_points=[_cp()],
    )
    residualized = AnalysisResult(
        author_id="author-1",
        run_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        config_hash="residualized",
        change_points=[],
    )

    def fake_run_per_author_analysis(*_args: Any, **_kwargs: Any):
        return residualized, [], [], []

    monkeypatch.setattr(
        "forensics.analysis.orchestrator._run_per_author_analysis",
        fake_run_per_author_analysis,
    )

    summary = _run_section_residualized_sensitivity(
        paths,
        ForensicsSettings(authors=[], analysis=AnalysisConfig(section_residualize_features=False)),
        ["author-slug"],
        {"author-slug": primary},
        probability_trajectory_by_slug={},
    )

    summary_path = paths.sensitivity_dir("section_residualized") / "sensitivity_summary.json"
    assert summary_path.is_file()
    assert summary["authors"]["author-slug"]["primary_change_points"] == 1
    assert summary["authors"]["author-slug"]["section_residualized_change_points"] == 0
    assert summary["authors"]["author-slug"]["downgrade_recommended"] is True


def test_section_residualized_sensitivity_skips_when_primary_is_already_residualized(
    tmp_path,
) -> None:
    paths = AnalysisArtifactPaths.from_layout(
        tmp_path,
        tmp_path / "articles.db",
        tmp_path / "features",
        tmp_path / "embeddings",
    )

    summary = _run_section_residualized_sensitivity(
        paths,
        ForensicsSettings(authors=[], analysis=AnalysisConfig(section_residualize_features=True)),
        ["author-slug"],
        {},
        probability_trajectory_by_slug={},
    )

    assert summary == {}
