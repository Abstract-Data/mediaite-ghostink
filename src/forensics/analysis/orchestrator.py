"""Phase 7 orchestration: assemble ``AnalysisResult`` and run full multi-author analysis."""

from __future__ import annotations

import hashlib
import json
import logging
from bisect import bisect_left
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import numpy as np
import polars as pl

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.changepoint import (
    analyze_author_feature_changepoints,
)
from forensics.analysis.comparison import compare_target_to_controls
from forensics.analysis.convergence import ProbabilityTrajectory, compute_convergence_scores
from forensics.analysis.drift import compute_author_drift_pipeline, load_article_embeddings
from forensics.analysis.statistics import (
    apply_correction,
    filter_by_effect_size,
    run_hypothesis_tests,
)
from forensics.analysis.utils import pair_months_with_velocities
from forensics.config.settings import AnalysisConfig, ForensicsSettings
from forensics.models.analysis import AnalysisResult, ChangePoint, DriftScores
from forensics.storage.json_io import write_json_artifact
from forensics.storage.parquet import load_feature_frame_sorted
from forensics.storage.repository import Repository
from forensics.utils.datetime import parse_datetime
from forensics.utils.provenance import write_corpus_custody

logger = logging.getLogger(__name__)


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
    write_json_artifact(paths.changepoints_json(slug), change_points)
    write_json_artifact(paths.convergence_json(slug), convergence_windows)
    write_json_artifact(paths.result_json(slug), assembled)
    write_json_artifact(paths.hypothesis_tests_json(slug), all_tests)


def _run_hypothesis_tests_for_changepoints(
    df_author: pl.DataFrame,
    timestamps: list[datetime],
    change_points: list[ChangePoint],
    author_id: str,
    analysis_cfg: AnalysisConfig,
) -> list:
    all_tests: list = []
    for cp in change_points:
        if cp.feature_name not in df_author.columns:
            continue
        raw = df_author[cp.feature_name].cast(pl.Float64, strict=False).to_numpy()
        med = float(np.nanmedian(raw[np.isfinite(raw)])) if np.any(np.isfinite(raw)) else 0.0
        raw = np.nan_to_num(raw, nan=med)
        series = [float(x) for x in raw]
        if len(series) < 6 or len(series) != len(timestamps):
            continue
        bidx = _breakpoint_index(timestamps, cp.timestamp)
        all_tests.extend(
            run_hypothesis_tests(
                series,
                bidx,
                cp.feature_name,
                author_id,
                n_bootstrap=analysis_cfg.bootstrap_iterations,
            )
        )
    apply_correction(
        all_tests,
        method=analysis_cfg.multiple_comparison_method,
        alpha=analysis_cfg.significance_threshold,
    )
    filter_by_effect_size(
        all_tests,
        analysis_cfg.effect_size_threshold,
        alpha=analysis_cfg.significance_threshold,
    )
    return all_tests


def _run_per_author_analysis(
    slug: str,
    repo: Repository,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory],
) -> tuple[AnalysisResult, list[ChangePoint], list, list] | None:
    """Changepoint, drift, convergence, and hypothesis testing for one author slug."""
    author = repo.get_author_by_slug(slug)
    if author is None:
        logger.warning("analysis: unknown slug=%s", slug)
        return None
    feat_path = paths.features_parquet(slug)
    if not feat_path.is_file():
        logger.warning("analysis: skip %s (missing %s)", slug, feat_path)
        return None

    df = load_feature_frame_sorted(feat_path)
    df_author = df.filter(pl.col("author_id") == author.id)
    if df_author.is_empty():
        df_author = df

    change_points = analyze_author_feature_changepoints(
        df_author,
        author_id=author.id,
        settings=config,
    )

    baseline_curve: list[tuple[datetime, float]] = []
    vel_tuples: list[tuple[str, float]] = []
    ai_conv: list[tuple[str, float]] | None = None
    drift: DriftScores | None = None

    try:
        pairs = load_article_embeddings(slug, paths)
    except (ValueError, OSError) as exc:
        logger.info("analysis: no embeddings for %s (%s)", slug, exc)
        pairs = []

    drift_res = compute_author_drift_pipeline(
        slug,
        author.id,
        pairs,
        config,
        paths=paths,
    )
    if drift_res is not None:
        drift = drift_res.drift_scores
        baseline_curve = drift_res.baseline_curve
        ai_conv = drift_res.ai_convergence
        vel_tuples = pair_months_with_velocities(drift_res.monthly_centroids, drift_res.velocities)

    prob = probability_trajectory_by_slug.get(slug)
    ac = config.analysis
    convergence_windows = compute_convergence_scores(
        change_points,
        vel_tuples,
        baseline_curve,
        ai_convergence_curve=ai_conv,
        probability_trajectory=prob,
        settings=config,
        use_permutation=ac.convergence_use_permutation,
        n_permutations=ac.convergence_permutation_iterations,
        permutation_seed=ac.convergence_permutation_seed,
    )

    ts_list = df_author["timestamp"].to_list()
    timestamps = [parse_datetime(t) for t in ts_list]

    all_tests = _run_hypothesis_tests_for_changepoints(
        df_author,
        timestamps,
        change_points,
        author.id,
        config.analysis,
    )

    assembled = assemble_analysis_result(
        author.id,
        change_points,
        convergence_windows,
        drift,
        all_tests,
        config.analysis,
    )
    return assembled, change_points, convergence_windows, all_tests


