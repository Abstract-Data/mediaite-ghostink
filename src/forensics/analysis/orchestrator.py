"""Phase 7 orchestration: assemble ``AnalysisResult`` and run full multi-author analysis."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import shutil
import time
from bisect import bisect_left
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import polars as pl

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.changepoint import (
    analyze_author_feature_changepoints,
)
from forensics.analysis.comparison import compare_target_to_controls
from forensics.analysis.convergence import (
    ConvergenceInput,
    ProbabilityTrajectory,
    compute_convergence_scores,
)
from forensics.analysis.drift import (
    EmbeddingRevisionGateError,
    compute_author_drift_pipeline,
    load_article_embeddings,
)
from forensics.analysis.era import classify_ai_marker_era
from forensics.analysis.evidence import filter_evidence_change_points
from forensics.analysis.statistics import (
    apply_correction,
    compute_n_rankable_features_per_family,
    filter_by_effect_size,
    run_hypothesis_tests,
)
from forensics.analysis.utils import pair_months_with_velocities
from forensics.config.settings import AnalysisConfig, ForensicsSettings
from forensics.models.analysis import AnalysisResult, ChangePoint, DriftScores
from forensics.models.features import strict_feature_decode_confirmatory
from forensics.preregistration import (
    PREREGISTERED_FEATURES,
    PREREGISTERED_SPLIT_DATE,
    PREREGISTERED_TEST_PREFIXES,
)
from forensics.storage.json_io import stable_sort_artifact_list, write_json_artifact
from forensics.storage.parquet import load_feature_frame_sorted
from forensics.storage.repository import Repository
from forensics.utils.datetime import timestamps_from_frame
from forensics.utils.provenance import (
    compute_model_config_hash,
    validate_analysis_result_config_hashes,
    write_corpus_custody,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AnalysisTimings",
    "assemble_analysis_result",
    "run_compare_only",
    "run_full_analysis",
    "run_parallel_author_refresh",
]


@dataclass
class AnalysisTimings:
    """Per-stage wall-clock seconds captured during ``run_full_analysis``.

    ``per_author`` maps ``slug → {stage_name: seconds}`` so the bench script
    can emit non-zero per-stage timings instead of only ``total``. ``compare``
    is a single newsroom-wide bucket because the comparison stage runs once
    per target outside the per-author loop.
    """

    per_author: dict[str, dict[str, float]] = field(default_factory=dict)
    compare: float = 0.0
    total: float = 0.0


@dataclass(frozen=True, slots=True)
class IsolatedAuthorAnalysis:
    """One author result produced in a private analysis directory."""

    slug: str
    analysis_dir: Path
    result: AnalysisResult
    stage_timings: dict[str, float] = field(default_factory=dict)


_REQUIRED_AUTHOR_ARTIFACT_SUFFIXES = (
    "_result.json",
    "_changepoints.json",
    "_convergence.json",
    "_hypothesis_tests.json",
)


def _ts_key(t: datetime) -> float:
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.timestamp()


def _breakpoint_index(timestamps: list[datetime], event: datetime) -> int:
    keys = [_ts_key(t) for t in timestamps]
    x = _ts_key(event)
    i = bisect_left(keys, x)
    return max(1, min(len(timestamps) - 1, i))


def _write_per_author_json_artifacts(
    slug: str,
    paths: AnalysisArtifactPaths,
    change_points: list[ChangePoint],
    convergence_windows: list,
    assembled: AnalysisResult,
    all_tests: list,
) -> None:
    # Phase 15 H2 — sort list-valued artifact bodies on the stable-tuple spec
    # so parallel and serial dispatch produce byte-identical JSON.
    write_json_artifact(
        paths.changepoints_json(slug),
        stable_sort_artifact_list(change_points, kind="change_points"),
    )
    write_json_artifact(
        paths.convergence_json(slug),
        stable_sort_artifact_list(convergence_windows, kind="convergence_windows"),
    )
    write_json_artifact(paths.result_json(slug), assembled)
    write_json_artifact(
        paths.hypothesis_tests_json(slug),
        stable_sort_artifact_list(all_tests, kind="hypothesis_tests"),
    )


def _clean_feature_series(df_author: pl.DataFrame, feature_name: str) -> list[float]:
    """Cast to float, median-impute NaN / inf, and return a plain ``list[float]``.

    Hoisted out of :func:`_run_hypothesis_tests_for_changepoints` so the per-
    feature cleaning can be cached across multiple change-points on the same
    feature (Phase 15 F2) and so tests can monkeypatch this symbol to assert
    cache-hit behaviour.
    """
    raw = df_author[feature_name].cast(pl.Float64, strict=False).to_numpy()
    finite = raw[np.isfinite(raw)]
    med = float(np.nanmedian(finite)) if finite.size else 0.0
    clean = np.nan_to_num(raw, nan=med)
    return [float(x) for x in clean]


def _run_hypothesis_tests_for_changepoints(
    df_author: pl.DataFrame,
    timestamps: list[datetime],
    change_points: list[ChangePoint],
    author_id: str,
    analysis_cfg: AnalysisConfig,
) -> list:
    # Phase 15 F2: cache cleaned per-feature series so multiple CPs on the
    # same feature reuse one median-imputation pass instead of re-scanning
    # the dataframe each iteration.
    feature_cache: dict[str, tuple[list[float], int]] = {}
    all_tests: list = []
    for cp in change_points:
        if cp.feature_name not in df_author.columns:
            continue
        cached = feature_cache.get(cp.feature_name)
        if cached is None:
            series = _clean_feature_series(df_author, cp.feature_name)
            feature_cache[cp.feature_name] = (series, len(series))
        series, n = feature_cache[cp.feature_name]
        if n < 6 or n != len(timestamps):
            continue
        bidx = _breakpoint_index(timestamps, cp.timestamp)
        all_tests.extend(
            run_hypothesis_tests(
                series,
                bidx,
                cp.feature_name,
                author_id,
                n_bootstrap=analysis_cfg.bootstrap_iterations,
                enable_ks_test=analysis_cfg.enable_ks_test,
            )
        )
    return all_tests


def _run_preregistered_split_tests(
    df_author: pl.DataFrame,
    timestamps: list[datetime],
    author_id: str,
    analysis_cfg: AnalysisConfig,
) -> list:
    if not timestamps:
        return []
    split_dt = datetime.combine(PREREGISTERED_SPLIT_DATE, dt_time.min, tzinfo=UTC)
    split_idx = bisect_left([_ts_key(t) for t in timestamps], _ts_key(split_dt))
    all_tests: list = []
    allowed_prefixes = tuple(f"{prefix}_" for prefix in PREREGISTERED_TEST_PREFIXES)
    for feature in PREREGISTERED_FEATURES:
        if feature not in df_author.columns:
            continue
        raw = df_author[feature].cast(pl.Float64, strict=False).to_numpy()
        finite = raw[np.isfinite(raw)]
        if finite.size == 0:
            continue
        fill = float(np.nanmedian(finite))
        series = [float(x) for x in np.nan_to_num(raw, nan=fill)]
        tests = run_hypothesis_tests(
            series,
            split_idx,
            feature,
            author_id,
            n_bootstrap=analysis_cfg.bootstrap_iterations,
        )
        all_tests.extend(test for test in tests if test.test_name.startswith(allowed_prefixes))
    return all_tests


def _apply_global_test_gates(
    tests_by_slug: dict[str, list],
    analysis_cfg: AnalysisConfig,
) -> dict[str, list]:
    labeled = [(slug, test) for slug, tests in tests_by_slug.items() for test in tests]
    if not labeled:
        return {slug: [] for slug in tests_by_slug}
    corrected = apply_correction(
        [test for _slug, test in labeled],
        method=analysis_cfg.multiple_comparison_method,
        alpha=analysis_cfg.significance_threshold,
    )
    gated = filter_by_effect_size(
        corrected,
        analysis_cfg.effect_size_threshold,
        alpha=analysis_cfg.significance_threshold,
    )
    grouped: dict[str, list] = {slug: [] for slug in tests_by_slug}
    for (slug, _test), gated_test in zip(labeled, gated, strict=True):
        grouped[slug].append(gated_test)
    return grouped


class _StageTimer:
    """Context-manager-free stopwatch that no-ops when ``sink is None``.

    ``record(stage_name)`` writes the wall-clock since the last call (or
    since construction) into ``sink[stage_name]`` and resets the clock. Used
    by ``_run_per_author_analysis`` to thread per-stage timings through to
    the bench script without polluting the call site with branchy
    ``if stage_timings is not None:`` guards.
    """

    __slots__ = ("_sink", "_t")

    def __init__(self, sink: dict[str, float] | None) -> None:
        self._sink = sink
        self._t = time.perf_counter()

    def record(self, stage: str) -> None:
        if self._sink is None:
            return
        now = time.perf_counter()
        self._sink[stage] = now - self._t
        self._t = now


def _run_per_author_analysis(
    slug: str,
    repo: Repository,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory],
    stage_timings: dict[str, float] | None = None,
    exploratory: bool = False,
    allow_pre_phase16_embeddings: bool = False,
) -> tuple[AnalysisResult, list[ChangePoint], list, list] | None:
    """Changepoint, drift, convergence, and hypothesis testing for one author slug.

    When ``stage_timings`` is provided, the per-stage wall-clock seconds are
    written into the dict (keys: ``extract``, ``changepoint``, ``drift``,
    ``convergence``, ``hypothesis_tests``) so the bench script can emit
    non-zero per-stage measurements instead of only the grand ``total``.
    """
    with strict_feature_decode_confirmatory(exploratory):
        author = repo.get_author_by_slug(slug)
        if author is None:
            logger.warning("analysis: unknown slug=%s", slug)
            return None
        feat_path = paths.features_parquet(slug)
        if not feat_path.is_file():
            logger.warning("analysis: skip %s (missing %s)", slug, feat_path)
            return None

        timer = _StageTimer(stage_timings)
        lf_all = load_feature_frame_sorted(feat_path)
        lf_author = lf_all.filter(pl.col("author_id") == author.id)
        df_author = lf_author.collect()
        if df_author.is_empty():
            df_author = lf_all.collect()
        timer.record("extract")

        raw_change_points = analyze_author_feature_changepoints(
            df_author,
            author_id=author.id,
            settings=config,
        )
        change_points = filter_evidence_change_points(raw_change_points, config.analysis)
        timer.record("changepoint")

        drift, baseline_curve, vel_tuples, ai_conv = _load_drift_signals(
            slug,
            author.id,
            paths,
            config,
            exploratory=exploratory,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
        )
        timer.record("drift")

        timestamps = timestamps_from_frame(df_author)
        all_tests = _run_hypothesis_tests_for_changepoints(
            df_author,
            timestamps,
            change_points,
            author.id,
            config.analysis,
        )
        all_tests.extend(
            _run_preregistered_split_tests(
                df_author,
                timestamps,
                author.id,
                config.analysis,
            )
        )
        timer.record("hypothesis_tests")

        prob = probability_trajectory_by_slug.get(slug)
        n_rankable = compute_n_rankable_features_per_family(all_tests)
        convergence_windows = compute_convergence_scores(
            ConvergenceInput.from_settings(
                change_points,
                vel_tuples,
                baseline_curve,
                config,
                ai_convergence_curve=ai_conv,
                probability_trajectory=prob,
                n_rankable_per_family=n_rankable,
            )
        )
        timer.record("convergence")

        assembled = assemble_analysis_result(
            author.id,
            change_points,
            convergence_windows,
            drift,
            all_tests,
            config.analysis,
        )
        return assembled, change_points, convergence_windows, all_tests


def _load_drift_signals(
    slug: str,
    author_id: str,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    exploratory: bool = False,
    allow_pre_phase16_embeddings: bool = False,
) -> tuple[
    DriftScores | None,
    list[tuple[datetime, float]],
    list[tuple[str, float]],
    list[tuple[str, float]] | None,
]:
    """Load embeddings and run the per-author drift pipeline.

    Extracted from :func:`_run_per_author_analysis` (Phase 15 G3) to keep the
    parent function under the McCabe complexity ceiling once per-stage
    timing brackets and the early-out ``return None`` paths are factored
    in. Returns ``(drift, baseline_curve, vel_tuples, ai_conv)`` with
    permissive defaults (empty lists / ``None``) when embeddings are
    unavailable.
    """
    baseline_curve: list[tuple[datetime, float]] = []
    vel_tuples: list[tuple[str, float]] = []
    ai_conv: list[tuple[str, float]] | None = None
    drift: DriftScores | None = None

    try:
        pairs = load_article_embeddings(
            slug,
            paths,
            expected_revision=config.analysis.embedding_model_revision,
            exploratory=exploratory,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
        )
    except EmbeddingRevisionGateError:
        raise
    except (ValueError, OSError) as exc:
        logger.info("analysis: no embeddings for %s (%s)", slug, exc)
        pairs = []

    drift_res = compute_author_drift_pipeline(
        slug,
        author_id,
        pairs,
        config,
        paths=paths,
    )
    if drift_res is not None:
        drift = drift_res.drift_scores
        baseline_curve = drift_res.baseline_curve
        ai_conv = drift_res.ai_convergence
        vel_tuples = pair_months_with_velocities(drift_res.monthly_centroids, drift_res.velocities)
    return drift, baseline_curve, vel_tuples, ai_conv


def _resolve_targets_and_controls(
    config: ForensicsSettings,
    author_slug: str | None,
    *,
    compare_pair: tuple[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """Resolve the target and control slug lists for the comparison stage.

    When ``compare_pair`` is provided as ``(target_slug, control_slug)`` the
    explicit pair takes precedence over ``settings.authors`` role assignments
    so operators can pin a one-off comparison without editing ``config.toml``.
    """
    if compare_pair is not None:
        target_slug, control_slug = compare_pair
        return [target_slug], [control_slug]
    controls = [a.slug for a in config.authors if a.role == "control"]
    targets = [a.slug for a in config.authors if a.role == "target"]
    if author_slug:
        targets = [author_slug] if author_slug in targets else targets
    return targets, controls


def _validate_compare_artifact_hashes(
    targets: list[str],
    controls: list[str],
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
) -> None:
    author_slugs = sorted(set(targets) | set(controls))
    ok, msg = validate_analysis_result_config_hashes(config, paths.analysis_dir, author_slugs)
    if not ok:
        raise ValueError(msg)


def _run_target_control_comparisons(
    targets: list[str],
    controls: list[str],
    results: dict[str, AnalysisResult],
    *,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
) -> dict[str, Any]:
    comparison_payload: dict[str, Any] = {"targets": {}}
    active_targets = [target for target in targets if target in results]
    if active_targets:
        _validate_compare_artifact_hashes(active_targets, controls, paths, config)
    changepoints_memory = {slug: list(res.change_points) for slug, res in results.items()}
    for tid in active_targets:
        try:
            report = compare_target_to_controls(
                tid,
                controls,
                paths,
                settings=config,
                changepoints_memory=changepoints_memory,
            )
            comparison_payload["targets"][tid] = report
        except (ValueError, OSError) as exc:
            logger.warning("analysis: comparison failed for %s (%s)", tid, exc)
    return comparison_payload


def _merge_run_metadata(
    paths: AnalysisArtifactPaths,
    results: dict[str, AnalysisResult],
    comparison_payload: dict[str, Any],
) -> None:
    meta_path = paths.run_metadata_json()
    if meta_path.is_file():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    else:
        prev = {}
    # Phase 15 H2 — sort top-level lists for parallel/serial byte-identity.
    prev.update(
        {
            "full_analysis_authors": sorted(results.keys()),
            "comparison_targets": sorted(comparison_payload["targets"].keys()),
            "completed_at": datetime.now(UTC).isoformat(),
        }
    )
    write_json_artifact(meta_path, prev)


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


def assemble_analysis_result(
    author_id: str,
    change_points: list[ChangePoint],
    convergence_windows: list,
    drift_scores: DriftScores | None,
    hypothesis_tests: list,
    config: AnalysisConfig,
) -> AnalysisResult:
    """Build ``AnalysisResult`` with a short deterministic hash of analysis settings."""
    config_hash = compute_model_config_hash(config, length=16, round_trip=True)
    return AnalysisResult(
        author_id=author_id,
        run_id=str(uuid4()),
        run_timestamp=datetime.now(UTC),
        config_hash=config_hash,
        change_points=change_points,
        convergence_windows=convergence_windows,
        drift_scores=drift_scores,
        hypothesis_tests=hypothesis_tests,
        era_classification=classify_ai_marker_era(change_points),
    )


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
        ctx = multiprocessing.get_context(mp_context) if mp_context else None
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

        if results:
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

    return results, per_author_timings


def _author_result_current(
    paths: AnalysisArtifactPaths, config: ForensicsSettings, slug: str
) -> bool:
    path = paths.result_json(slug)
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    expected = compute_model_config_hash(config.analysis, length=16, round_trip=True)
    return payload.get("config_hash") == expected


def _stale_author_slugs(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    author_slug: str | None,
) -> list[str]:
    if author_slug is not None:
        return [author_slug]
    configured = [author.slug for author in config.authors]
    if all(_author_result_current(paths, config, slug) for slug in configured):
        return []
    # Hypothesis-test correction is global across authors, so a mixed current/stale
    # cohort must be recomputed together to avoid FDR denominator drift.
    return configured


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
        isolated_outputs = []
        for slug in slugs:
            isolated = _isolated_author_worker(
                slug,
                paths,
                config,
                probability_trajectory_by_slug,
                run_id,
                exploratory,
                allow_pre_phase16_embeddings,
            )
            if isolated is not None:
                isolated_outputs.append(isolated)
        return isolated_outputs
    isolated_outputs: list[IsolatedAuthorAnalysis] = []
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
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
        for future in as_completed(future_to_slug):
            slug = future_to_slug[future]
            isolated = future.result()
            if isolated is None:
                logger.warning("analysis-refresh: skipped %s", slug)
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
    """Refresh stale configured authors through isolated parallel author directories."""
    run_id = str(uuid4())
    slugs = _stale_author_slugs(paths, config, author_slug)
    workers = _resolve_parallel_refresh_workers(config, max_workers)
    logger.info(
        "analysis-refresh: refreshing %d stale author(s) with %d worker(s)",
        len(slugs),
        workers,
    )
    prob_map = probability_trajectory_by_slug or {}
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


def run_compare_only(
    config: ForensicsSettings,
    *,
    paths: AnalysisArtifactPaths,
    author_slug: str | None = None,
    compare_pair: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Regenerate ``comparison_report.json`` from on-disk artifacts.

    When ``compare_pair`` is supplied as ``(target_slug, control_slug)`` the
    explicit pair takes precedence over both ``author_slug`` and the
    configured author roles, so operators can pin a one-off comparison
    without editing ``config.toml``.

    When ``author_slug`` is provided (and ``compare_pair`` is not), the
    caller always wants that single author compared even if it isn't in the
    configured target list (matches the pre-Phase-13 CLI contract). A warning
    is logged so the ambiguity surfaces in the operator's logs.
    """
    if compare_pair is not None:
        targets, controls = _resolve_targets_and_controls(
            config,
            author_slug=None,
            compare_pair=compare_pair,
        )
    else:
        targets, controls = _resolve_targets_and_controls(config, author_slug)
        if author_slug and author_slug not in targets:
            logger.warning(
                "compare-only: author_slug=%r is not a configured target; "
                "forcing single-slug comparison (controls are still loaded from config)",
                author_slug,
            )
            targets = [author_slug]
    _validate_compare_artifact_hashes(targets, controls, paths, config)
    out: dict[str, Any] = {"targets": {}}
    for tid in targets:
        try:
            out["targets"][tid] = compare_target_to_controls(
                tid,
                controls,
                paths,
                settings=config,
            )
        except (ValueError, OSError) as exc:
            logger.warning("compare-only: failed for %s (%s)", tid, exc)
    write_json_artifact(paths.comparison_report_json(), out)
    return out
