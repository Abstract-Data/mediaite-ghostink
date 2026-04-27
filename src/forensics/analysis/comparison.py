"""Target vs control author comparisons and editorial attribution."""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import polars as pl
from scipy import stats

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS, analyze_author_feature_changepoints
from forensics.analysis.convergence import ConvergenceInput, compute_convergence_scores
from forensics.analysis.drift import load_drift_summary
from forensics.analysis.evidence import filter_evidence_change_points
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import ChangePoint, ConvergenceWindow, DriftScores
from forensics.models.author import Author
from forensics.paths import AnalysisArtifactPaths, intervals_overlap, load_feature_frame_for_author
from forensics.storage.repository import Repository
from forensics.utils.datetime import timestamps_from_frame

logger = logging.getLogger(__name__)


def compute_signal_attribution(
    target_change_windows: list[ConvergenceWindow],
    control_change_windows: dict[str, list[ConvergenceWindow]],
) -> float:
    """0 = outlet-wide (controls agree), 1 = author-specific (controls rarely agree)."""
    if not target_change_windows:
        return 0.5
    control_ids = list(control_change_windows.keys())
    if not control_ids:
        return 1.0

    scores: list[float] = []
    for tw in target_change_windows:
        agree = 0
        for cid in control_ids:
            for cw in control_change_windows[cid]:
                if intervals_overlap(tw.start_date, tw.end_date, cw.start_date, cw.end_date):
                    agree += 1
                    break
        frac = agree / float(len(control_ids))
        scores.append(1.0 - frac)
    return float(np.mean(scores)) if scores else 0.5


def _numeric_feature_columns(df: pl.DataFrame) -> list[str]:
    return [c for c in PELT_FEATURE_COLUMNS if c in df.columns]


def _finite_values(df: pl.DataFrame, col: str) -> np.ndarray:
    vals = df[col].cast(pl.Float64, strict=False).drop_nulls().to_numpy()
    return vals[np.isfinite(vals)]


def _feature_coverage_diagnostics(df: pl.DataFrame, columns: list[str]) -> dict[str, list[str]]:
    diagnostics = {
        "all_zero": [],
        "all_null": [],
        "all_nan": [],
        "has_non_finite": [],
    }
    for col in columns:
        if col not in df.columns:
            continue
        series = df[col].cast(pl.Float64, strict=False)
        values = series.drop_nulls().to_numpy()
        if len(values) == 0:
            diagnostics["all_null"].append(col)
            continue
        finite = values[np.isfinite(values)]
        if len(finite) == 0 and np.isnan(values).all():
            diagnostics["all_nan"].append(col)
            continue
        if len(finite) != len(values):
            diagnostics["has_non_finite"].append(col)
        if len(finite) > 0 and np.all(finite == 0.0):
            diagnostics["all_zero"].append(col)
    return diagnostics


def _load_or_compute_changepoints(
    slug: str,
    repo: Repository,
    paths: AnalysisArtifactPaths,
    settings: ForensicsSettings,
    *,
    feature_frame: pl.DataFrame | None = None,
    changepoints_memory: dict[str, list[ChangePoint]] | None = None,
) -> list[ChangePoint]:
    if changepoints_memory is not None and slug in changepoints_memory:
        return filter_evidence_change_points(changepoints_memory[slug], settings.analysis)
    cp_json = paths.changepoints_json(slug)
    if cp_json.is_file():
        raw = json.loads(cp_json.read_text(encoding="utf-8"))
        return filter_evidence_change_points(
            [ChangePoint.model_validate(x) for x in raw],
            settings.analysis,
        )
    au = repo.get_author_by_slug(slug)
    p = paths.features_dir / f"{slug}.parquet"
    if au is None or not p.is_file():
        return []
    dfc = feature_frame
    if dfc is None:
        dfc = load_feature_frame_for_author(paths.features_dir, slug, au.id)
    if dfc is None:
        return []
    return filter_evidence_change_points(
        analyze_author_feature_changepoints(dfc, author_id=au.id, settings=settings),
        settings.analysis,
    )


