"""Cross-pipeline convergence (Phase 7): stylometry, embedding drift, optional probability."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS
from forensics.analysis.monthkeys import iter_months_in_window, month_key_to_range
from forensics.analysis.utils import closed_interval_contains
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import ChangePoint, ConvergenceWindow

logger = logging.getLogger(__name__)

# Named convergence-scoring constants (RF-SMELL-003 / audit for pre-registration lock).
PIPELINE_SCORE_PASS_THRESHOLD: float = 0.5
"""Both pipeline A and pipeline B scores must exceed this for the window to pass on A/B alone."""

EMBEDDING_DROP_EPSILON: float = 0.05
"""Denominator epsilon for the head-vs-tail embedding similarity drop ratio."""

AI_CURVE_NORMALIZATION_DIVISOR: float = 0.5
"""Divisor that normalizes the AI-curve delta (last - first) to the [0, 1] score range."""

AI_SINGLE_VALUE_FALLBACK: float = 0.25
"""Fallback score when only one month of AI-curve data is available in the window."""


@dataclass
class ProbabilityTrajectory:
    """Optional Phase 9 trajectory signals aligned by ``YYYY-MM`` month keys."""

    monthly_perplexity: list[tuple[str, float]]
    monthly_burstiness: list[tuple[str, float]]
    monthly_binoculars: list[tuple[str, float]] | None = None


def _months_touching_window(
    window_start: date, window_end: date, month_keys: Iterable[str]
) -> list[str]:
    return [key for key, _, _ in iter_months_in_window(window_start, window_end, month_keys)]


def _monthly_values_in_window(
    window_start: date,
    window_end: date,
    monthly_series: list[tuple[str, float]],
) -> list[float]:
    by_key = dict(monthly_series)
    return [by_key[key] for key, _, _ in iter_months_in_window(window_start, window_end, by_key)]


def _two_halves_drop_score(values: list[float], strong_drop_ratio: float) -> float:
    """Score from first vs second half mean: strong drop → 1.0, mild drop → 0.5, else 0.0."""
    if len(values) < 2:
        return 0.0
    first = float(np.mean(values[: len(values) // 2]))
    last = float(np.mean(values[len(values) // 2 :]))
    if first > 1e-9 and last < first * strong_drop_ratio:
        return 1.0
    if first > 1e-9 and last < first:
        return 0.5
    return 0.0


def compute_probability_pipeline_score(
    window_start: date,
    window_end: date,
    prob: ProbabilityTrajectory,
    *,
    settings: ForensicsSettings | None = None,
) -> float:
    """Composite 0–1 from perplexity drop, burstiness flattening, optional Binoculars."""
    parts: list[float] = []

    ppx = _monthly_values_in_window(window_start, window_end, prob.monthly_perplexity)
    ppx_drop = 0.92 if settings is None else settings.analysis.convergence_perplexity_drop_ratio
    if len(ppx) >= 2:
        parts.append(_two_halves_drop_score(ppx, ppx_drop))

    br = _monthly_values_in_window(window_start, window_end, prob.monthly_burstiness)
    br_drop = 0.94 if settings is None else settings.analysis.convergence_burstiness_drop_ratio
    if len(br) >= 2:
        parts.append(_two_halves_drop_score(br, br_drop))

    if prob.monthly_binoculars:
        bx = _monthly_values_in_window(window_start, window_end, prob.monthly_binoculars)
        if len(bx) >= 2:
            spread = float(np.std(bx, ddof=1)) if len(bx) > 2 else abs(bx[-1] - bx[0])
            parts.append(min(1.0, spread))

    if not parts:
        return 0.0
    return float(sum(parts) / len(parts))


def _baseline_curve_as_dates(
    baseline_similarity_curve: list[tuple[datetime, float]],
) -> list[tuple[date, float]]:
    sim_by_date: list[tuple[date, float]] = []
    for dt, s in baseline_similarity_curve:
        dkey = dt.date() if isinstance(dt, datetime) else dt
        sim_by_date.append((dkey, s))
    return sim_by_date


def _window_start_candidates(
    change_points: list[ChangePoint],
    sim_by_date: list[tuple[date, float]],
    centroid_velocities: list[tuple[str, float]],
) -> set[date]:
    starts: set[date] = set()
    for cp in change_points:
        starts.add(cp.timestamp.date())
    if sim_by_date:
        starts.add(sim_by_date[0][0])
    if centroid_velocities:
        m0, _ = month_key_to_range(centroid_velocities[0][0])
        starts.add(m0)
    return starts


def _stylometry_weights_in_window(
    change_points: list[ChangePoint],
    start_d: date,
    end_d: date,
) -> dict[str, tuple[float, float]]:
    feats_weights: dict[str, tuple[float, float]] = {}
    for cp in change_points:
        d = cp.timestamp.date()
        if closed_interval_contains(d, start_d, end_d):
            w = max(float(cp.confidence), 1e-6)
            prev = feats_weights.get(cp.feature_name)
            if prev is None or w * abs(cp.effect_size_cohens_d) > prev[0] * abs(prev[1]):
                feats_weights[cp.feature_name] = (w, float(cp.effect_size_cohens_d))
    return feats_weights


def _pipeline_a_from_stylometry(
    feats_weights: dict[str, tuple[float, float]],
    total: int,
) -> tuple[list[str], float, float]:
    features_converging = sorted(feats_weights.keys())
    ratio = len(features_converging) / float(total) if total else 0.0
    if features_converging:
        num = sum(w * d for w, d in feats_weights.values())
        den = sum(w for w, _ in feats_weights.values())
        pipeline_a_score = float(min(1.0, max(0.0, abs(num / den)))) if den > 0 else 0.0
    else:
        pipeline_a_score = 0.0
    return features_converging, ratio, pipeline_a_score


def _velocity_peak_and_months(
    start_d: date,
    end_d: date,
    vel_by_month: dict[str, float],
    v_mean: float,
    v_std: float,
    v_thr: float,
) -> tuple[float, list[str]]:
    months_in = [key for key, _, _ in iter_months_in_window(start_d, end_d, vel_by_month)]
    vel_window = [vel_by_month[m] for m in months_in]
    peak_signal = 0.0
    if vel_window and v_std > 1e-12:
        numer = max(vel_window) - v_mean
        denom = 2.0 * v_std + 1e-12
        peak_signal = float(min(1.0, max(0.0, numer / denom)))
    elif vel_window and max(vel_window) > v_thr:
        peak_signal = 1.0
    return peak_signal, months_in


def _embedding_similarity_signal(
    sim_by_date: list[tuple[date, float]],
    start_d: date,
    end_d: date,
) -> float:
    sim_window = [s for d, s in sim_by_date if closed_interval_contains(d, start_d, end_d)]
    if len(sim_window) < 2:
        return 0.0
    head = float(np.mean(sim_window[: max(1, len(sim_window) // 3)]))
    tail = float(np.mean(sim_window[-max(1, len(sim_window) // 3) :]))
    drop = head - tail
    return float(min(1.0, max(0.0, drop / (abs(head) + EMBEDDING_DROP_EPSILON))))


def _ai_curve_signal(ai_by_month: dict[str, float], months_in: list[str]) -> float:
    ai_vals = [ai_by_month[m] for m in months_in if m in ai_by_month]
    if len(ai_vals) >= 2:
        return float(
            min(1.0, max(0.0, (ai_vals[-1] - ai_vals[0]) / AI_CURVE_NORMALIZATION_DIVISOR))
        )
    if len(ai_vals) == 1:
        return AI_SINGLE_VALUE_FALLBACK
    return 0.0


@dataclass(frozen=True, slots=True)
class ConvergenceInput:
    """Packaged inputs for ``compute_convergence_scores`` (RF-PATTERN-002 / P2-ARCH-002).

    Bundles the 12 parameters the scoring function used to take positionally so
    callers can build the struct incrementally, scoring helpers can share it,
    and new signals slot in without another keyword argument avalanche.
    """

    change_points: list[ChangePoint]
    centroid_velocities: list[tuple[str, float]]
    baseline_similarity_curve: list[tuple[datetime, float]]
    window_days: int
    min_feature_ratio: float
    total_feature_count: int
    ai_convergence_curve: list[tuple[str, float]] | None
    probability_trajectory: ProbabilityTrajectory | None
    settings: ForensicsSettings | None
    use_permutation: bool
    permutation_seed: int
    n_permutations: int

    @classmethod
    def build(
        cls,
        change_points: list[ChangePoint],
        centroid_velocities: list[tuple[str, float]],
        baseline_similarity_curve: list[tuple[datetime, float]],
        *,
        window_days: int = 90,
        min_feature_ratio: float = 0.6,
        total_feature_count: int | None = None,
        ai_convergence_curve: list[tuple[str, float]] | None = None,
        probability_trajectory: ProbabilityTrajectory | None = None,
        settings: ForensicsSettings | None = None,
        use_permutation: bool = False,
        permutation_seed: int = 42,
        n_permutations: int = 1000,
    ) -> ConvergenceInput:
        """Resolve defaults from ``settings`` and from ``PELT_FEATURE_COLUMNS``."""
        if settings is not None:
            window_days = settings.analysis.convergence_window_days
            min_feature_ratio = settings.analysis.convergence_min_feature_ratio
        total = (
            total_feature_count if total_feature_count is not None else len(PELT_FEATURE_COLUMNS)
        )
        return cls(
            change_points=change_points,
            centroid_velocities=centroid_velocities,
            baseline_similarity_curve=baseline_similarity_curve,
            window_days=window_days,
            min_feature_ratio=min_feature_ratio,
            total_feature_count=total,
            ai_convergence_curve=ai_convergence_curve,
            probability_trajectory=probability_trajectory,
            settings=settings,
            use_permutation=use_permutation,
            permutation_seed=permutation_seed,
            n_permutations=n_permutations,
        )


@dataclass(frozen=True, slots=True)
class _VelocityStats:
    """Precomputed per-author velocity aggregates reused across windows."""

    by_month: dict[str, float]
    mean: float
    std: float
    threshold: float


def _precompute_velocity_stats(
    centroid_velocities: list[tuple[str, float]],
) -> _VelocityStats:
    vel_by_month = dict(centroid_velocities)
    vel_vals = np.asarray([v for _, v in centroid_velocities], dtype=float)
    v_mean = float(np.mean(vel_vals)) if vel_vals.size else 0.0
    v_std = float(np.std(vel_vals, ddof=1)) if vel_vals.size > 1 else 0.0
    return _VelocityStats(
        by_month=vel_by_month,
        mean=v_mean,
        std=v_std,
        threshold=v_mean + 2.0 * v_std,
    )


def _score_single_window(
    start_d: date,
    end_d: date,
    *,
    input_: ConvergenceInput,
    velocity_stats: _VelocityStats,
    sim_by_date: list[tuple[date, float]],
    ai_by_month: dict[str, float],
) -> ConvergenceWindow | None:
    """Score one candidate window; ``None`` means the window failed the cutoffs."""
    feats_weights = _stylometry_weights_in_window(input_.change_points, start_d, end_d)
    features_converging, ratio, pipeline_a_score = _pipeline_a_from_stylometry(
        feats_weights, input_.total_feature_count
    )

    peak_signal, months_in = _velocity_peak_and_months(
        start_d,
        end_d,
        velocity_stats.by_month,
        velocity_stats.mean,
        velocity_stats.std,
        velocity_stats.threshold,
    )
    sim_signal = _embedding_similarity_signal(sim_by_date, start_d, end_d)
    ai_signal = _ai_curve_signal(ai_by_month, months_in) if input_.ai_convergence_curve else 0.0

    b_parts = [peak_signal, sim_signal]
    if input_.ai_convergence_curve:
        b_parts.append(ai_signal)
    pipeline_b_score = float(sum(b_parts) / len(b_parts)) if b_parts else 0.0

    pipeline_c: float | None = None
    if input_.probability_trajectory is not None:
        pipeline_c = compute_probability_pipeline_score(
            start_d,
            end_d,
            input_.probability_trajectory,
            settings=input_.settings,
        )

    passes_ratio = ratio >= input_.min_feature_ratio
    passes_ab = (
        pipeline_a_score > PIPELINE_SCORE_PASS_THRESHOLD
        and pipeline_b_score > PIPELINE_SCORE_PASS_THRESHOLD
    )
    if not (passes_ratio or passes_ab):
        return None

    return ConvergenceWindow(
        start_date=start_d,
        end_date=end_d,
        features_converging=features_converging,
        convergence_ratio=ratio,
        pipeline_a_score=pipeline_a_score,
        pipeline_b_score=pipeline_b_score,
        pipeline_c_score=pipeline_c,
    )


def _run_permutation_test(
    input_: ConvergenceInput,
    windows_out: list[ConvergenceWindow],
) -> None:
    """Empirical null over change-point labels; logs the observed p-value."""
    from forensics.analysis.permutation import permutation_test

    # Null: shuffle change-point labels, recompute max convergence ratio. The
    # membership of each change-point in each window does not depend on the
    # shuffle, so precompute it once.
    rng = np.random.default_rng(input_.permutation_seed)
    labels = np.array([cp.feature_name for cp in input_.change_points])
    window_members: list[np.ndarray] = [
        np.array(
            [
                i
                for i, cp in enumerate(input_.change_points)
                if closed_interval_contains(cp.timestamp.date(), w.start_date, w.end_date)
            ],
            dtype=int,
        )
        for w in windows_out
    ]

    total = input_.total_feature_count
    null: list[float] = []
    for _ in range(input_.n_permutations):
        shuffled = rng.permutation(labels)
        max_shuf_ratio = 0.0
        for idx in window_members:
            if idx.size == 0:
                continue
            ratio_shuf = len(set(shuffled[idx])) / float(total)
            if ratio_shuf > max_shuf_ratio:
                max_shuf_ratio = ratio_shuf
        null.append(max_shuf_ratio)

    observed = max(w.convergence_ratio for w in windows_out)
    result = permutation_test(observed, null, n_permutations=input_.n_permutations)
    logger.info(
        "convergence permutation test: observed_ratio=%.3f p=%.4f (null mean=%.3f)",
        result.observed,
        result.p_value,
        result.null_mean,
    )


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
    use_permutation: bool = False,
    permutation_seed: int = 42,
    n_permutations: int = 1000,
) -> list[ConvergenceWindow]:
    """Quantify agreement between Pipeline A (stylometry), Pipeline B (embeddings), and C.

    When ``use_permutation`` is True, each returned window's convergence ratio
    is additionally evaluated via a permutation test over the change-point
    timestamps. The empirical p-value is logged but does not alter the returned
    windows — the default path is unchanged.
    """
    input_ = ConvergenceInput.build(
        change_points,
        centroid_velocities,
        baseline_similarity_curve,
        window_days=window_days,
        min_feature_ratio=min_feature_ratio,
        total_feature_count=total_feature_count,
        ai_convergence_curve=ai_convergence_curve,
        probability_trajectory=probability_trajectory,
        settings=settings,
        use_permutation=use_permutation,
        permutation_seed=permutation_seed,
        n_permutations=n_permutations,
    )
    if input_.total_feature_count <= 0:
        return []

    velocity_stats = _precompute_velocity_stats(centroid_velocities)
    sim_by_date = _baseline_curve_as_dates(baseline_similarity_curve)
    ai_by_month = dict(ai_convergence_curve) if ai_convergence_curve else {}
    starts = _window_start_candidates(change_points, sim_by_date, centroid_velocities)
    if not starts:
        return []

    windows_out: list[ConvergenceWindow] = []
    seen: set[tuple[date, date]] = set()

    for start_d in sorted(starts):
        end_d = start_d + timedelta(days=input_.window_days)
        key = (start_d, end_d)
        if key in seen:
            continue
        seen.add(key)
        window = _score_single_window(
            start_d,
            end_d,
            input_=input_,
            velocity_stats=velocity_stats,
            sim_by_date=sim_by_date,
            ai_by_month=ai_by_month,
        )
        if window is not None:
            windows_out.append(window)

    if input_.use_permutation and windows_out and input_.change_points:
        _run_permutation_test(input_, windows_out)

    return windows_out
