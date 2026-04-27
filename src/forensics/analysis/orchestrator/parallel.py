"""Parallel/isolated author execution for analysis orchestration."""

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
from forensics.analysis.drift import EmbeddingDriftInputsError, EmbeddingRevisionGateError
from forensics.analysis.orchestrator.comparison import (
    _resolve_targets_and_controls,
    _run_target_control_comparisons,
)
from forensics.analysis.orchestrator.per_author import (
    _apply_global_test_gates,
    _run_per_author_analysis,
    _write_per_author_json_artifacts,
)
from forensics.analysis.orchestrator.staleness import _merge_run_metadata, _stale_author_slugs
from forensics.analysis.probability_trajectories import build_probability_trajectory_by_slug
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import AnalysisResult, ChangePoint
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.json_io import write_json_artifact
from forensics.storage.repository import Repository
from forensics.utils.provenance import (
    compute_model_config_hash,
    write_corpus_custody,
)

logger = logging.getLogger(__name__)


def _embedding_fail_should_propagate(exploratory: bool, exc: BaseException) -> bool:
    """Confirmatory runs surface embedding drift failures instead of swallowing them."""
    return (not exploratory) and isinstance(
        exc,
        (EmbeddingDriftInputsError, EmbeddingRevisionGateError),
    )


_REQUIRED_AUTHOR_ARTIFACT_SUFFIXES = (
    "_result.json",
    "_changepoints.json",
    "_convergence.json",
    "_hypothesis_tests.json",
)


def _persist_isolated_refresh_error(
    paths: AnalysisArtifactPaths,
    author_slug: str,
    exc: BaseException,
) -> None:
    """Write a JSON sidecar next to scrape error logs when an isolated worker fails."""
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


def _per_author_worker(
    slug: str,
    db_path: Path,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    prob_map: dict[str, ProbabilityTrajectory],
    exploratory: bool,
    allow_pre_phase16_embeddings: bool,
) -> tuple[str, AnalysisResult | None, dict[str, float]]:
    """ProcessPool worker: opens its own ``Repository`` (SQLite is not fork-safe).

    Returns ``(slug, assembled_or_None, stage_timings)``. The worker writes
    the per-author JSON artifacts directly via ``write_json_artifact`` (atomic
    rename); the main process aggregates the assembled results dict and
    handles newsroom-wide artifacts (``comparison_report.json``,
    ``run_metadata.json``, ``corpus_custody.json``).

    Log lines are tagged with ``slug=%s`` so concurrent worker output can be
    disambiguated when grepping the run log.
    """
    stage_timings: dict[str, float] = {}
    with Repository(db_path) as repo:
        per_author = _run_per_author_analysis(
            slug,
            repo,
            paths,
            config,
            probability_trajectory_by_slug=prob_map,
            stage_timings=stage_timings,
            exploratory=exploratory,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
        )
    if per_author is None:
        logger.info("analysis: slug=%s skipped (missing author or features)", slug)
        return slug, None, stage_timings
    assembled, change_points, convergence_windows, all_tests = per_author
    _write_per_author_json_artifacts(
        slug,
        paths,
        change_points,
        convergence_windows,
        assembled,
        all_tests,
    )
    logger.info(
        "analysis: slug=%s change_points=%d windows=%d tests=%d",
        slug,
        len(change_points),
        len(convergence_windows),
        len(all_tests),
    )
    return slug, assembled, stage_timings


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
    exploratory: bool,
    allow_pre_phase16_embeddings: bool,
) -> IsolatedAuthorAnalysis | None:
    """Run one author into ``data/analysis/parallel/<run_id>/<slug>/``."""
    isolated_paths = _isolated_author_paths(paths, run_id, slug)
    stage_timings: dict[str, float] = {}
    with Repository(paths.db_path) as repo:
        per_author = _run_per_author_analysis(
            slug,
            repo,
            isolated_paths,
            config,
            probability_trajectory_by_slug=prob_map,
            stage_timings=stage_timings,
            exploratory=exploratory,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
        )
    if per_author is None:
        logger.info("analysis-refresh: slug=%s skipped (missing author or features)", slug)
        return None
    assembled, change_points, convergence_windows, all_tests = per_author
    _write_per_author_json_artifacts(
        slug,
        isolated_paths,
        change_points,
        convergence_windows,
        assembled,
        all_tests,
    )
    return IsolatedAuthorAnalysis(
        slug=slug,
        analysis_dir=isolated_paths.analysis_dir,
        result=assembled,
        stage_timings=stage_timings,
    )


def _resolve_max_workers(config: ForensicsSettings, override: int | None) -> int:
    """Resolve the worker count: explicit override > config > ``cpu_count - 1``.

    Always returns ``>= 1``. ``override`` of ``1`` (or any non-positive value
    from config / CPU detection) keeps the legacy serial dispatch.
    """
    if override is not None:
        return max(1, int(override))
    cfg = config.analysis.max_workers
    if cfg is not None:
        return max(1, int(cfg))
    cpu = os.cpu_count() or 1
    return max(1, cpu - 1)


def _resolve_parallel_refresh_workers(config: ForensicsSettings, override: int | None) -> int:
    """Resolve conservative worker count for isolated author refresh jobs."""
    if override is not None or config.analysis.max_workers is not None:
        return _resolve_max_workers(config, override)
    cpu = os.cpu_count() or 1
    return min(3, max(1, cpu - 1))


