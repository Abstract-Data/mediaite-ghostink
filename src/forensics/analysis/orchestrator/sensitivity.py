"""Sensitivity reruns for section residualization."""

from __future__ import annotations

from typing import Any

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.convergence import ProbabilityTrajectory
from forensics.analysis.orchestrator.per_author import (
    _run_per_author_analysis,
    _write_per_author_json_artifacts,
)
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import AnalysisResult
from forensics.storage.json_io import write_json_artifact
from forensics.storage.repository import Repository


def _section_residualized_settings(config: ForensicsSettings) -> ForensicsSettings:
    analysis = config.analysis.model_copy(update={"section_residualize_features": True})
    return config.model_copy(update={"analysis": analysis})


def _run_section_residualized_sensitivity(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    slugs: list[str],
    primary_results: dict[str, AnalysisResult],
    *,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory],
    exploratory: bool = False,
    allow_pre_phase16_embeddings: bool = False,
) -> dict[str, Any]:
    if config.analysis.section_residualize_features:
        return {}
    flagged = [
        slug
        for slug in slugs
        if slug in primary_results
        and (primary_results[slug].change_points or primary_results[slug].convergence_windows)
    ]
    if not flagged:
        return {}

    sensitivity_paths = paths.with_analysis_dir(paths.sensitivity_dir("section_residualized"))
    sensitivity_config = _section_residualized_settings(config)
    summary: dict[str, Any] = {"authors": {}, "analysis_dir": str(sensitivity_paths.analysis_dir)}
    with Repository(paths.db_path) as repo:
        for slug in flagged:
            per_author = _run_per_author_analysis(
                slug,
                repo,
                sensitivity_paths,
                sensitivity_config,
                probability_trajectory_by_slug=probability_trajectory_by_slug,
                exploratory=exploratory,
                allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
            )
            if per_author is None:
                continue
            assembled, change_points, convergence_windows, all_tests = per_author
            _write_per_author_json_artifacts(
                slug,
                sensitivity_paths,
                change_points,
                convergence_windows,
                assembled,
                all_tests,
            )
            primary_count = len(primary_results[slug].change_points)
            residualized_count = len(change_points)
            summary["authors"][slug] = {
                "primary_change_points": primary_count,
                "section_residualized_change_points": residualized_count,
                "primary_convergence_windows": len(primary_results[slug].convergence_windows),
                "section_residualized_convergence_windows": len(convergence_windows),
                "downgrade_recommended": residualized_count < primary_count,
            }

    write_json_artifact(sensitivity_paths.analysis_dir / "sensitivity_summary.json", summary)
    return summary