def _load_target_author_and_frame(
    repo: Repository,
    paths: AnalysisArtifactPaths,
    target_id: str,
) -> tuple[Author, pl.DataFrame]:
    target_author = repo.get_author_by_slug(target_id)
    if target_author is None:
        msg = f"Unknown target slug: {target_id}"
        raise ValueError(msg)
    target_path = paths.features_parquet(target_id)
    if not target_path.is_file():
        msg = f"Missing features for target: {target_path}"
        raise ValueError(msg)
    df_t = load_feature_frame_for_author(paths.features_dir, target_id, target_author.id)
    if df_t is None:
        msg = f"Missing features for target: {target_path}"
        raise ValueError(msg)
    return target_author, df_t


def _load_control_frames_and_pooled(
    repo: Repository,
    paths: AnalysisArtifactPaths,
    control_ids: list[str],
) -> tuple[pl.DataFrame, dict[str, pl.DataFrame]]:
    control_frames: list[pl.DataFrame] = []
    control_feature_frames: dict[str, pl.DataFrame] = {}
    for slug in control_ids:
        au = repo.get_author_by_slug(slug)
        if au is None:
            logger.warning("compare: skip unknown control slug=%s", slug)
            continue
        dfc = load_feature_frame_for_author(paths.features_dir, slug, au.id)
        if dfc is None:
            logger.warning("compare: skip missing features slug=%s", slug)
            continue
        control_frames.append(dfc)
        control_feature_frames[slug] = dfc
    pooled = pl.concat(control_frames) if control_frames else pl.DataFrame()
    return pooled, control_feature_frames


def _two_sample_feature_comparisons(
    df_t: pl.DataFrame,
    pooled: pl.DataFrame,
) -> dict[str, dict[str, Any]]:
    feature_comparisons: dict[str, dict[str, Any]] = {}
    cols = _numeric_feature_columns(df_t)
    for col in cols:
        tvals = _finite_values(df_t, col)
        if pooled.is_empty() or col not in pooled.columns:
            continue
        cvals = _finite_values(pooled, col)
        if tvals.size < 3 or cvals.size < 3:
            continue
        t_stat, p_two = stats.ttest_ind(tvals, cvals, equal_var=False)
        if not np.isfinite(t_stat) or not np.isfinite(p_two):
            continue
        feature_comparisons[col] = {
            "all": {
                "t_stat": float(t_stat),
                "p_value": float(p_two),
                "target_mean": float(np.mean(tvals)),
                "control_mean": float(np.mean(cvals)),
            }
        }
    return feature_comparisons


