"""Target vs control author comparisons and editorial attribution (Phase 7)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from scipy import stats

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS, analyze_author_feature_changepoints
from forensics.analysis.convergence import compute_convergence_scores
from forensics.analysis.drift import (
    compute_baseline_similarity_curve,
    compute_monthly_centroids,
    load_article_embeddings,
    track_centroid_velocity,
)
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import ChangePoint, ConvergenceWindow, DriftScores
from forensics.storage.parquet import read_features
from forensics.storage.repository import Repository, init_db
from forensics.utils.datetime import parse_datetime

logger = logging.getLogger(__name__)


def _intervals_overlap_date(a0, a1, b0, b1) -> bool:
    return a0 <= b1 and b0 <= a1


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
                if _intervals_overlap_date(tw.start_date, tw.end_date, cw.start_date, cw.end_date):
                    agree += 1
                    break
        frac = agree / float(len(control_ids))
        scores.append(1.0 - frac)
    return float(np.mean(scores)) if scores else 0.5


def _load_feature_frame(features_path: Path) -> pl.DataFrame:
    df = read_features(features_path)
    if "timestamp" not in df.columns:
        msg = f"features parquet missing timestamp: {features_path}"
        raise ValueError(msg)
    return df.sort("timestamp")


def _numeric_feature_columns(df: pl.DataFrame) -> list[str]:
    return [c for c in PELT_FEATURE_COLUMNS if c in df.columns]


def compare_target_to_controls(
    target_id: str,
    control_ids: list[str],
    features_dir: Path,
    db_path: Path,
    *,
    settings: ForensicsSettings,
    analysis_dir: Path,
    embeddings_dir: Path,
    project_root: Path,
) -> dict[str, Any]:
    """Two-sample tests (target vs pooled controls) plus cached change-point / drift summaries."""
    init_db(db_path)
    repo = Repository(db_path)

    target_author = repo.get_author_by_slug(target_id)
    if target_author is None:
        msg = f"Unknown target slug: {target_id}"
        raise ValueError(msg)

    target_path = features_dir / f"{target_id}.parquet"
    if not target_path.is_file():
        msg = f"Missing features for target: {target_path}"
        raise ValueError(msg)
    df_t = _load_feature_frame(target_path).filter(pl.col("author_id") == target_author.id)
    if df_t.is_empty():
        df_t = _load_feature_frame(target_path)

    control_frames: list[pl.DataFrame] = []
    for slug in control_ids:
        au = repo.get_author_by_slug(slug)
        if au is None:
            logger.warning("compare: skip unknown control slug=%s", slug)
            continue
        p = features_dir / f"{slug}.parquet"
        if not p.is_file():
            logger.warning("compare: skip missing features slug=%s", slug)
            continue
        dfc = _load_feature_frame(p).filter(pl.col("author_id") == au.id)
        if dfc.is_empty():
            dfc = _load_feature_frame(p)
        control_frames.append(dfc)

    pooled = pl.concat(control_frames) if control_frames else pl.DataFrame()

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

    control_change_points: dict[str, list[ChangePoint]] = {}
    control_drift_scores: dict[str, DriftScores | None] = {}
    control_windows: dict[str, list[ConvergenceWindow]] = {}

    for slug in control_ids:
        cp_json = analysis_dir / f"{slug}_changepoints.json"
        if cp_json.is_file():
            raw = json.loads(cp_json.read_text(encoding="utf-8"))
            control_change_points[slug] = [ChangePoint.model_validate(x) for x in raw]
        else:
            au = repo.get_author_by_slug(slug)
            p = features_dir / f"{slug}.parquet"
            if au is not None and p.is_file():
                dfc = _load_feature_frame(p).filter(pl.col("author_id") == au.id)
                if dfc.is_empty():
                    dfc = _load_feature_frame(p)
                control_change_points[slug] = analyze_author_feature_changepoints(
                    dfc, author_id=au.id, settings=settings
                )
            else:
                control_change_points[slug] = []

        drift_path = analysis_dir / f"{slug}_drift.json"
        if drift_path.is_file():
            raw_drift = drift_path.read_text(encoding="utf-8")
            control_drift_scores[slug] = DriftScores.model_validate_json(raw_drift)
        else:
            control_drift_scores[slug] = None

        curve_path = analysis_dir / f"{slug}_baseline_curve.json"
        baseline_curve: list = []
        if curve_path.is_file():
            for row in json.loads(curve_path.read_text(encoding="utf-8")):
                ts = parse_datetime(row["published_at"])
                baseline_curve.append((ts, float(row["similarity"])))

        cps = control_change_points[slug]
        ds = control_drift_scores[slug]
        if ds and ds.monthly_centroid_velocities:
            months = []
            npz_path = analysis_dir / f"{slug}_centroids.npz"
            if npz_path.is_file():
                data = np.load(npz_path)
                months = [str(x) for x in data["months"].tolist()]
            if len(months) >= 2:
                vel_tuples = list(zip(months[1:], ds.monthly_centroid_velocities, strict=False))
            else:
                vel_tuples = [(f"m{i}", v) for i, v in enumerate(ds.monthly_centroid_velocities)]
        else:
            vel_tuples = []
            try:
                pairs = load_article_embeddings(
                    slug,
                    embeddings_dir,
                    db_path,
                    project_root=project_root,
                )
                if len(pairs) >= 2:
                    monthly = compute_monthly_centroids(pairs)
                    vels = track_centroid_velocity(monthly)
                    vel_tuples = [(monthly[i + 1][0], vels[i]) for i in range(len(vels))]
                    baseline_curve = compute_baseline_similarity_curve(pairs)
            except (ValueError, OSError) as exc:
                logger.debug("compare: no embeddings for %s (%s)", slug, exc)

        control_windows[slug] = compute_convergence_scores(
            cps,
            vel_tuples,
            baseline_curve,
        )

    target_cp_path = analysis_dir / f"{target_id}_changepoints.json"
    if target_cp_path.is_file():
        raw_cp = json.loads(target_cp_path.read_text(encoding="utf-8"))
        target_cps = [ChangePoint.model_validate(x) for x in raw_cp]
    else:
        target_cps = analyze_author_feature_changepoints(
            df_t,
            author_id=target_author.id,
            settings=settings,
        )

    target_curve: list = []
    tc_path = analysis_dir / f"{target_id}_baseline_curve.json"
    if tc_path.is_file():
        for row in json.loads(tc_path.read_text(encoding="utf-8")):
            target_curve.append((parse_datetime(row["published_at"]), float(row["similarity"])))

    target_vel: list[tuple[str, float]] = []
    td = analysis_dir / f"{target_id}_drift.json"
    if td.is_file():
        tdrift = DriftScores.model_validate_json(td.read_text(encoding="utf-8"))
        npz_path = analysis_dir / f"{target_id}_centroids.npz"
        if tdrift.monthly_centroid_velocities and npz_path.is_file():
            data = np.load(npz_path)
            months = [str(x) for x in data["months"].tolist()]
            if len(months) >= 2:
                target_vel = list(zip(months[1:], tdrift.monthly_centroid_velocities, strict=False))
    if not target_vel:
        try:
            pairs = load_article_embeddings(
                target_id,
                embeddings_dir,
                db_path,
                project_root=project_root,
            )
            if len(pairs) >= 2:
                monthly = compute_monthly_centroids(pairs)
                vels = track_centroid_velocity(monthly)
                target_vel = [(monthly[i + 1][0], vels[i]) for i in range(len(vels))]
                if not target_curve:
                    target_curve = compute_baseline_similarity_curve(pairs)
        except (ValueError, OSError):
            pass

    target_windows = compute_convergence_scores(target_cps, target_vel, target_curve)
    editorial_vs_author_signal = compute_signal_attribution(target_windows, control_windows)

    ccp_out = {
        k: [cp.model_dump(mode="json") for cp in v] for k, v in control_change_points.items()
    }
    return {
        "feature_comparisons": feature_comparisons,
        "control_change_points": ccp_out,
        "control_drift_scores": {
            k: (v.model_dump(mode="json") if v else None) for k, v in control_drift_scores.items()
        },
        "editorial_vs_author_signal": editorial_vs_author_signal,
    }
