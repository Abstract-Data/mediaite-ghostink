"""Top-level analysis runner orchestration."""

from __future__ import annotations

import json
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
from forensics.utils.provenance import write_corpus_custody

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
    """Run changepoint + drift + convergence + hypothesis tests; write JSON artifacts.

    Previously declared ``async`` for historical reasons — the body is entirely
    synchronous (Repository / Polars / NumPy) so the coroutine wrapper was dead
    weight. Callers now invoke the function directly instead of via
    ``asyncio.run(...)``.

    Phase 15 G1: when ``max_workers`` (or ``settings.analysis.max_workers``)
    resolves to ``> 1`` the per-author loop dispatches via
    :class:`concurrent.futures.ProcessPoolExecutor`. Each worker opens its own
    :class:`Repository` (SQLite handles are not safe to fork), writes its own
    per-author JSON artifacts (atomic via ``write_json_artifact``), and
    returns the assembled :class:`AnalysisResult` plus per-stage timings to
    the main process for aggregation. The main process owns the newsroom-wide
    artifacts (``comparison_report.json``, ``run_metadata.json``,
    ``corpus_custody.json``) so there is no shared mutable state.

    ``compare_pair`` overrides the ``settings.authors`` target/control roles
    for the explicit ``(target_slug, control_slug)`` pair so the
    ``forensics analyze --compare TARGET,CONTROL`` flag can drive a one-off
    comparison without editing ``config.toml``.

    ``timings_out`` (when provided) is populated in-place with per-author
    stage wall-clock seconds plus the newsroom-wide ``compare`` and ``total``
    buckets so the bench script can emit non-zero per-stage measurements.

    ``mp_context`` selects the ``multiprocessing`` start method for the
    worker pool (e.g. ``"fork"`` / ``"spawn"`` / ``"forkserver"``). The
    ``"fork"`` context inherits the parent process' module state — used by
    the parity test in ``tests/integration/test_parallel_parity.py`` so the
    monkeypatched ``uuid4`` / ``datetime`` pinning propagates into workers.
    Production callers should leave this ``None`` (system default).
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

    write_json_artifact(paths.comparison_report_json(), comparison_payload)

    _merge_run_metadata(paths, results, comparison_payload)
    if sensitivity_summary:
        meta_path = paths.run_metadata_json()
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
        meta["section_residualized_sensitivity"] = sensitivity_summary
        write_json_artifact(meta_path, meta)

    write_corpus_custody(paths.db_path, paths.analysis_dir)

    if timings_out is not None:
        timings_out.per_author = per_author_timings
        timings_out.compare = compare_seconds
        timings_out.total = time.perf_counter() - t_total

    return results