def _comparison_feature_coverage(
    df_t: pl.DataFrame,
    pooled: pl.DataFrame,
    control_feature_frames: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    cols = sorted(set(_numeric_feature_columns(df_t)) | set(_numeric_feature_columns(pooled)))
    return {
        "target": _feature_coverage_diagnostics(df_t, cols),
        "pooled_controls": _feature_coverage_diagnostics(pooled, cols),
        "controls": {
            slug: _feature_coverage_diagnostics(frame, cols)
            for slug, frame in control_feature_frames.items()
        },
    }


def _summarize_control_authors(
    control_ids: list[str],
    repo: Repository,
    paths: AnalysisArtifactPaths,
    settings: ForensicsSettings,
    control_feature_frames: dict[str, pl.DataFrame],
    *,
    changepoints_memory: dict[str, list[ChangePoint]] | None = None,
) -> tuple[
    dict[str, list[ChangePoint]],
    dict[str, DriftScores | None],
    dict[str, list[ConvergenceWindow]],
]:
    control_change_points: dict[str, list[ChangePoint]] = {}
    control_drift_scores: dict[str, DriftScores | None] = {}
    control_windows: dict[str, list[ConvergenceWindow]] = {}

    for slug in control_ids:
        control_change_points[slug] = _load_or_compute_changepoints(
            slug,
            repo,
            paths,
            settings,
            feature_frame=control_feature_frames.get(slug),
            changepoints_memory=changepoints_memory,
        )

        drift_path = paths.drift_json(slug)
        if drift_path.is_file():
            raw_drift = drift_path.read_text(encoding="utf-8")
            control_drift_scores[slug] = DriftScores.model_validate_json(raw_drift)
        else:
            control_drift_scores[slug] = None

        summary = load_drift_summary(slug, paths, settings=settings)
        cps = control_change_points[slug]
        frame = control_feature_frames.get(slug)
        ts_ctrl = timestamps_from_frame(frame) if frame is not None else None
        control_windows[slug] = compute_convergence_scores(
            ConvergenceInput.from_settings(
                cps,
                summary.velocities,
                summary.baseline_curve,
                settings,
                article_timestamps=ts_ctrl,
            )
        )
    return control_change_points, control_drift_scores, control_windows


def _editorial_signal_for_target(
    target_id: str,
    target_author: Author,
    df_t: pl.DataFrame,
    paths: AnalysisArtifactPaths,
    settings: ForensicsSettings,
    control_windows: dict[str, list[ConvergenceWindow]],
    *,
    changepoints_memory: dict[str, list[ChangePoint]] | None = None,
) -> float:
    if changepoints_memory is not None and target_id in changepoints_memory:
        target_cps = filter_evidence_change_points(
            changepoints_memory[target_id], settings.analysis
        )
    else:
        target_cps = filter_evidence_change_points(
            _editorial_target_changepoints_disk_or_compute(
                target_id,
                target_author,
                df_t,
                paths,
                settings,
            ),
            settings.analysis,
        )
    summary = load_drift_summary(target_id, paths, settings=settings)

    target_windows = compute_convergence_scores(
        ConvergenceInput.from_settings(
            target_cps,
            summary.velocities,
            summary.baseline_curve,
            settings,
            article_timestamps=timestamps_from_frame(df_t),
        )
    )
    return compute_signal_attribution(target_windows, control_windows)


def _editorial_target_changepoints_disk_or_compute(
    target_id: str,
    target_author: Author,
    df_t: pl.DataFrame,
    paths: AnalysisArtifactPaths,
    settings: ForensicsSettings,
) -> list[ChangePoint]:
    target_cp_path = paths.changepoints_json(target_id)
    if target_cp_path.is_file():
        raw_cp = json.loads(target_cp_path.read_text(encoding="utf-8"))
        return [ChangePoint.model_validate(x) for x in raw_cp]
    return analyze_author_feature_changepoints(
        df_t,
        author_id=target_author.id,
        settings=settings,
    )


def compare_target_to_controls(
    target_id: str,
    control_ids: list[str],
    paths: AnalysisArtifactPaths,
    *,
    settings: ForensicsSettings,
    changepoints_memory: dict[str, list[ChangePoint]] | None = None,
) -> dict[str, Any]:
    """Two-sample tests (target vs pooled controls) plus cached change-point / drift summaries."""
    with Repository(paths.db_path) as repo:
        target_author, df_t = _load_target_author_and_frame(repo, paths, target_id)
        pooled, control_feature_frames = _load_control_frames_and_pooled(repo, paths, control_ids)
        feature_comparisons = _two_sample_feature_comparisons(df_t, pooled)
        feature_coverage = _comparison_feature_coverage(df_t, pooled, control_feature_frames)
        control_change_points, control_drift_scores, control_windows = _summarize_control_authors(
            control_ids,
            repo,
            paths,
            settings,
            control_feature_frames,
            changepoints_memory=changepoints_memory,
        )
        editorial_vs_author_signal = _editorial_signal_for_target(
            target_id,
            target_author,
            df_t,
            paths,
            settings,
            control_windows,
            changepoints_memory=changepoints_memory,
        )

        ccp_out = {
            k: [cp.model_dump(mode="json") for cp in v] for k, v in control_change_points.items()
        }
        return {
            "feature_comparisons": feature_comparisons,
            "feature_coverage_diagnostics": feature_coverage,
            "control_change_points": ccp_out,
            "control_drift_scores": {
                k: (v.model_dump(mode="json") if v else None)
                for k, v in control_drift_scores.items()
            },
            "editorial_vs_author_signal": editorial_vs_author_signal,
        }