def _resolve_targets_and_controls(
    config: ForensicsSettings,
    author_slug: str | None,
) -> tuple[list[str], list[str]]:
    controls = [a.slug for a in config.authors if a.role == "control"]
    targets = [a.slug for a in config.authors if a.role == "target"]
    if author_slug:
        targets = [author_slug] if author_slug in targets else targets
    return targets, controls


def _run_target_control_comparisons(
    targets: list[str],
    controls: list[str],
    results: dict[str, AnalysisResult],
    *,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
) -> dict[str, Any]:
    comparison_payload: dict[str, Any] = {"targets": {}}
    for tid in targets:
        if tid not in results:
            continue
        try:
            report = compare_target_to_controls(
                tid,
                controls,
                paths,
                settings=config,
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
    prev.update(
        {
            "full_analysis_authors": list(results.keys()),
            "comparison_targets": list(comparison_payload["targets"].keys()),
            "completed_at": datetime.now(UTC).isoformat(),
        }
    )
    write_json_artifact(meta_path, prev)


def assemble_analysis_result(
    author_id: str,
    change_points: list[ChangePoint],
    convergence_windows: list,
    drift_scores: DriftScores | None,
    hypothesis_tests: list,
    config: AnalysisConfig,
) -> AnalysisResult:
    """Build ``AnalysisResult`` with a short deterministic hash of analysis settings."""
    payload = config.model_dump(mode="json", round_trip=True)
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    config_hash = hashlib.sha256(raw).hexdigest()[:16]
    return AnalysisResult(
        author_id=author_id,
        run_id=str(uuid4()),
        run_timestamp=datetime.now(UTC),
        config_hash=config_hash,
        change_points=change_points,
        convergence_windows=convergence_windows,
        drift_scores=drift_scores,
        hypothesis_tests=hypothesis_tests,
    )


async def run_full_analysis(
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    author_slug: str | None = None,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory] | None = None,
) -> dict[str, AnalysisResult]:
    """Run changepoint + drift + convergence + hypothesis tests; write JSON artifacts."""
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)

    slugs = [author_slug] if author_slug else [a.slug for a in config.authors]
    prob_map = probability_trajectory_by_slug or {}

    results: dict[str, AnalysisResult] = {}

    with Repository(paths.db_path) as repo:
        for slug in slugs:
            per_author = _run_per_author_analysis(
                slug,
                repo,
                paths,
                config,
                probability_trajectory_by_slug=prob_map,
            )
            if per_author is None:
                continue
            assembled, change_points, convergence_windows, all_tests = per_author
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

    write_corpus_custody(paths.db_path, paths.analysis_dir)

    return results


def run_compare_only(
    config: ForensicsSettings,
    *,
    paths: AnalysisArtifactPaths,
    author_slug: str | None = None,
) -> dict[str, Any]:
    """Regenerate ``comparison_report.json`` from on-disk artifacts."""
    targets, controls = _resolve_targets_and_controls(config, author_slug)
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
