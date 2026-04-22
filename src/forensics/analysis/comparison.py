"""Target vs control author comparisons and editorial attribution (Phase 7)."""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import polars as pl
from scipy import stats

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS, analyze_author_feature_changepoints
from forensics.analysis.convergence import compute_convergence_scores
from forensics.analysis.drift import (
    compute_baseline_similarity_curve,
    compute_monthly_centroids,
    load_article_embeddings,
    track_centroid_velocity,
)
from forensics.analysis.utils import intervals_overlap, load_feature_frame_for_author
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import ChangePoint, ConvergenceWindow, DriftScores
from forensics.models.author import Author
from forensics.storage.repository import Repository
from forensics.utils.datetime import parse_datetime

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


def _load_or_compute_changepoints(
    slug: str,
    repo: Repository,
    paths: AnalysisArtifactPaths,
    settings: ForensicsSettings,
    *,
    feature_frame: pl.DataFrame | None = None,
) -> list[ChangePoint]:
    cp_json = paths.changepoints_json(slug)
    if cp_json.is_file():
        raw = json.loads(cp_json.read_text(encoding="utf-8"))
        return [ChangePoint.model_validate(x) for x in raw]
    au = repo.get_author_by_slug(slug)
    p = paths.features_dir / f"{slug}.parquet"
    if au is None or not p.is_file():
        return []
    dfc = feature_frame
    if dfc is None:
        dfc = load_feature_frame_for_author(paths.features_dir, slug, au.id)
    if dfc is None:
        return []
    return analyze_author_feature_changepoints(dfc, author_id=au.id, settings=settings)


def _velocity_and_baseline_for_slug(
    slug: str,
    repo: Repository,
    paths: AnalysisArtifactPaths,
    settings: ForensicsSettings,
) -> tuple[list[tuple[str, float]], list[tuple[Any, float]]]:
    """Return ``(vel_tuples, baseline_curve)`` from disk or by recomputing from embeddings."""
    drift_path = paths.drift_json(slug)
    baseline_curve: list = []
    vel_tuples: list[tuple[str, float]] = []

    curve_path = paths.baseline_curve_json(slug)
    if curve_path.is_file():
        for row in json.loads(curve_path.read_text(encoding="utf-8")):
            ts = parse_datetime(row["published_at"])
            baseline_curve.append((ts, float(row["similarity"])))

    ds: DriftScores | None = None
    if drift_path.is_file():
        ds = DriftScores.model_validate_json(drift_path.read_text(encoding="utf-8"))

    if ds and ds.monthly_centroid_velocities:
        npz_path = paths.centroids_npz(slug)
        months: list[str] = []
        if npz_path.is_file():
            data = np.load(npz_path)
            months = [str(x) for x in data["months"].tolist()]
        if len(months) >= 2:
            vel_tuples = list(zip(months[1:], ds.monthly_centroid_velocities, strict=False))
        else:
            vel_tuples = [(f"m{i}", v) for i, v in enumerate(ds.monthly_centroid_velocities)]
    else:
        try:
            pairs = load_article_embeddings(slug, paths)
            if len(pairs) >= 2:
                monthly = compute_monthly_centroids(pairs)
                vels = track_centroid_velocity(monthly)
                vel_tuples = [(monthly[i + 1][0], vels[i]) for i in range(len(vels))]
                if not baseline_curve:
                    baseline_curve = compute_baseline_similarity_curve(
                        pairs,
                        baseline_count=settings.analysis.baseline_embedding_count,
                    )
        except (ValueError, OSError) as exc:
            logger.debug("compare: no embeddings for %s (%s)", slug, exc)

    return vel_tuples, baseline_curve


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
        tvals = df_t[col].cast(pl.Float64, strict=False).drop_nulls().to_numpy()
        if pooled.is_empty() or col not in pooled.columns:
            continue
        cvals = pooled[col].cast(pl.Float64, strict=False).drop_nulls().to_numpy()
        if tvals.size < 3 or cvals.size < 3:
            continue
        t_stat, p_two = stats.ttest_ind(tvals, cvals, equal_var=False)
        feature_comparisons[col] = {
            "all": {
                "t_stat": float(t_stat),
                "p_value": float(p_two),
                "target_mean": float(np.mean(tvals)),
                "control_mean": float(np.mean(cvals)),
            }
        }
    return feature_comparisons


def _summarize_control_authors(
    control_ids: list[str],
    repo: Repository,
    paths: AnalysisArtifactPaths,
    settings: ForensicsSettings,
    control_feature_frames: dict[str, pl.DataFrame],
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
        )

        drift_path = paths.drift_json(slug)
        if drift_path.is_file():
            raw_drift = drift_path.read_text(encoding="utf-8")
            control_drift_scores[slug] = DriftScores.model_validate_json(raw_drift)
        else:
            control_drift_scores[slug] = None

        vel_tuples, baseline_curve = _velocity_and_baseline_for_slug(
            slug,
            repo,
            paths,
            settings,
        )
        cps = control_change_points[slug]
        control_windows[slug] = compute_convergence_scores(
            cps,
            vel_tuples,
            baseline_curve,
            settings=settings,
        )
    return control_change_points, control_drift_scores, control_windows


def _editorial_signal_for_target(
    target_id: str,
    target_author: Author,
    df_t: pl.DataFrame,
    repo: Repository,
    paths: AnalysisArtifactPaths,
    settings: ForensicsSettings,
    control_windows: dict[str, list[ConvergenceWindow]],
) -> float:
    target_cp_path = paths.changepoints_json(target_id)
    if target_cp_path.is_file():
        raw_cp = json.loads(target_cp_path.read_text(encoding="utf-8"))
        target_cps = [ChangePoint.model_validate(x) for x in raw_cp]
    else:
        target_cps = analyze_author_feature_changepoints(
            df_t,
            author_id=target_author.id,
            settings=settings,
        )

    target_vel, target_curve = _velocity_and_baseline_for_slug(
        target_id,
        repo,
        paths,
        settings,
    )

    target_windows = compute_convergence_scores(
        target_cps,
        target_vel,
        target_curve,
        settings=settings,
    )
    return compute_signal_attribution(target_windows, control_windows)


def compare_target_to_controls(
    target_id: str,
    control_ids: list[str],
    paths: AnalysisArtifactPaths,
    *,
    settings: ForensicsSettings,
) -> dict[str, Any]:
    """Two-sample tests (target vs pooled controls) plus cached change-point / drift summaries."""
    with Repository(paths.db_path) as repo:
        target_author, df_t = _load_target_author_and_frame(repo, paths, target_id)
        pooled, control_feature_frames = _load_control_frames_and_pooled(
            repo, paths, control_ids
        )
        feature_comparisons = _two_sample_feature_comparisons(df_t, pooled)
        control_change_points, control_drift_scores, control_windows = _summarize_control_authors(
            control_ids,
            repo,
            paths,
            settings,
            control_feature_frames,
        )
        editorial_vs_author_signal = _editorial_signal_for_target(
            target_id,
            target_author,
            df_t,
            repo,
            paths,
            settings,
            control_windows,
        )

        ccp_out = {
            k: [cp.model_dump(mode="json") for cp in v] for k, v in control_change_points.items()
        }
        return {
            "feature_comparisons": feature_comparisons,
            "control_change_points": ccp_out,
            "control_drift_scores": {
                k: (v.model_dump(mode="json") if v else None)
                for k, v in control_drift_scores.items()
            },
            "editorial_vs_author_signal": editorial_vs_author_signal,
        }