def _finalize_parallel_author_results(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    results: dict[str, AnalysisResult],
) -> None:
    """Apply global hypothesis gates and write per-author JSON after parallel workers."""
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
    exploratory: bool,
    allow_pre_phase16_embeddings: bool,
) -> tuple[dict[str, AnalysisResult], dict[str, dict[str, float]]]:
    """Serial or parallel per-author analysis, global test gating, artifact writes."""
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
                    exploratory=exploratory,
                    allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
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
        # C-09 — default to spawn (macOS-safe); tests pass ``mp_context="fork"`` for parity hooks.
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
                    exploratory,
                    allow_pre_phase16_embeddings,
                ): slug
                for slug in slugs
            }
            for future in as_completed(future_to_slug):
                slug = future_to_slug[future]
                try:
                    returned_slug, assembled, stage_timings = future.result()
                except Exception as exc:  # noqa: BLE001 - log + continue per-author
                    if _embedding_fail_should_propagate(exploratory, exc):
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


def _validate_isolated_author_output(
    isolated: IsolatedAuthorAnalysis,
    config: ForensicsSettings,
) -> None:
    expected = compute_model_config_hash(config.analysis, length=16, round_trip=True)
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
    """Validate every isolated author output before promoting any canonical artifact."""
    for isolated in isolated_outputs:
        _validate_isolated_author_output(isolated, config)
    for isolated in isolated_outputs:
        _promote_isolated_author_output(isolated, paths)
    # I-06 — explicit marker so operators can tell the last parallel promotion completed cleanly.
    marker = paths.analysis_dir / "parallel_promotion_complete.json"
    write_json_artifact(
        marker,
        {
            "validated_slugs": sorted(item.slug for item in isolated_outputs),
            "config_hash": compute_model_config_hash(config.analysis, length=16, round_trip=True),
        },
    )


def _run_isolated_author_serial_jobs(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    slugs: list[str],
    *,
    run_id: str,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory],
    exploratory: bool,
    allow_pre_phase16_embeddings: bool,
) -> list[IsolatedAuthorAnalysis]:
    isolated_outputs: list[IsolatedAuthorAnalysis] = []
    for slug in slugs:
        try:
            isolated = _isolated_author_worker(
                slug,
                paths,
                config,
                probability_trajectory_by_slug,
                run_id,
                exploratory,
                allow_pre_phase16_embeddings,
            )
        except Exception as exc:  # noqa: BLE001 — mirror full-analysis worker policy
            if _embedding_fail_should_propagate(exploratory, exc):
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


def _run_isolated_author_jobs(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    slugs: list[str],
    *,
    run_id: str,
    max_workers: int,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory],
    exploratory: bool,
    allow_pre_phase16_embeddings: bool,
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
            exploratory=exploratory,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
        )
    isolated_outputs: list[IsolatedAuthorAnalysis] = []
    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=worker_count, mp_context=ctx) as executor:
        future_to_slug = {
            executor.submit(
                _isolated_author_worker,
                slug,
                paths,
                config,
                probability_trajectory_by_slug,
                run_id,
                exploratory,
                allow_pre_phase16_embeddings,
            ): slug
            for slug in slugs
        }
        for fut in as_completed(future_to_slug):
            author_slug = future_to_slug[fut]
            try:
                isolated = fut.result()
            except Exception as exc:  # noqa: BLE001 — mirror full-analysis worker policy
                if _embedding_fail_should_propagate(exploratory, exc):
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


def run_parallel_author_refresh(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    author_slug: str | None = None,
    max_workers: int | None = None,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory] | None = None,
    exploratory: bool = False,
    allow_pre_phase16_embeddings: bool = False,
) -> dict[str, AnalysisResult]:
    """Refresh stale configured authors through isolated parallel author directories.

    When ``probability_trajectory_by_slug`` is ``None``, trajectories are loaded
    the same way as :func:`run_full_analysis` (feature parquet or
    ``data/probability/<slug>.parquet``).
    """
    run_id = str(uuid4())
    slugs = _stale_author_slugs(paths, config, author_slug)
    workers = _resolve_parallel_refresh_workers(config, max_workers)
    logger.info(
        "analysis-refresh: refreshing %d stale author(s) with %d worker(s)",
        len(slugs),
        workers,
    )
    if probability_trajectory_by_slug is None:
        all_slugs = [a.slug for a in config.authors]
        prob_map = build_probability_trajectory_by_slug(paths, all_slugs)
    else:
        prob_map = probability_trajectory_by_slug
    isolated_outputs = _run_isolated_author_jobs(
        paths,
        config,
        slugs,
        run_id=run_id,
        max_workers=workers,
        probability_trajectory_by_slug=prob_map,
        exploratory=exploratory,
        allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
    )
    if not isolated_outputs:
        logger.info("analysis-refresh: no stale author artifacts to refresh")
        return {}

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
        refreshed = IsolatedAuthorAnalysis(
            slug=item.slug,
            analysis_dir=item.analysis_dir,
            result=assembled,
            stage_timings=item.stage_timings,
        )
        refreshed_outputs.append(refreshed)

    _validate_and_promote_isolated_outputs(refreshed_outputs, paths, config)

    targets, controls = _resolve_targets_and_controls(config, author_slug)
    comparison_payload = _run_target_control_comparisons(
        targets,
        controls,
        results,
        paths=paths,
        config=config,
        exploratory=exploratory,
    )
    if not comparison_payload.get("targets"):
        logger.warning(
            "comparison_report: empty targets — no target-vs-control comparisons produced; "
            "check target role in config, on-disk result artifacts, and --author scope (L-02)"
        )
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
    return results
