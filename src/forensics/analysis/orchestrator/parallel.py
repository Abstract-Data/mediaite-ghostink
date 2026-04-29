"""Parallel/isolated author execution for analysis orchestration.

Confirmatory analysis (``AnalysisMode.exploratory`` false) relies on
:data:`forensics.models.features.STRICT_DECODE_CTX` so nested feature JSON
decodes fail closed instead of coercing to ``{}``. That ContextVar defaults to
``False`` in each new process-pool worker; :func:`_run_per_author_analysis`
wraps its body in :func:`forensics.models.features.strict_feature_decode_confirmatory`
so strict mode is enabled only for the duration of that call. Do not invoke
feature decode paths from parallel workers outside this wrapper, or hashes and
downstream gates may diverge from the in-process CLI path.

Isolated refresh (``run_parallel_author_refresh``) lives in
:mod:`forensics.analysis.orchestrator.refresh` and is re-exported here for the
orchestrator monkeypatch contract.
"""

from __future__ import annotations

import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib import import_module
from pathlib import Path

from forensics.analysis.convergence import ProbabilityTrajectory
from forensics.analysis.orchestrator.mode import AnalysisMode
from forensics.analysis.orchestrator.parallel_shared import (
    _REQUIRED_AUTHOR_ARTIFACT_SUFFIXES,
    _resolve_max_workers,
    _run_repo_per_author_pipeline_with_artifacts,
)
from forensics.analysis.orchestrator.per_author import (
    _apply_global_test_gates,
    _run_per_author_analysis,
    _write_per_author_json_artifacts,
)
from forensics.analysis.orchestrator.worker_errors import parallel_worker_exception_is_recoverable
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import AnalysisResult, ChangePoint
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.repository import Repository

logger = logging.getLogger(__name__)

__all__ = [
    "IsolatedAuthorAnalysis",
    "_REQUIRED_AUTHOR_ARTIFACT_SUFFIXES",
    "_isolated_author_worker",
    "_run_isolated_author_jobs",
    "_per_author_worker",
    "_resolve_max_workers",
    "_resolve_parallel_refresh_workers",
    "_run_full_analysis_per_authors",
    "_run_repo_per_author_pipeline_with_artifacts",
    "_validate_and_promote_isolated_outputs",
    "run_parallel_author_refresh",
]


def _per_author_worker(
    slug: str,
    db_path: Path,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    prob_map: dict[str, ProbabilityTrajectory],
    mode: AnalysisMode,
) -> tuple[str, AnalysisResult | None, dict[str, float]]:
    if not mode.exploratory:
        logger.debug(
            "analysis worker: confirmatory mode slug=%s "
            "(strict feature JSON decode is scoped inside _run_per_author_analysis)",
            slug,
        )
    stage_timings: dict[str, float] = {}
    with Repository(db_path) as repo:
        assembled = _run_repo_per_author_pipeline_with_artifacts(
            slug,
            repo,
            paths,
            config,
            prob_map,
            mode,
            stage_timings,
            job_kind="analysis",
            emit_success_log=True,
        )
    if assembled is None:
        return slug, None, stage_timings
    return slug, assembled, stage_timings


def _finalize_parallel_author_results(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    results: dict[str, AnalysisResult],
) -> None:
    if not results:
        return
    gated_tests_by_slug = _apply_global_test_gates(
        {slug: res.hypothesis_tests for slug, res in results.items()},
        config.analysis,
    )
    for slug, res in list(results.items()):
        all_tests = gated_tests_by_slug.get(slug, [])
        assembled = res.model_copy(update={"hypothesis_tests": all_tests})
        results[slug] = assembled
        _write_per_author_json_artifacts(
            slug,
            paths,
            assembled.change_points,
            assembled.convergence_windows,
            assembled,
            all_tests,
        )


def _run_full_analysis_per_authors(
    slugs: list[str],
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    prob_map: dict[str, ProbabilityTrajectory],
    workers: int,
    mp_context: str | None,
    *,
    mode: AnalysisMode,
) -> tuple[dict[str, AnalysisResult], dict[str, dict[str, float]]]:
    results: dict[str, AnalysisResult] = {}
    per_author_timings: dict[str, dict[str, float]] = {}

    if workers <= 1:
        pending: dict[str, tuple[AnalysisResult, list[ChangePoint], list, list]] = {}
        with Repository(paths.db_path) as repo:
            for slug in slugs:
                stage_timings: dict[str, float] = {}
                per_author = _run_per_author_analysis(
                    slug,
                    repo,
                    paths,
                    config,
                    probability_trajectory_by_slug=prob_map,
                    stage_timings=stage_timings,
                    mode=mode,
                )
                per_author_timings[slug] = stage_timings
                if per_author is None:
                    continue
                pending[slug] = per_author

        gated_tests_by_slug = _apply_global_test_gates(
            {slug: raw_tests for slug, (_assembled, _cps, _windows, raw_tests) in pending.items()},
            config.analysis,
        )
        for slug, (assembled, change_points, convergence_windows, _raw_tests) in pending.items():
            all_tests = gated_tests_by_slug.get(slug, [])
            assembled = assembled.model_copy(update={"hypothesis_tests": all_tests})
            results[slug] = assembled
            _write_per_author_json_artifacts(
                slug,
                paths,
                change_points,
                convergence_windows,
                assembled,
                all_tests,
            )
            logger.info(
                "analysis: author=%s change_points=%d windows=%d tests=%d",
                slug,
                len(change_points),
                len(convergence_windows),
                len(all_tests),
            )
    else:
        worker_count = min(workers, max(1, len(slugs)))
        logger.info(
            "analysis: dispatching %d author(s) across %d worker(s)",
            len(slugs),
            worker_count,
        )
        ctx = (
            multiprocessing.get_context(mp_context)
            if mp_context
            else multiprocessing.get_context("spawn")
        )
        with ProcessPoolExecutor(max_workers=worker_count, mp_context=ctx) as executor:
            future_to_slug = {
                executor.submit(
                    _per_author_worker,
                    slug,
                    paths.db_path,
                    paths,
                    config,
                    prob_map,
                    mode,
                ): slug
                for slug in slugs
            }
            for future in as_completed(future_to_slug):
                slug = future_to_slug[future]
                try:
                    returned_slug, assembled, stage_timings = future.result()
                except BaseException as exc:
                    if not parallel_worker_exception_is_recoverable(mode, exc):
                        raise
                    logger.error(
                        "analysis: worker crashed for slug=%s (%s)",
                        slug,
                        exc,
                        exc_info=True,
                    )
                    per_author_timings[slug] = {}
                    continue
                per_author_timings[returned_slug] = stage_timings
                if assembled is not None:
                    results[returned_slug] = assembled

        _finalize_parallel_author_results(paths, config, results)

    return results, per_author_timings


_orchestrator_refresh = import_module("forensics.analysis.orchestrator.refresh")

IsolatedAuthorAnalysis = _orchestrator_refresh.IsolatedAuthorAnalysis
_isolated_author_worker = _orchestrator_refresh._isolated_author_worker
_run_isolated_author_jobs = _orchestrator_refresh._run_isolated_author_jobs
_resolve_parallel_refresh_workers = _orchestrator_refresh._resolve_parallel_refresh_workers
_validate_and_promote_isolated_outputs = (
    _orchestrator_refresh._validate_and_promote_isolated_outputs
)
run_parallel_author_refresh = _orchestrator_refresh.run_parallel_author_refresh
