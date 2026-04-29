"""Shared per-author worker pipeline used by parallel dispatch and isolated refresh."""

from __future__ import annotations

import logging
import os
from typing import Literal

from forensics.analysis.convergence import ProbabilityTrajectory
from forensics.analysis.orchestrator.mode import AnalysisMode
from forensics.analysis.orchestrator.per_author import (
    _run_per_author_analysis,
    _write_per_author_json_artifacts,
)
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import AnalysisResult
from forensics.models.features import STRICT_DECODE_CTX
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.repository import Repository

logger = logging.getLogger(__name__)


def _resolve_max_workers(config: ForensicsSettings, override: int | None) -> int:
    if override is not None:
        return max(1, int(override))
    cfg = config.analysis.max_workers
    if cfg is not None:
        return max(1, int(cfg))
    cpu = os.cpu_count() or 1
    return max(1, cpu - 1)


_REQUIRED_AUTHOR_ARTIFACT_SUFFIXES = (
    "_result.json",
    "_changepoints.json",
    "_convergence.json",
    "_hypothesis_tests.json",
)


def _run_repo_per_author_pipeline_with_artifacts(
    slug: str,
    repo: Repository,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    prob_map: dict[str, ProbabilityTrajectory],
    mode: AnalysisMode,
    stage_timings: dict[str, float],
    *,
    job_kind: Literal["analysis", "analysis-refresh"],
    emit_success_log: bool,
) -> AnalysisResult | None:
    per_author = _run_per_author_analysis(
        slug,
        repo,
        paths,
        config,
        probability_trajectory_by_slug=prob_map,
        stage_timings=stage_timings,
        mode=mode,
    )
    assert not STRICT_DECODE_CTX.get(), (
        f"STRICT_DECODE_CTX must be reset after _run_per_author_analysis ({job_kind} slug={slug!r})"
    )
    if per_author is None:
        logger.info("%s: slug=%s skipped (missing author or features)", job_kind, slug)
        return None
    assembled, change_points, convergence_windows, all_tests = per_author
    _write_per_author_json_artifacts(
        slug,
        paths,
        change_points,
        convergence_windows,
        assembled,
        all_tests,
    )
    if emit_success_log:
        logger.info(
            "%s: slug=%s change_points=%d windows=%d tests=%d",
            job_kind,
            slug,
            len(change_points),
            len(convergence_windows),
            len(all_tests),
        )
    return assembled


__all__ = [
    "_REQUIRED_AUTHOR_ARTIFACT_SUFFIXES",
    "_resolve_max_workers",
    "_run_repo_per_author_pipeline_with_artifacts",
]
