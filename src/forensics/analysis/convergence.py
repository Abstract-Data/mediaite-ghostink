"""Cross-pipeline convergence (Phase 7): stylometry, embedding drift, optional probability."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS
from forensics.analysis.feature_families import FAMILY_COUNT, FEATURE_FAMILIES
from forensics.analysis.monthkeys import iter_months_in_window, month_key_to_range
from forensics.config.settings import AnalysisConfig, ForensicsSettings
from forensics.models.analysis import ChangePoint, ConvergenceWindow
from forensics.paths import closed_interval_contains
from forensics.storage.json_io import write_json_artifact

logger = logging.getLogger(__name__)


def resolve_effective_convergence_window_days(
    analysis: AnalysisConfig,
    article_timestamps: list[datetime],
) -> int:
    """I-02 — bounded convergence window from median inter-article spacing (days)."""
    if not analysis.convergence_window_adaptive or len(article_timestamps) < 2:
        return int(analysis.convergence_window_days)
    ts = sorted(article_timestamps)
    deltas = [max(0.0, (ts[i] - ts[i - 1]).total_seconds() / 86400.0) for i in range(1, len(ts))]
    if not deltas:
        return int(analysis.convergence_window_days)
    deltas.sort()
    med = float(deltas[len(deltas) // 2])
    adaptive = int(round(max(14.0, med * 6.0)))
    lo, hi = int(analysis.convergence_window_days_min), int(analysis.convergence_window_days_max)
    return max(lo, min(hi, adaptive))


# Named convergence-scoring constants (RF-SMELL-003 / audit for pre-registration lock).
PIPELINE_SCORE_PASS_THRESHOLD: float = 0.3
"""Both pipeline A and pipeline B scores must exceed this for the window to pass on A/B alone.

Lowered from 0.5 → 0.3 in Fix-F (post-Phase-15-Fix-E) so pipeline_b-positive
windows from percentile mode actually persist into the AB intersection. The
strict 0.5 threshold filtered all percentile-mode-lifted windows because
peak_signal alone tops at 0.5 when sim_signal=ai_signal=0.
"""

DRIFT_ONLY_PB_THRESHOLD: float = 0.3
"""Phase 15 Fix-G third persistence channel — fallback when no settings supply one.

A window survives whenever ``pipeline_b_score >= DRIFT_ONLY_PB_THRESHOLD``
regardless of the ratio / AB-intersection gates. Pre-Fix-G, 13 of 14 authors
persisted *zero* windows with positive pipeline_b because their pa fell below
0.3, hiding the drift signal from the report. The runtime value lives on
``AnalysisConfig.convergence_drift_only_pb_threshold`` and is propagated via
:class:`ConvergenceInput`.

