"""Isolated parallel author refresh (promote-from-private workdirs)."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from forensics.analysis.convergence import ProbabilityTrajectory
from forensics.analysis.orchestrator.comparison import (
    _resolve_targets_and_controls,
    _run_target_control_comparisons,
    warn_comparison_report_empty_targets,
)
from forensics.analysis.orchestrator.mode import DEFAULT_ANALYSIS_MODE, AnalysisMode
from forensics.analysis.orchestrator.parallel_shared import (
    _REQUIRED_AUTHOR_ARTIFACT_SUFFIXES,
    _resolve_max_workers,
    _run_repo_per_author_pipeline_with_artifacts,
)
from forensics.analysis.orchestrator.per_author import (
    _apply_global_test_gates,
    _write_per_author_json_artifacts,
)
from forensics.analysis.orchestrator.staleness import _merge_run_metadata, _stale_author_slugs
from forensics.analysis.orchestrator.worker_errors import parallel_worker_exception_is_recoverable
from forensics.analysis.probability_trajectories import build_probability_trajectory_by_slug
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import AnalysisResult
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.json_io import write_json_artifact
from forensics.storage.repository import Repository
from forensics.utils.provenance import compute_analysis_config_hash, write_corpus_custody

logger = logging.getLogger(__name__)


def _dispatch_isolated_author_worker(
    slug: str,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    prob_map: dict[str, ProbabilityTrajectory],
    run_id: str,
    mode: AnalysisMode,
) -> IsolatedAuthorAnalysis | None:
    """Delegate to :data:`parallel._isolated_author_worker` so tests can monkeypatch it."""
    from forensics.analysis.orchestrator import parallel as _parallel_mod

    return _parallel_mod._isolated_author_worker(slug, paths, config, prob_map, run_id, mode)


def _persist_isolated_refresh_error(
    paths: AnalysisArtifactPaths,
    author_slug: str,
    exc: BaseException,
) -> None:
    err_path = paths.scrape_errors_path / f"isolated_refresh_{author_slug}.json"
    write_json_artifact(
        err_path,
        {
            "author_slug": author_slug,
            "job_kind": "isolated_refresh",
            "error": repr(exc),
        },
    )


@dataclass(frozen=True, slots=True)
class IsolatedAuthorAnalysis:
    """One author result produced in a private analysis directory."""

    slug: str
    analysis_dir: Path
    result: AnalysisResult
    stage_timings: dict[str, float] = field(default_factory=dict)


def _isolated_author_paths(
    paths: AnalysisArtifactPaths,
    run_id: str,
    slug: str,
) -> AnalysisArtifactPaths:
    return paths.with_analysis_dir(paths.analysis_dir / "parallel" / run_id / slug)


def _isolated_author_worker(
    slug: str,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    prob_map: dict[str, ProbabilityTrajectory],
    run_id: str,
    mode: AnalysisMode,
) -> IsolatedAuthorAnalysis | None:
    if not mode.exploratory:
        logger.debug(
            "analysis-refresh worker: confirmatory mode slug=%s "
            "(strict feature JSON decode is scoped inside _run_per_author_analysis)",
            slug,
        )
    isolated_paths = _isolated_author_paths(paths, run_id, slug)
    stage_timings: dict[str, float] = {}
    with Repository(paths.db_path) as repo:
        assembled = _run_repo_per_author_pipeline_with_artifacts(
            slug,
            repo,
            isolated_paths,
            config,
            prob_map,
            mode,
            stage_timings,
            job_kind="analysis-refresh",
            emit_success_log=False,
        )
    if assembled is None:
        return None
    return IsolatedAuthorAnalysis(
        slug=slug,
        analysis_dir=isolated_paths.analysis_dir,
        result=assembled,
        stage_timings=stage_timings,
    )


def _resolve_parallel_refresh_workers(config: ForensicsSettings, override: int | None) -> int:
    if override is not None or config.analysis.max_workers is not None:
        return _resolve_max_workers(config, override)
    cpu = os.cpu_count() or 1
    return min(3, max(1, cpu - 1))


def _validate_isolated_author_output(
    isolated: IsolatedAuthorAnalysis,
    config: ForensicsSettings,
) -> None:
    expected = compute_analysis_config_hash(config)
    result_path = isolated.analysis_dir / f"{isolated.slug}_result.json"
    if not result_path.is_file():
        msg = f"missing isolated result artifact: {result_path}"
        raise ValueError(msg)
    result = AnalysisResult.model_validate_json(result_path.read_text(encoding="utf-8"))
    if result.config_hash != expected:
        msg = (
            f"stale isolated result for {isolated.slug}: "
            f"config_hash={result.config_hash!r} expected={expected!r}"
        )
        raise ValueError(msg)
    missing = [
        str(isolated.analysis_dir / f"{isolated.slug}{suffix}")
        for suffix in _REQUIRED_AUTHOR_ARTIFACT_SUFFIXES
        if not (isolated.analysis_dir / f"{isolated.slug}{suffix}").is_file()
    ]
    if missing:
        msg = f"missing isolated companion artifacts for {isolated.slug}: {'; '.join(missing)}"
        raise ValueError(msg)


def _promote_isolated_author_output(
    isolated: IsolatedAuthorAnalysis,
    paths: AnalysisArtifactPaths,
) -> None:
    for src in sorted(isolated.analysis_dir.glob(f"{isolated.slug}_*")):
        dst = paths.analysis_dir / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(f".{dst.name}.tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)


def _validate_and_promote_isolated_outputs(
    isolated_outputs: list[IsolatedAuthorAnalysis],
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
) -> None:
    for isolated in isolated_outputs:
        _validate_isolated_author_output(isolated, config)
    for isolated in isolated_outputs:
        _promote_isolated_author_output(isolated, paths)
    marker = paths.analysis_dir / "parallel_promotion_complete.json"
    write_json_artifact(
        marker,
        {
            "validated_slugs": sorted(item.slug for item in isolated_outputs),
            "config_hash": compute_analysis_config_hash(config),
        },
    )


def _run_isolated_author_serial_jobs(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    slugs: list[str],
    *,
    run_id: str,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory],
    mode: AnalysisMode,
) -> list[IsolatedAuthorAnalysis]:
    isolated_outputs: list[IsolatedAuthorAnalysis] = []
    for slug in slugs:
        try:
            isolated = _dispatch_isolated_author_worker(
                slug,
                paths,
                config,
                probability_trajectory_by_slug,
                run_id,
                mode,
            )
        except BaseException as exc:
            if not parallel_worker_exception_is_recoverable(mode, exc):
                raise
            logger.exception(
                "isolated refresh worker failed",
                extra={"author_slug": slug, "job_kind": "isolated_refresh", "error": repr(exc)},
            )
            _persist_isolated_refresh_error(paths, slug, exc)
            continue
        if isolated is None:
            logger.warning("analysis-refresh: skipped %s", slug)
            continue
        isolated_outputs.append(isolated)
    return isolated_outputs


def _run_isolated_author_parallel_jobs(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    slugs: list[str],
    *,
    run_id: str,
    worker_count: int,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory],
    mode: AnalysisMode,
) -> list[IsolatedAuthorAnalysis]:
    isolated_outputs: list[IsolatedAuthorAnalysis] = []
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=worker_count, mp_context=ctx) as executor:
        future_to_slug = {
            executor.submit(
                _dispatch_isolated_author_worker,
                slug,
                paths,
                config,
                probability_trajectory_by_slug,
                run_id,
                mode,
            ): slug
            for slug in slugs
        }
        for fut in as_completed(future_to_slug):
            author_slug = future_to_slug[fut]
            try:
                isolated = fut.result()
            except BaseException as exc:
                if not parallel_worker_exception_is_recoverable(mode, exc):
                    raise
                logger.exception(
                    "isolated refresh worker failed",
                    extra={
                        "author_slug": author_slug,
                        "job_kind": "isolated_refresh",
                        "error": repr(exc),
                    },
                )
                _persist_isolated_refresh_error(paths, author_slug, exc)
                continue
            if isolated is None:
                logger.warning("analysis-refresh: skipped %s", author_slug)
                continue
            isolated_outputs.append(isolated)
    return sorted(isolated_outputs, key=lambda item: item.slug)


def _run_isolated_author_jobs(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    slugs: list[str],
    *,
    run_id: str,
    max_workers: int,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory],
    mode: AnalysisMode,
) -> list[IsolatedAuthorAnalysis]:
    if not slugs:
        return []
    worker_count = min(max(1, max_workers), len(slugs))
    if worker_count <= 1:
        return _run_isolated_author_serial_jobs(
            paths,
            config,
            slugs,
            run_id=run_id,
            probability_trajectory_by_slug=probability_trajectory_by_slug,
            mode=mode,
        )
    return _run_isolated_author_parallel_jobs(
        paths,
        config,
        slugs,
        run_id=run_id,
        worker_count=worker_count,
        probability_trajectory_by_slug=probability_trajectory_by_slug,
        mode=mode,
    )


def _prepare_parallel_refresh_inputs(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    author_slug: str | None,
    max_workers: int | None,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory] | None,
) -> tuple[str, list[str], int, dict[str, ProbabilityTrajectory]]:
    run_id = str(uuid4())
    slugs = _stale_author_slugs(paths, config, author_slug)
    workers = _resolve_parallel_refresh_workers(config, max_workers)
    if probability_trajectory_by_slug is None:
        all_slugs = [a.slug for a in config.authors]
        prob_map = build_probability_trajectory_by_slug(paths, all_slugs)
    else:
        prob_map = probability_trajectory_by_slug
    return run_id, slugs, workers, prob_map


def _build_gated_refresh_outputs(
    isolated_outputs: list[IsolatedAuthorAnalysis],
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
) -> tuple[dict[str, AnalysisResult], list[IsolatedAuthorAnalysis]]:
    results = {item.slug: item.result for item in isolated_outputs}
    gated_tests_by_slug = _apply_global_test_gates(
        {slug: result.hypothesis_tests for slug, result in results.items()},
        config.analysis,
    )
    refreshed_outputs: list[IsolatedAuthorAnalysis] = []
    for item in isolated_outputs:
        all_tests = gated_tests_by_slug.get(item.slug, [])
        assembled = item.result.model_copy(update={"hypothesis_tests": all_tests})
        results[item.slug] = assembled
        isolated_paths = paths.with_analysis_dir(item.analysis_dir)
        _write_per_author_json_artifacts(
            item.slug,
            isolated_paths,
            assembled.change_points,
            assembled.convergence_windows,
            assembled,
            all_tests,
        )
        refreshed_outputs.append(
            IsolatedAuthorAnalysis(
                slug=item.slug,
                analysis_dir=item.analysis_dir,
                result=assembled,
                stage_timings=item.stage_timings,
            )
        )
    return results, refreshed_outputs


def _finalize_parallel_refresh_artifacts(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    results: dict[str, AnalysisResult],
    refreshed_outputs: list[IsolatedAuthorAnalysis],
    run_id: str,
    workers: int,
    author_slug: str | None,
    mode: AnalysisMode,
) -> None:
    _validate_and_promote_isolated_outputs(refreshed_outputs, paths, config)
    targets, controls = _resolve_targets_and_controls(config, author_slug)
    comparison_payload = _run_target_control_comparisons(
        targets,
        controls,
        results,
        paths=paths,
        config=config,
        mode=mode,
    )
    if not comparison_payload.get("targets"):
        warn_comparison_report_empty_targets()
    write_json_artifact(paths.comparison_report_json(), comparison_payload)
    _merge_run_metadata(paths, results, comparison_payload)
    meta_path = paths.run_metadata_json()
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    meta["parallel_author_refresh"] = {
        "run_id": run_id,
        "refreshed_authors": sorted(results),
        "workers": workers,
        "isolated_root": str(paths.analysis_dir / "parallel" / run_id),
    }
    write_json_artifact(meta_path, meta)
    write_corpus_custody(paths.db_path, paths.analysis_dir)


def run_parallel_author_refresh(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    author_slug: str | None = None,
    max_workers: int | None = None,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory] | None = None,
    mode: AnalysisMode = DEFAULT_ANALYSIS_MODE,
) -> dict[str, AnalysisResult]:
    """Refresh stale per-author analysis artifacts via isolated workdirs, then promote.

    Stale slugs are discovered under ``paths``; each author is re-analyzed in
    ``data/analysis/parallel/<run_id>/<slug>/``. After global hypothesis gating,
    outputs are validated and copied to the canonical ``paths.analysis_dir``,
    then ``comparison_report.json`` and ``run_metadata.json`` are rebuilt.

    Args:
        paths: Artifact layout (DB + analysis directories).
        config: Loaded ``ForensicsSettings``.
        author_slug: Optional single slug; otherwise all configured authors that
            need refresh.
        max_workers: Optional override for worker count (else config/CPU heuristics).
        probability_trajectory_by_slug: Optional pre-built trajectories; if
            omitted, trajectories are built like :func:`run_full_analysis`.
        mode: Confirmatory vs exploratory embedding policy.

    Returns:
        Mapping of author slug to refreshed :class:`AnalysisResult`.
    """
    run_id, slugs, workers, prob_map = _prepare_parallel_refresh_inputs(
        paths,
        config,
        author_slug=author_slug,
        max_workers=max_workers,
        probability_trajectory_by_slug=probability_trajectory_by_slug,
    )
    logger.info(
        "analysis-refresh: refreshing %d stale author(s) with %d worker(s)",
        len(slugs),
        workers,
    )
    isolated_outputs = _run_isolated_author_jobs(
        paths,
        config,
        slugs,
        run_id=run_id,
        max_workers=workers,
        probability_trajectory_by_slug=prob_map,
        mode=mode,
    )
    if not isolated_outputs:
        logger.info("analysis-refresh: no stale author artifacts to refresh")
        return {}

    results, refreshed_outputs = _build_gated_refresh_outputs(isolated_outputs, paths, config)
    _finalize_parallel_refresh_artifacts(
        paths,
        config,
        results=results,
        refreshed_outputs=refreshed_outputs,
        run_id=run_id,
        workers=workers,
        author_slug=author_slug,
        mode=mode,
    )
    return results


# __all__ keeps leading-underscore names so tests and
# ``forensics.analysis.orchestrator`` can patch the same entry points that
# historically lived on ``parallel``; they are not a stable public API.
__all__ = [
    "IsolatedAuthorAnalysis",
    "_isolated_author_worker",
    "_resolve_parallel_refresh_workers",
    "_validate_and_promote_isolated_outputs",
    "run_parallel_author_refresh",
]
