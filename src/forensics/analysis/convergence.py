"""Cross-pipeline convergence (Phase 7): stylometry, embedding drift, optional probability."""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import ChangePoint, ConvergenceWindow


def _month_key_to_range(key: str) -> tuple[date, date]:
    y_str, m_str = key.split("-", 1)
    y, mo = int(y_str), int(m_str)
    last = calendar.monthrange(y, mo)[1]
    return date(y, mo, 1), date(y, mo, last)


def _intervals_overlap(a0: date, a1: date, b0: date, b1: date) -> bool:
    return a0 <= b1 and b0 <= a1


@dataclass
class ProbabilityTrajectory:
    """Optional Phase 9 trajectory signals aligned by ``YYYY-MM`` month keys."""

    monthly_perplexity: list[tuple[str, float]]
    monthly_burstiness: list[tuple[str, float]]
    monthly_binoculars: list[tuple[str, float]] | None = None


def _months_touching_window(
    window_start: date, window_end: date, month_keys: Iterable[str]
) -> list[str]:
    out: list[str] = []
    for key in month_keys:
        m0, m1 = _month_key_to_range(key)
        if _intervals_overlap(window_start, window_end, m0, m1):
            out.append(key)
    return out


def compute_probability_pipeline_score(
    window_start: date,
    window_end: date,
    prob: ProbabilityTrajectory,
    *,
    settings: ForensicsSettings | None = None,
) -> float:
    """Composite 0–1 from perplexity drop, burstiness flattening, optional Binoculars."""
    parts: list[float] = []

    ppx = []
    for k, v in prob.monthly_perplexity:
        m0, m1 = _month_key_to_range(k)
        if _intervals_overlap(window_start, window_end, m0, m1):
            ppx.append(v)
    ppx_drop = 0.92 if settings is None else settings.analysis.convergence_perplexity_drop_ratio
    if len(ppx) >= 2:
        first, last = float(np.mean(ppx[: len(ppx) // 2])), float(np.mean(ppx[len(ppx) // 2 :]))
        if first > 1e-9 and last < first * ppx_drop:
            parts.append(1.0)
        elif first > 1e-9 and last < first:
            parts.append(0.5)
        else:
            parts.append(0.0)

    br = []
    for k, v in prob.monthly_burstiness:
        m0, m1 = _month_key_to_range(k)
        if _intervals_overlap(window_start, window_end, m0, m1):
            br.append(v)
    br_drop = 0.94 if settings is None else settings.analysis.convergence_burstiness_drop_ratio
    if len(br) >= 2:
        first_b, last_b = float(np.mean(br[: len(br) // 2])), float(np.mean(br[len(br) // 2 :]))
        if first_b > 1e-9 and last_b < first_b * br_drop:
            parts.append(1.0)
        elif first_b > 1e-9 and last_b < first_b:
            parts.append(0.5)
        else:
            parts.append(0.0)

    if prob.monthly_binoculars:
        bx = []
        for k, v in prob.monthly_binoculars:
            m0, m1 = _month_key_to_range(k)
            if _intervals_overlap(window_start, window_end, m0, m1):
                bx.append(v)
        if len(bx) >= 2:
            spread = float(np.std(bx, ddof=1)) if len(bx) > 2 else abs(bx[-1] - bx[0])
            parts.append(min(1.0, spread))

    if not parts:
        return 0.0
    return float(sum(parts) / len(parts))


def compute_convergence_scores(
    change_points: list[ChangePoint],
    centroid_velocities: list[tuple[str, float]],
    baseline_similarity_curve: list[tuple[datetime, float]],
    window_days: int = 90,
    min_feature_ratio: float = 0.6,
    *,
    total_feature_count: int | None = None,
    ai_convergence_curve: list[tuple[str, float]] | None = None,
    probability_trajectory: ProbabilityTrajectory | None = None,
    settings: ForensicsSettings | None = None,
) -> list[ConvergenceWindow]:
    """Quantify agreement between Pipeline A (stylometry) and Pipeline B (embeddings)."""
    if settings is not None:
        window_days = settings.analysis.convergence_window_days
        min_feature_ratio = settings.analysis.convergence_min_feature_ratio
    total = total_feature_count if total_feature_count is not None else len(PELT_FEATURE_COLUMNS)
    if total <= 0:
        return []

    vel_by_month = {m: v for m, v in centroid_velocities}
    vel_vals = np.asarray([v for _, v in centroid_velocities], dtype=float)
    v_mean = float(np.mean(vel_vals)) if vel_vals.size else 0.0
    v_std = float(np.std(vel_vals, ddof=1)) if vel_vals.size > 1 else 0.0
    v_thr = v_mean + 2.0 * v_std

    sim_by_date = []
    for dt, s in baseline_similarity_curve:
        dkey = dt.date() if isinstance(dt, datetime) else dt
        sim_by_date.append((dkey, s))

    ai_by_month = {m: s for m, s in ai_convergence_curve} if ai_convergence_curve else {}

    starts: set[date] = set()
    for cp in change_points:
        starts.add(cp.timestamp.date())
    if sim_by_date:
        starts.add(sim_by_date[0][0])
    if centroid_velocities:
        m0, _ = _month_key_to_range(centroid_velocities[0][0])
        starts.add(m0)

    if not starts:
        return []

    windows_out: list[ConvergenceWindow] = []
    seen: set[tuple[date, date]] = set()

    for start_d in sorted(starts):
        end_d = start_d + timedelta(days=window_days)
        key = (start_d, end_d)
        if key in seen:
            continue
        seen.add(key)

        feats_weights: dict[str, tuple[float, float]] = {}
        for cp in change_points:
            d = cp.timestamp.date()
            if start_d <= d <= end_d:
                w = max(float(cp.confidence), 1e-6)
                prev = feats_weights.get(cp.feature_name)
                if prev is None or w * abs(cp.effect_size_cohens_d) > prev[0] * abs(prev[1]):
                    feats_weights[cp.feature_name] = (w, float(cp.effect_size_cohens_d))

        features_converging = sorted(feats_weights.keys())
        ratio = len(features_converging) / float(total) if total else 0.0

        if features_converging:
            num = sum(w * d for w, d in feats_weights.values())
            den = sum(w for w, _ in feats_weights.values())
            pipeline_a_score = float(min(1.0, max(0.0, abs(num / den)))) if den > 0 else 0.0
        else:
            pipeline_a_score = 0.0

        months_in = []
        for m in vel_by_month:
            m0, m1 = _month_key_to_range(m)
            if _intervals_overlap(start_d, end_d, m0, m1):
                months_in.append(m)
        vel_window = [vel_by_month[m] for m in months_in]
        peak_signal = 0.0
        if vel_window and v_std > 1e-12:
            numer = max(vel_window) - v_mean
            denom = 2.0 * v_std + 1e-12
            peak_signal = float(min(1.0, max(0.0, numer / denom)))
        elif vel_window and max(vel_window) > v_thr:
            peak_signal = 1.0

        sim_window = [s for d, s in sim_by_date if start_d <= d <= end_d]
        sim_signal = 0.0
        if len(sim_window) >= 2:
            head = float(np.mean(sim_window[: max(1, len(sim_window) // 3)]))
            tail = float(np.mean(sim_window[-max(1, len(sim_window) // 3) :]))
            drop = head - tail
            sim_signal = float(min(1.0, max(0.0, drop / (abs(head) + 0.05))))
        elif len(sim_window) == 1:
            sim_signal = 0.0

        ai_signal = 0.0
        if ai_by_month:
            ai_vals = [ai_by_month[m] for m in months_in if m in ai_by_month]
            if len(ai_vals) >= 2:
                ai_signal = float(min(1.0, max(0.0, (ai_vals[-1] - ai_vals[0]) / 0.5)))
            elif len(ai_vals) == 1:
                ai_signal = 0.25

        b_parts = [peak_signal, sim_signal]
        if ai_convergence_curve:
            b_parts.append(ai_signal)
        pipeline_b_score = float(sum(b_parts) / len(b_parts)) if b_parts else 0.0

        pipeline_c: float | None = None
        if probability_trajectory is not None:
            pipeline_c = compute_probability_pipeline_score(
                start_d,
                end_d,
                probability_trajectory,
                settings=settings,
            )

        passes_ratio = ratio >= min_feature_ratio
        passes_ab = pipeline_a_score > 0.5 and pipeline_b_score > 0.5
        if not (passes_ratio or passes_ab):
            continue

        windows_out.append(
            ConvergenceWindow(
                start_date=start_d,
                end_date=end_d,
                features_converging=features_converging,
                convergence_ratio=ratio,
                pipeline_a_score=pipeline_a_score,
                pipeline_b_score=pipeline_b_score,
                pipeline_c_score=pipeline_c,
            )
        )

    return windows_out