M-18 — treat ``passes_via`` entries containing ``drift_only`` as the weakest
admission tier in narratives; the 0.3 threshold was chosen post-hoc (see
``data/preregistration/amendment_phase15.md``).
"""

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


def _cps_in_window(
    change_points: list[ChangePoint],
    start_d: date,
    end_d: date,
) -> list[ChangePoint]:
    """Change-points whose timestamp falls in ``[start_d, end_d]``."""
    return [
        cp for cp in change_points if closed_interval_contains(cp.timestamp.date(), start_d, end_d)
    ]


def _eligible_convergence_family_axes(
    n_rankable_per_family: dict[str, int],
    family_count: int,
) -> int:
    """Denominator for Pipeline A family coverage ratio (Phase 16 D5).

    When ``n_rankable_per_family`` is empty (no hypothesis-test context), fall
    back to ``family_count`` so unit tests and compare-only paths behave as
    before Phase 16. Otherwise count how many registered families have at
    least one BH-rankable feature in the hypothesis battery for this author.
    """
    if not n_rankable_per_family:
        return family_count
    eligible = sum(1 for c in n_rankable_per_family.values() if c > 0)
    return eligible if eligible > 0 else family_count


def _pipeline_a_from_stylometry(
    cps_in_window: list[ChangePoint],
    n_rankable_per_family: dict[str, int],
) -> tuple[list[str], list[str], float, float]:
    """Pipeline A score under family grouping (Phase 15 B2).

    One vote per family: the representative CP for a family is the in-window
    CP that maximises ``confidence * |effect_size_cohens_d|``. The ratio is
    computed over eligible stylometric axes (Phase 16 D5: families with at
    least one rankable hypothesis-test feature when counts are supplied;
    otherwise ``FAMILY_COUNT``), and the score is the unweighted mean of
    per-family representative scores clipped to ``[0, 1]``.

    Returns ``(features_converging, families_converging, ratio, score)`` —
    ``features_converging`` lists one representative raw feature per family
    sorted alphabetically; ``families_converging`` mirrors it at the family
    level so callers can populate ``ConvergenceWindow.families_converging``.
    """
    family_reps: dict[str, float] = {}
    family_feature: dict[str, str] = {}
    for cp in cps_in_window:
        fam = FEATURE_FAMILIES.get(cp.feature_name)
        if fam is None:
            continue
        # M-19 — cap per change-point before family aggregation (extreme |d|
        # no longer saturates the family mean). ``effect_proxy`` is the
        # strength axis (M-10); fall back to ``confidence`` for legacy rows.
        proxy = float(cp.effect_proxy) if cp.effect_proxy is not None else float(cp.confidence)
        score = min(1.0, proxy * abs(float(cp.effect_size_cohens_d)))
        prev = family_reps.get(fam, -1.0)
        if score > prev:
            family_reps[fam] = score
            family_feature[fam] = cp.feature_name

    if not family_reps:
        return [], [], 0.0, 0.0

    denom = float(_eligible_convergence_family_axes(n_rankable_per_family, FAMILY_COUNT))
    ratio = len(family_reps) / denom
    pipeline_a_score = float(min(1.0, float(np.mean(list(family_reps.values())))))
    features_converging = sorted(family_feature.values())
    families_converging = sorted(family_reps.keys())
    return features_converging, families_converging, ratio, pipeline_a_score


def _velocity_peak_and_months(
    start_d: date,
    end_d: date,
    vel_by_month: dict[str, float],
    v_mean: float,
    v_std: float,
    v_thr: float,
    *,
    mode: str = "legacy",
    author_velocities_all: list[float] | None = None,
) -> tuple[float, list[str]]:
    """Velocity peak signal + the months covered by the window.

    Phase 15 E3: when ``mode == "percentile"`` the peak signal becomes the
    per-author percentile rank of the window's max velocity against the
    author's full history (``author_velocities_all``), not a z-score against
    the (potentially tiny) newsroom-wide mean/std.
    """
    months_in = [key for key, _, _ in iter_months_in_window(start_d, end_d, vel_by_month)]
    vel_window = [vel_by_month[m] for m in months_in]
    if not vel_window:
        return 0.0, months_in

    if mode == "percentile" and author_velocities_all:
        hist = np.asarray(author_velocities_all, dtype=float)
        peak_signal = float((hist <= max(vel_window)).mean())
        return peak_signal, months_in

    peak_signal = 0.0
    if v_std > 1e-12:
        numer = max(vel_window) - v_mean
        denom = 2.0 * v_std + 1e-12
        peak_signal = float(min(1.0, max(0.0, numer / denom)))
    elif max(vel_window) > v_thr:
        peak_signal = 1.0
    return peak_signal, months_in


def _embedding_similarity_signal(
    sim_by_date: list[tuple[date, float]],
    start_d: date,
    end_d: date,
    *,
    mode: str = "legacy",
    sim_std_author: float = 0.0,
) -> float:
    """Head-vs-tail similarity drop; Phase 15 E3 uses a per-author epsilon floor."""
    sim_window = [s for d, s in sim_by_date if closed_interval_contains(d, start_d, end_d)]
    if len(sim_window) < 2:
        return 0.0
    head = float(np.mean(sim_window[: max(1, len(sim_window) // 3)]))
    tail = float(np.mean(sim_window[-max(1, len(sim_window) // 3) :]))
    drop = head - tail
    epsilon = (
        max(EMBEDDING_DROP_EPSILON, 0.1 * sim_std_author)
        if mode == "percentile"
        else EMBEDDING_DROP_EPSILON
    )
    return float(min(1.0, max(0.0, drop / (abs(head) + epsilon))))


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
    drift_only_pb_threshold: float = DRIFT_ONLY_PB_THRESHOLD
    n_rankable_per_family: dict[str, int] = field(default_factory=dict)

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
        drift_only_pb_threshold: float | None = None,
        n_rankable_per_family: dict[str, int] | None = None,
        article_timestamps: list[datetime] | None = None,
    ) -> ConvergenceInput:
        """Resolve defaults from ``settings`` and from ``PELT_FEATURE_COLUMNS``."""
        if settings is not None:
            window_days = settings.analysis.convergence_window_days
            if article_timestamps is not None:
                window_days = resolve_effective_convergence_window_days(
                    settings.analysis,
                    list(article_timestamps),
                )
            min_feature_ratio = settings.analysis.convergence_min_feature_ratio
            if drift_only_pb_threshold is None:
                drift_only_pb_threshold = settings.analysis.convergence_drift_only_pb_threshold
        if drift_only_pb_threshold is None:
            drift_only_pb_threshold = DRIFT_ONLY_PB_THRESHOLD
        total = (
            total_feature_count if total_feature_count is not None else len(PELT_FEATURE_COLUMNS)
        )
        rankable = dict(n_rankable_per_family) if n_rankable_per_family is not None else {}
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
            drift_only_pb_threshold=drift_only_pb_threshold,
            n_rankable_per_family=rankable,
        )

    @classmethod
    def from_settings(
        cls,
        change_points: list[ChangePoint],
        centroid_velocities: list[tuple[str, float]],
        baseline_similarity_curve: list[tuple[datetime, float]],
        settings: ForensicsSettings,
        *,
        ai_convergence_curve: list[tuple[str, float]] | None = None,
        probability_trajectory: ProbabilityTrajectory | None = None,
        total_feature_count: int | None = None,
        n_rankable_per_family: dict[str, int] | None = None,
        article_timestamps: list[datetime] | None = None,
    ) -> ConvergenceInput:
        """Build a ``ConvergenceInput`` using permutation knobs drawn from settings.

        This is the common case for callers with a populated ``ForensicsSettings``;
        it reads ``convergence_use_permutation`` /
        ``convergence_permutation_iterations`` / ``convergence_permutation_seed``
        from ``settings.analysis`` instead of forcing every call site to re-thread
        those three attributes.
        """
        ac = settings.analysis
        return cls.build(
            change_points,
            centroid_velocities,
            baseline_similarity_curve,
            settings=settings,
            ai_convergence_curve=ai_convergence_curve,
            probability_trajectory=probability_trajectory,
            total_feature_count=total_feature_count,
            use_permutation=ac.convergence_use_permutation,
            n_permutations=ac.convergence_permutation_iterations,
            permutation_seed=ac.convergence_permutation_seed,
            n_rankable_per_family=n_rankable_per_family,
            article_timestamps=article_timestamps,
        )


@dataclass(frozen=True, slots=True)
class _VelocityStats:
    """Precomputed per-author velocity aggregates reused across windows."""

    by_month: dict[str, float]
    mean: float
    std: float
    threshold: float
    all_values: list[float]


def _precompute_velocity_stats(
    centroid_velocities: list[tuple[str, float]],
) -> _VelocityStats:
    vel_by_month = dict(centroid_velocities)
    all_values = [v for _, v in centroid_velocities]
    vel_vals = np.asarray(all_values, dtype=float)
    v_mean = float(np.mean(vel_vals)) if vel_vals.size else 0.0
    v_std = float(np.std(vel_vals, ddof=1)) if vel_vals.size > 1 else 0.0
    return _VelocityStats(
        by_month=vel_by_month,
        mean=v_mean,
        std=v_std,
        threshold=v_mean + 2.0 * v_std,
        all_values=all_values,
    )


def _sim_std_author(sim_by_date: list[tuple[date, float]]) -> float:
    """Author-level std of the baseline-similarity curve (Phase 15 E3 anchor)."""
    if len(sim_by_date) <= 1:
        return 0.0
    return float(np.std(np.fromiter((s for _, s in sim_by_date), dtype=float), ddof=1))


def _score_single_window(
    start_d: date,
    end_d: date,
    *,
    input_: ConvergenceInput,
    velocity_stats: _VelocityStats,
    sim_by_date: list[tuple[date, float]],
    sim_std_author: float,
    ai_by_month: dict[str, float],
) -> tuple[ConvergenceWindow | None, dict[str, Any]]:
    """Score one candidate window; ``None`` window means the window failed the cutoffs.

    Always returns a component dict (L-01) for structured convergence diagnostics.
    """
    cps_in_window = _cps_in_window(input_.change_points, start_d, end_d)
    features_converging, families_converging, ratio, pipeline_a_score = _pipeline_a_from_stylometry(
        cps_in_window,
        input_.n_rankable_per_family,
    )

    pipeline_b_mode = (
        input_.settings.analysis.pipeline_b_mode if input_.settings is not None else "legacy"
    )

    peak_signal, months_in = _velocity_peak_and_months(
        start_d,
        end_d,
        velocity_stats.by_month,
        velocity_stats.mean,
        velocity_stats.std,
        velocity_stats.threshold,
        mode=pipeline_b_mode,
        author_velocities_all=velocity_stats.all_values,
    )
    sim_signal = _embedding_similarity_signal(
        sim_by_date,
        start_d,
        end_d,
        mode=pipeline_b_mode,
        sim_std_author=sim_std_author,
    )
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

    # Phase 15 E1 — emit per-window component signals at DEBUG so the seven
    # authors whose Pipeline B floors to 0.0 are diagnosable from logs alone.
    author_label = getattr(input_, "author_id", None) or (
        cps_in_window[0].author_id if cps_in_window else "?"
    )
    logger.debug(
        "convergence: author=%s window=%s-%s peak_signal=%.4f sim_signal=%.4f "
        "ai_signal=%.4f pipeline_b=%.4f",
        author_label,
        start_d,
        end_d,
        peak_signal,
        sim_signal,
        ai_signal,
        pipeline_b_score,
    )

    passes_ratio = ratio >= input_.min_feature_ratio
    passes_ab = (
        pipeline_a_score > PIPELINE_SCORE_PASS_THRESHOLD
        and pipeline_b_score > PIPELINE_SCORE_PASS_THRESHOLD
    )
    # Phase 15 Fix-G — drift-only channel: persist windows where the embedding
    # / velocity signal is strong enough on its own, even if pipeline_a is too
    # weak to clear the AB intersection and the family ratio gate misses.
    passes_drift_only = pipeline_b_score >= input_.drift_only_pb_threshold
    admitted = bool(passes_ratio or passes_ab or passes_drift_only)
    passes_via: list[str] = []
    if passes_ratio:
        passes_via.append("ratio")
    if passes_ab:
        passes_via.append("ab")
    if passes_drift_only:
        passes_via.append("drift_only")

    components: dict[str, Any] = {
        "window_start": start_d.isoformat(),
        "window_end": end_d.isoformat(),
        "peak_signal": peak_signal,
        "sim_signal": sim_signal,
        "ai_signal": ai_signal,
        "pipeline_a_score": pipeline_a_score,
        "pipeline_b_score": pipeline_b_score,
        "pipeline_c_score": pipeline_c,
        "convergence_ratio": ratio,
        "min_feature_ratio": input_.min_feature_ratio,
        "passes_ratio": passes_ratio,
        "passes_ab": passes_ab,
        "passes_drift_only": passes_drift_only,
        "passes_via": list(passes_via),
        "admitted": admitted,
        "n_change_points_in_window": len(cps_in_window),
    }
    if not admitted:
        return None, components

    return (
        ConvergenceWindow(
            start_date=start_d,
            end_date=end_d,
            features_converging=features_converging,
            families_converging=families_converging,
            n_rankable_per_family=dict(input_.n_rankable_per_family),
            convergence_ratio=ratio,
            pipeline_a_score=pipeline_a_score,
            pipeline_b_score=pipeline_b_score,
            pipeline_c_score=pipeline_c,
            passes_via=passes_via,
        ),
        components,
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


_RAW_CP_METHODS: frozenset[str] = frozenset({"pelt", "bocpd"})
_SECTION_ADJUSTED_CP_METHODS: frozenset[str] = frozenset(
    {"pelt_section_adjusted", "bocpd_section_adjusted"}
)


def _filter_change_points_by_source(
    change_points: list[ChangePoint],
    source: str,
    *,
    residualization_enabled: bool = True,
) -> list[ChangePoint]:
    """Phase 15 J5 dispatch: pick the CP stream the convergence stage consumes.

    - ``"raw"`` keeps only raw PELT/BOCPD change-points.
    - ``"section_adjusted"`` keeps only section-adjusted variants if any exist
      for this author; otherwise falls back to raw. The fallback logs at INFO
      when residualization was supposed to produce them (real signal — none
      survived) and at DEBUG when the producer is configured to skip
      residualization (silent expected path; the consumer-side default still
      asks for ``section_adjusted``).
    """
    if source == "raw":
        return [cp for cp in change_points if cp.method in _RAW_CP_METHODS]
    if source == "section_adjusted":
        adjusted = [cp for cp in change_points if cp.method in _SECTION_ADJUSTED_CP_METHODS]
        if adjusted:
            return adjusted
        msg = "convergence: no section-adjusted change-points found; falling back to raw CPs"
        if residualization_enabled:
            logger.info(msg)
        else:
            logger.debug(msg)
        return [cp for cp in change_points if cp.method in _RAW_CP_METHODS]
    # Unknown source: pass through untouched rather than silently drop data.
    return change_points


def compute_convergence_scores(
    input_: ConvergenceInput,
    *,
    components_artifact_path: Path | None = None,
    author_slug: str | None = None,
) -> list[ConvergenceWindow]:
    """Quantify agreement between Pipeline A (stylometry), Pipeline B (embeddings), and C.

    When ``input_.use_permutation`` is True, each returned window's convergence ratio
    is additionally evaluated via a permutation test over the change-point
    timestamps. The empirical p-value is logged but does not alter the returned
    windows — the default path is unchanged.

    Construct ``input_`` via :meth:`ConvergenceInput.from_settings` for the common
    case (a populated ``ForensicsSettings``) or :meth:`ConvergenceInput.build` for
    full control over the permutation knobs.
    """
    if input_.total_feature_count <= 0:
        return []

    # Phase 15 J5 — choose raw vs section-adjusted CPs before any scoring runs.
    cp_source = (
        input_.settings.analysis.convergence_cp_source if input_.settings is not None else "raw"
    )
    residualization_enabled = (
        input_.settings.analysis.section_residualize_features
        if input_.settings is not None
        else False
    )
    filtered_cps = _filter_change_points_by_source(
        input_.change_points,
        cp_source,
        residualization_enabled=residualization_enabled,
    )
    if filtered_cps is not input_.change_points:
        input_ = replace(input_, change_points=filtered_cps)

    velocity_stats = _precompute_velocity_stats(input_.centroid_velocities)
    sim_by_date = _baseline_curve_as_dates(input_.baseline_similarity_curve)
    sim_std = _sim_std_author(sim_by_date)
    ai_by_month = dict(input_.ai_convergence_curve) if input_.ai_convergence_curve else {}
    starts = _window_start_candidates(input_.change_points, sim_by_date, input_.centroid_velocities)
    if not starts:
        return []

    windows_out: list[ConvergenceWindow] = []
    component_rows: list[dict[str, Any]] = []
    seen: set[tuple[date, date]] = set()

    for start_d in sorted(starts):
        end_d = start_d + timedelta(days=input_.window_days)
        key = (start_d, end_d)
        if key in seen:
            continue
        seen.add(key)
        window, comp = _score_single_window(
            start_d,
            end_d,
            input_=input_,
            velocity_stats=velocity_stats,
            sim_by_date=sim_by_date,
            sim_std_author=sim_std,
            ai_by_month=ai_by_month,
        )
        component_rows.append(comp)
        if window is not None:
            windows_out.append(window)

    if components_artifact_path is not None:
        payload: dict[str, Any] = {
            "author_slug": author_slug or "",
            "windows_evaluated": len(component_rows),
            "window_components": component_rows,
        }
        write_json_artifact(components_artifact_path, payload)

    if input_.use_permutation and windows_out and input_.change_points:
        _run_permutation_test(input_, windows_out)

    return windows_out
