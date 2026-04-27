"""Top-level analysis runner orchestration."""

from __future__ import annotations

import logging
import time

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.convergence import ProbabilityTrajectory
from forensics.analysis.orchestrator.comparison import (
    _resolve_targets_and_controls,
    _run_target_control_comparisons,
)
from forensics.analysis.orchestrator.parallel import (
    _resolve_max_workers,
    _run_full_analysis_per_authors,
)
from forensics.analysis.orchestrator.per_author import assemble_analysis_result
from forensics.analysis.orchestrator.sensitivity import _run_section_residualized_sensitivity
from forensics.analysis.orchestrator.staleness import _merge_run_metadata
from forensics.analysis.orchestrator.timings import AnalysisTimings
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import AnalysisResult
from forensics.storage.json_io import write_json_artifact
from forensics.utils.provenance import read_latest_scraped_at_iso, write_corpus_custody

logger = logging.getLogger(__name__)

__all__ = ["assemble_analysis_result", "run_full_analysis"]


def run_full_analysis(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    author_slug: str | None = None,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory] | None = None,
    max_workers: int | None = None,
    compare_pair: tuple[str, str] | None = None,
    timings_out: AnalysisTimings | None = None,
    mp_context: str | None = None,
    exploratory: bool = False,
    allow_pre_phase16_embeddings: bool = False,
) -> dict[str, AnalysisResult]:
    """Run per-author analysis, comparisons, and shared artifacts under ``paths``.

    Parallel mode: workers return :class:`AnalysisResult` and write per-slug JSON
    only (no shared SQLite). ``compare_pair``, ``timings_out``, and ``mp_context``
    follow the CLI / test contracts; preregistration gates live upstream.
    """
    # Parent dirs for analysis outputs are created inside the write helpers
    # (``write_json_artifact`` / ``write_corpus_custody``); no explicit mkdir
    # needed here (RF-DRY-004).
    slugs = [author_slug] if author_slug else [a.slug for a in config.authors]
    prob_map = probability_trajectory_by_slug or {}
    workers = _resolve_max_workers(config, max_workers)
    # Always serial when there's only one author — spinning up a ProcessPool
    # for a single task wastes seconds of fork / spawn overhead and forfeits
    # the in-process monkeypatching the parity test relies on.
    if len(slugs) <= 1:
        workers = 1

    t_total = time.perf_counter()
    results, per_author_timings = _run_full_analysis_per_authors(
        slugs,
        paths,
        config,
        prob_map,
        workers,
        mp_context,
        exploratory=exploratory,
        allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
    )

    sensitivity_summary = _run_section_residualized_sensitivity(
        paths,
        config,
        slugs,
        results,
        probability_trajectory_by_slug=prob_map,
        exploratory=exploratory,
        allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
    )

    t_compare = time.perf_counter()
    targets, controls = _resolve_targets_and_controls(
        config,
        author_slug,
        compare_pair=compare_pair,
    )
    comparison_payload = _run_target_control_comparisons(
        targets,
        controls,
        results,
        paths=paths,
        config=config,
    )
    compare_seconds = time.perf_counter() - t_compare

    if not comparison_payload.get("targets"):
        logger.warning(
            "comparison_report: empty targets — no target-vs-control comparisons produced; "
            "check target role in config, on-disk result artifacts, and --author scope (L-02)"
        )

    write_json_artifact(paths.comparison_report_json(), comparison_payload)

    scraped = read_latest_scraped_at_iso(paths.db_path)
    _merge_run_metadata(
        paths,
        results,
        comparison_payload,
        last_scraped_at=scraped,
        section_residualized_sensitivity=sensitivity_summary if sensitivity_summary else None,
    )

    write_corpus_custody(paths.db_path, paths.analysis_dir)

    if timings_out is not None:
        timings_out.per_author = per_author_timings
        timings_out.compare = compare_seconds
        timings_out.total = time.perf_counter() - t_total

    return results
