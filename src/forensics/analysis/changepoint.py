"""Change-point detection (PELT, BOCPD) and convergence windows.

``detect_bocpd`` defaults to MAP run-length reset; ``mode="p_r0_legacy"`` keeps the
old ``P(r=0)`` threshold path for A/B and parity (see GUARDRAILS for the legacy pin).
``_BocpdPrior.cumsum_sq`` gives O(1) segment SS for NIG → Student-t when
``student_t``; Normal-known-σ² remains for parity.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl
import ruptures as rpt
from scipy.special import logsumexp
from scipy.stats import t as student_t_dist

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.evidence import filter_evidence_change_points
from forensics.analysis.section_residualization import residualize_features_by_section
from forensics.analysis.statistics import cohens_d
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import ChangePoint
from forensics.paths import load_feature_frame_for_author, resolve_author_rows
from forensics.storage.json_io import write_json_artifact
from forensics.storage.repository import Repository
from forensics.utils.datetime import timestamps_from_frame

BocpdMode = Literal["map_reset", "p_r0_legacy"]

logger = logging.getLogger(__name__)

PeltCostModel = Literal["l2", "l1", "rbf"]

PELT_FEATURE_COLUMNS: tuple[str, ...] = (
    "ttr",
    "mattr",
    "hapax_ratio",
    "yules_k",
    "simpsons_d",
    "ai_marker_frequency",
    "sent_length_mean",
    "sent_length_std",
    "sent_length_skewness",
    "subordinate_clause_depth",
    "conjunction_freq",
    "passive_voice_ratio",
    "paragraph_length_variance",
    "flesch_kincaid",
    "coleman_liau",
    "gunning_fog",
    "bigram_entropy",
    "trigram_entropy",
    "self_similarity_30d",
    "self_similarity_90d",
    "formula_opening_score",
    "first_person_ratio",
    "hedging_frequency",
)


def collect_imputation_stats_for_changepoint_frame(
    df: pl.DataFrame,
    *,
    author_id: str,
    feature_columns: tuple[str, ...] = PELT_FEATURE_COLUMNS,
    section_residualize_applies: bool = False,
) -> dict[str, Any]:
    """L-05 — non-finite value counts per feature before median imputation in detectors."""
    per_feature: dict[str, dict[str, int]] = {}
    for col in feature_columns:
        if col not in df.columns:
            continue
        arr = df[col].cast(pl.Float64, strict=False).to_numpy()
        n = int(arr.size)
        n_nan = int(np.isnan(arr).sum())
        n_inf = int(np.isinf(arr).sum())
        per_feature[col] = {
            "n_values": n,
            "n_nan": n_nan,
            "n_inf": n_inf,
            "n_imputed": n_nan + n_inf,
        }
    return {
        "author_id": author_id,
        "section_residualize_features": section_residualize_applies,
        "note": (
            "Counts use the feature frame as passed into changepoint analysis "
            "(before internal section residualization and per-feature median imputation)."
        ),
        "per_feature": per_feature,
    }


def write_imputation_stats_artifact(
    path: Path,
    df: pl.DataFrame,
    *,
    author_id: str,
    settings: ForensicsSettings,
) -> None:
    """Write L-05 imputation stats JSON for one author."""
    payload = collect_imputation_stats_for_changepoint_frame(
        df,
        author_id=author_id,
        section_residualize_applies=settings.analysis.section_residualize_features,
    )
    write_json_artifact(path, payload)


def _impute_finite_feature_series(values: np.ndarray) -> np.ndarray:
    """C-02 — single imputation site for changepoint detectors (median of finite values)."""
    y = np.asarray(values, dtype=float).ravel()
    finite = y[np.isfinite(y)]
    med = float(np.nanmedian(finite)) if finite.size else 0.0
    return np.nan_to_num(y, nan=med, posinf=med, neginf=med)


def detect_pelt(
    signal: np.ndarray,
    pen: float = 3.0,
    *,
    cost_model: PeltCostModel = "l2",
) -> list[int]:
    """Run PELT change-point detection on a 1D signal.

    Phase 15 F0 — default ``cost_model`` is ``"l2"`` (1-D mean-shift,
    O(n)); ``"rbf"`` is the legacy O(n²) kernel kept for audit, ``"l1"``
    is the outlier-robust alternative. See ``AnalysisConfig.pelt_cost_model``.

    Callers must pass a finite series (impute upstream via
    :func:`_impute_finite_feature_series`).
    """
    y = np.asarray(signal, dtype=float).ravel()
    if len(y) < 10:
        return []
    if not np.isfinite(y).all():
        msg = "detect_pelt expects finite values; use _impute_finite_feature_series first"
        raise ValueError(msg)
    algo = rpt.Pelt(model=cost_model, min_size=5).fit(y.reshape(-1, 1))
    breakpoints = algo.predict(pen=pen)
    return [int(b) for b in breakpoints[:-1]]


@dataclass(frozen=True, slots=True)
class _BocpdPrior:
    """Prior hyperparameters computed once per signal (RF-CPLX-004 split).

    Normal-known-σ² fields (legacy / ``student_t=False`` path):
      - ``sigma2``/``inv_sig2``: known observation variance estimated from the
        first ``min(80, n)`` samples.
      - ``mu0``/``inv_v0``: Normal prior mean + inverse variance (seeded from
        the first ``min(10, n)`` samples).

    NIG → Student-t fields (default / ``student_t=True`` path; Murphy 2007 §7.6):
      - ``mu0_t``: prior mean for the segment mean.
      - ``kappa0``: prior pseudo-count for the mean (κ₀).
      - ``alpha0``: shape for the inverse-gamma over σ².
      - ``beta0``: scale for the inverse-gamma over σ².

    Hazard:
      - ``log_h``/``log_1mh``: log-hazard and log-1-hazard for the constant-rate prior.

    Prefix sums (O(1) per-step segment statistics):
      - ``cumsum``: prefix sums of ``x``.
      - ``cumsum_sq``: prefix sums of ``x**2`` (Phase 15 A4 — needed for NIG ``ss``).
    """

    sigma2: float
    inv_sig2: float
    mu0: float
    inv_v0: float
    mu0_t: float
    kappa0: float
    alpha0: float
    beta0: float
    log_h: float
    log_1mh: float
    cumsum: np.ndarray
    cumsum_sq: np.ndarray


def _bocpd_init_prior(x: np.ndarray, hazard_rate: float) -> _BocpdPrior:
    n = len(x)
    seed_slice = x[: min(10, n)]
    sigma2 = max(float(np.var(x[: min(80, n)])), 1e-12)
    mu0 = float(np.mean(seed_slice))
    # NIG seeding (Murphy 2007 §7.6): fall back to the wider prefix variance
    # when the 10-sample seed is degenerate (e.g. constant warmup).
    seed_var = float(np.var(seed_slice))
    var_seed = seed_var if seed_var >= 1e-12 else sigma2
    zero = np.zeros(1, dtype=float)
    return _BocpdPrior(
        sigma2=sigma2,
        inv_sig2=1.0 / sigma2,
        mu0=mu0,
        inv_v0=1.0 / (sigma2 * 4.0),
        mu0_t=mu0,
        kappa0=1.0,
        alpha0=1.0,
        beta0=0.5 * var_seed,
        log_h=float(np.log(hazard_rate)),
        log_1mh=float(np.log(max(1e-12, 1.0 - hazard_rate))),
        cumsum=np.concatenate((zero, np.cumsum(x, dtype=float))),
        cumsum_sq=np.concatenate((zero, np.cumsum(np.square(x), dtype=float))),
    )


def _normal_log_pred(
    xt: float,
    prior: _BocpdPrior,
    s_idx: np.ndarray,
    sum_s: np.ndarray,
) -> np.ndarray:
    """Normal-known-σ² posterior predictive (legacy path)."""
    lengths = s_idx.astype(float)
    inv_v = prior.inv_v0 + lengths * prior.inv_sig2
    m = (prior.inv_v0 * prior.mu0 + prior.inv_sig2 * sum_s) / inv_v
    var_pred = 1.0 / inv_v + prior.sigma2
    return -0.5 * (np.log(2 * np.pi * var_pred) + (xt - m) ** 2 / var_pred)


def _student_t_log_pred(
    xt: float,
    prior: _BocpdPrior,
    s_idx: np.ndarray,
    sum_s: np.ndarray,
    sum_sq_s: np.ndarray,
) -> np.ndarray:
    """NIG → Student-t posterior predictive (Murphy 2007 §7.6).

    For a segment of length ``n`` with sum ``s`` and sum-of-squares ``ss``:

        κ_n = κ_0 + n
        μ_n = (κ_0 μ_0 + s) / κ_n
        α_n = α_0 + n/2
        β_n = β_0 + 0.5 (ss − n (s/n)²) + 0.5 κ_0 n (s/n − μ_0)² / κ_n

    Posterior predictive at ``x_t``:

        ν      = 2 α_n
        loc    = μ_n
        scale² = β_n (κ_n + 1) / (α_n κ_n)

    Implemented vector-safe over the segment-length axis. ``scipy.stats.t.logpdf``
    handles ν → ∞ correctly (reduces to Normal).
    """
    n_arr = s_idx.astype(float)
    kappa_n = prior.kappa0 + n_arr
    mu_n = (prior.kappa0 * prior.mu0_t + sum_s) / kappa_n
    alpha_n = prior.alpha0 + 0.5 * n_arr
    sample_mean = sum_s / n_arr
    centered_ss = sum_sq_s - n_arr * sample_mean * sample_mean
    # Numerical floor: tiny negative values from float roundoff.
    centered_ss = np.maximum(centered_ss, 0.0)
    prior_pull = 0.5 * prior.kappa0 * n_arr * (sample_mean - prior.mu0_t) ** 2 / kappa_n
    beta_n = prior.beta0 + 0.5 * centered_ss + prior_pull
    nu = 2.0 * alpha_n
    scale2 = beta_n * (kappa_n + 1.0) / (alpha_n * kappa_n)
    # Guard against degenerate scale (e.g. n=1 with var_seed≈0).
    scale2 = np.maximum(scale2, 1e-300)
    scale = np.sqrt(scale2)
    return student_t_dist.logpdf(xt, df=nu, loc=mu_n, scale=scale)


def _bocpd_step(
    t: int,
    xt: float,
    log_pi: np.ndarray,
    prior: _BocpdPrior,
    *,
    student_t: bool = False,
) -> tuple[np.ndarray, float]:
    """One forward update of the run-length posterior. Returns ``(log_pi_new, p_cp)``.

    ``student_t=False`` keeps the original Normal-known-σ² predictive used by
    Phase 15 Unit 1 (preserved for A/B + parity tests). ``student_t=True``
    swaps in the NIG → Student-t predictive (Phase 15 A4).
    """
    max_s = t
    log_pi = np.asarray(log_pi, dtype=float)
    if log_pi.size < max_s:
        log_pi = np.concatenate([log_pi, np.full(max_s - log_pi.size, -np.inf)])

    s_idx = np.arange(1, max_s + 1, dtype=np.int64)
    sum_s = prior.cumsum[t] - prior.cumsum[t - s_idx]
    if student_t:
        sum_sq_s = prior.cumsum_sq[t] - prior.cumsum_sq[t - s_idx]
        log_pred = _student_t_log_pred(xt, prior, s_idx, sum_s, sum_sq_s)
    else:
        log_pred = _normal_log_pred(xt, prior, s_idx, sum_s)

    log_evidence = logsumexp(log_pi[:max_s] + log_pred)
    log_pi_new = np.full(t + 1, -np.inf)
    log_pi_new[0] = prior.log_h + log_evidence
    log_pi_new[1 : t + 1] = prior.log_1mh + log_pi[:t] + log_pred[:t]
    log_pi_new -= logsumexp(log_pi_new)

    return log_pi_new, float(np.exp(log_pi_new[0]))


def _detect_bocpd_legacy(
    x: np.ndarray,
    prior: _BocpdPrior,
    *,
    threshold: float,
    student_t: bool,
) -> list[tuple[int, float]]:
    """Pre-Phase-A read-out: threshold ``P(r_t = 0 | x_{1:t})`` against ``threshold``.

    Preserved byte-for-byte for rollback and replication. Under constant
    hazard this quantity is algebraically pinned to the hazard rate (see
    GUARDRAILS Sign), so the rule cannot fire on real change-points; we keep
    it only so a one-line config flip restores prior runs exactly.
    """
    n = len(x)
    log_pi = np.array([0.0])
    out: list[tuple[int, float]] = []
    for t in range(1, n):
        log_pi, p_cp = _bocpd_step(t, float(x[t]), log_pi, prior, student_t=student_t)
        if p_cp >= threshold:
            out.append((t, p_cp))
    return out


def _detect_bocpd_map_reset(
    x: np.ndarray,
    prior: _BocpdPrior,
    *,
    map_drop_ratio: float,
    min_run_length: int,
    reset_cooldown: int,
    student_t: bool,
) -> list[tuple[int, float]]:
    """Forward sweep emitting (t, confidence) on each MAP run-length reset.

    Confidence is the posterior mass at the new MAP run-length — bounded in
    [0, 1] and informative, unlike ``P(r=0)``.
    """
    n = len(x)
    log_pi = np.array([0.0])
    prev_map = 0
    last_emit_t = -10_000
    raw_emits: list[tuple[int, float]] = []
    for t in range(1, n):
        log_pi, _ = _bocpd_step(t, float(x[t]), log_pi, prior, student_t=student_t)
        current_map = int(np.argmax(log_pi))
        warmed_up = prev_map >= min_run_length
        in_cooldown = (t - last_emit_t) < reset_cooldown
        reset_detected = current_map < prev_map * map_drop_ratio
        if warmed_up and reset_detected and not in_cooldown:
            confidence = float(np.exp(log_pi[current_map]))
            raw_emits.append((t, confidence))
            last_emit_t = t
        prev_map = current_map
    return raw_emits


def _collapse_adjacent_emits(
    emits: list[tuple[int, float]], merge_window: int
) -> list[tuple[int, float]]:
    """Multi-reset collapse: keep the highest-confidence emit per adjacency cluster.

    A single mean shift can drop the MAP across several consecutive timesteps
    (e.g. 50 → 10 → 2). Merging within ``merge_window`` reduces those to one CP.
    """
    if merge_window <= 0 or len(emits) <= 1:
        return emits
    merged: list[tuple[int, float]] = []
    cluster = [emits[0]]
    for t_i, c_i in emits[1:]:
        if t_i - cluster[-1][0] <= merge_window:
            cluster.append((t_i, c_i))
        else:
            merged.append(max(cluster, key=lambda p: p[1]))
            cluster = [(t_i, c_i)]
    merged.append(max(cluster, key=lambda p: p[1]))
    return merged


def detect_bocpd(
    signal: np.ndarray,
    hazard_rate: float = 1 / 250.0,
    *,
    mode: BocpdMode = "map_reset",
    threshold: float = 0.5,
    map_drop_ratio: float = 0.5,
    min_run_length: int = 5,
    reset_cooldown: int = 3,
    merge_window: int = 2,
    student_t: bool = True,
) -> list[tuple[int, float]]:
    """BOCPD over a 1-D signal with constant hazard.

    Two detection modes are supported:

    - ``mode="map_reset"`` (default, Phase 15 Phase A): emit a CP at timestep
      ``t`` when the posterior MAP run-length drops below ``map_drop_ratio``
      times its previous value. Subject to a ``min_run_length`` warmup gate,
      a ``reset_cooldown`` refractory period, and a ``merge_window`` collapse
      that keeps the highest-confidence emit per cluster of adjacent resets.
      Confidence returned is the posterior mass at the new MAP run-length —
      meaningful, bounded in [0, 1].
    - ``mode="p_r0_legacy"``: pre-Phase-A behavior. Threshold-compares
      ``P(r_t = 0 | x_{1:t})`` against ``threshold``. Preserved byte-for-byte
      for rollback and replication studies; structurally pinned to the
      hazard rate under constant-hazard A&M (see GUARDRAILS Sign).

    The forward update math (``_bocpd_step``) is identical between modes.
    Only the read-out changes.

    The posterior predictive defaults to NIG → Student-t (Murphy 2007 §7.6,
    ``student_t=True``); set ``student_t=False`` to fall back to the original
    Normal-known-σ² conjugate.
    """
    x = np.asarray(signal, dtype=float).ravel()
    n = len(x)
    min_n = max(6, min_run_length + 2) if mode == "map_reset" else 6
    if n < min_n:
        return []

    prior = _bocpd_init_prior(x, hazard_rate)
    if mode == "p_r0_legacy":
        return _detect_bocpd_legacy(x, prior, threshold=threshold, student_t=student_t)
    raw_emits = _detect_bocpd_map_reset(
        x,
        prior,
        map_drop_ratio=map_drop_ratio,
        min_run_length=min_run_length,
        reset_cooldown=reset_cooldown,
        student_t=student_t,
    )
    return _collapse_adjacent_emits(raw_emits, merge_window)


def _pelt_confidence_from_effect(d: float) -> float:
    """Map effect size to [0, 1] as a pragmatic PELT confidence proxy."""
    return float(min(1.0, max(0.0, abs(d) / (abs(d) + 1.0))))


def _breakpoint_timestamp(timestamps: list[datetime], idx: int) -> datetime:
    if idx <= 0:
        return timestamps[0]
    if idx >= len(timestamps):
        return timestamps[-1]
    return timestamps[idx]


def _changepoints_from_breaks(
    feature_name: str,
    author_id: str,
    values: np.ndarray,
    timestamps: list[datetime],
    raw_breaks: list[int],
    *,
    method: str,
    confidence_for_break: Callable[[int, np.ndarray, np.ndarray, float], float],
) -> list[ChangePoint]:
    """Translate raw break indices into ``ChangePoint`` objects.

    Both PELT and BOCPD emit integer break indices and need the same
    slice-split-then-cohens-d treatment; ``confidence_for_break`` is the only
    method-specific piece (PELT uses ``|d|/(|d|+1)``, BOCPD uses the posterior).
    """
    y = np.asarray(values, dtype=float).ravel()
    out: list[ChangePoint] = []
    for idx in raw_breaks:
        if idx <= 0 or idx >= len(y):
            continue
        before, after = y[:idx], y[idx:]
        d = cohens_d(before, after)
        m_before, m_after = float(np.mean(before)), float(np.mean(after))
        direction: str = "increase" if m_after >= m_before else "decrease"
        conf = confidence_for_break(idx, before, after, d)
        out.append(
            ChangePoint(
                feature_name=feature_name,
                author_id=author_id,
                timestamp=_breakpoint_timestamp(timestamps, idx),
                confidence=conf,
                effect_proxy=conf,
                method=method,
                effect_size_cohens_d=float(d),
                direction=direction,  # type: ignore[arg-type]
            )
        )
    return out


def changepoints_from_pelt(
    feature_name: str,
    author_id: str,
    values: np.ndarray,
    timestamps: list[datetime],
    pen: float,
    *,
    cost_model: PeltCostModel = "l2",
) -> list[ChangePoint]:
    y = _impute_finite_feature_series(np.asarray(values, dtype=float).ravel())
    breaks = detect_pelt(y, pen=pen, cost_model=cost_model)
    return _changepoints_from_breaks(
        feature_name,
        author_id,
        y,
        timestamps,
        breaks,
        method="pelt",
        confidence_for_break=lambda _idx, _before, _after, d: _pelt_confidence_from_effect(d),
    )


def changepoints_from_bocpd(
    feature_name: str,
    author_id: str,
    values: np.ndarray,
    timestamps: list[datetime],
    hazard_rate: float,
    *,
    mode: BocpdMode = "map_reset",
    threshold: float = 0.5,
    map_drop_ratio: float = 0.5,
    min_run_length: int = 5,
    reset_cooldown: int = 3,
    merge_window: int = 2,
    student_t: bool = True,
) -> list[ChangePoint]:
    raw = detect_bocpd(
        values,
        hazard_rate=hazard_rate,
        mode=mode,
        threshold=threshold,
        map_drop_ratio=map_drop_ratio,
        min_run_length=min_run_length,
        reset_cooldown=reset_cooldown,
        merge_window=merge_window,
        student_t=student_t,
    )
    probs: dict[int, float] = dict(raw)
    return _changepoints_from_breaks(
        feature_name,
        author_id,
        values,
        timestamps,
        list(probs),
        method="bocpd",
        confidence_for_break=lambda idx, _before, _after, _d: float(min(1.0, max(0.0, probs[idx]))),
    )


def _changepoints_for_feature(
    col: str,
    df: pl.DataFrame,
    timestamps: list[datetime],
    *,
    author_id: str,
    methods: set[str],
    pen: float,
    pelt_cost_model: PeltCostModel,
    hazard: float,
    bocpd_mode: BocpdMode,
    bocpd_legacy_threshold: float,
    settings: ForensicsSettings,
) -> list[ChangePoint]:
    """Run all configured detectors on one feature column.

    Extracted from :func:`analyze_author_feature_changepoints` so the per-
    feature work can be dispatched to a ``ThreadPoolExecutor`` when
    ``feature_workers > 1`` (Phase 15 G2). Returns ``[]`` for missing /
    short / flat / undetectable series.
    """
    if col not in df.columns:
        return []
    series = _impute_finite_feature_series(
        df[col].cast(pl.Float64, strict=False).to_numpy(),
    )
    if len(series) < 10:
        return []
    # Phase 15 F3: skip flat series. PELT cannot produce meaningful CPs on
    # a constant signal, and BOCPD's variance normalization divides by
    # ~zero (sigma2 floored to 1e-12 — unstable predictive). Early-exit
    # before either detector to keep audits clean.
    if float(np.std(series)) < 1e-9:
        logger.debug(
            "changepoint: author=%s feature=%s skipped — constant signal",
            author_id,
            col,
        )
        return []
    found: list[ChangePoint] = []
    if "pelt" in methods:
        # Phase 15 J6 calibration — scale the global penalty by the feature's
        # standard deviation so a single ``pelt_penalty`` value behaves
        # consistently across features whose raw scales span 3 orders of
        # magnitude (e.g. ``ttr`` std≈0.07, ``sent_length_mean`` std≈5.5).
        # Without scaling, any global penalty over-segments low-variance
        # features and under-detects on high-variance ones.
        scaled_pen = pen * float(np.std(series))
        found.extend(
            changepoints_from_pelt(
                col,
                author_id,
                series,
                timestamps,
                scaled_pen,
                cost_model=pelt_cost_model,
            )
        )
    if "bocpd" in methods:
        found.extend(
            changepoints_from_bocpd(
                col,
                author_id,
                series,
                timestamps,
                hazard_rate=hazard,
                mode=bocpd_mode,
                threshold=bocpd_legacy_threshold,
                map_drop_ratio=settings.analysis.bocpd_map_drop_ratio,
                min_run_length=settings.analysis.bocpd_min_run_length,
                reset_cooldown=settings.analysis.bocpd_reset_cooldown,
                merge_window=settings.analysis.bocpd_merge_window,
                student_t=settings.analysis.bocpd_student_t,
            )
        )
    return found


def analyze_author_feature_changepoints(
    df: pl.DataFrame,
    *,
    author_id: str,
    settings: ForensicsSettings,
) -> list[ChangePoint]:
    """Run configured changepoint methods on each numeric feature column.

    Phase 15 G2 — opportunistic per-feature parallelism. When
    ``settings.analysis.feature_workers > 1`` the 23-feature loop is
    dispatched to a ``ThreadPoolExecutor`` (NOT a ``ProcessPoolExecutor``;
    G1 already wraps the per-author loop in processes, so nesting another
    process pool deadlocks on macOS spawn semantics, and PELT/BOCPD do
    enough numpy work to release the GIL). Default ``feature_workers == 1``
    keeps the legacy serial path.

    Output ordering matches the serial path byte-for-byte: results are
    collected into a ``{feature: [ChangePoint]}`` dict and walked in
    ``PELT_FEATURE_COLUMNS`` order, which is identical to the serial
    iteration order.
    """
    if settings.analysis.section_residualize_features:
        df = residualize_features_by_section(
            df,
            feature_columns=list(PELT_FEATURE_COLUMNS),
            min_articles_per_section=settings.analysis.min_articles_per_section_for_residualize,
        )
    methods = {m.lower() for m in settings.analysis.changepoint_methods}
    pen = settings.analysis.pelt_penalty
    pelt_cost_model = settings.analysis.pelt_cost_model
    n_articles = int(df.height)
    hazard = float(settings.analysis.bocpd_hazard_rate)
    if settings.analysis.bocpd_hazard_auto:
        exp = max(1, int(settings.analysis.bocpd_expected_changes_per_author))
        hazard = float(exp) / float(max(1, n_articles))
        hazard = max(1e-6, min(1.0, hazard))
    # Phase 15 Phase A — read all six BOCPD knobs from settings. The legacy
    # ``bocpd_threshold`` field is gone (see GUARDRAILS Sign + Unit 1 notes);
    # only ``mode="p_r0_legacy"`` consults ``threshold`` and we hard-code the
    # historical default there so a one-line config flip restores prior runs.
    bocpd_mode: BocpdMode = settings.analysis.bocpd_detection_mode
    bocpd_legacy_threshold = 0.5

    timestamps = timestamps_from_frame(df)
    feature_workers = max(1, int(settings.analysis.feature_workers))

    def _run_one(col: str) -> list[ChangePoint]:
        return _changepoints_for_feature(
            col,
            df,
            timestamps,
            author_id=author_id,
            methods=methods,
            pen=pen,
            pelt_cost_model=pelt_cost_model,
            hazard=hazard,
            bocpd_mode=bocpd_mode,
            bocpd_legacy_threshold=bocpd_legacy_threshold,
            settings=settings,
        )

    if feature_workers <= 1:
        # Legacy serial path — preserved byte-for-byte. The result-collector
        # branch below is order-equivalent but we keep this so the cold path
        # has zero ThreadPoolExecutor overhead.
        out: list[ChangePoint] = []
        for col in PELT_FEATURE_COLUMNS:
            out.extend(_run_one(col))
        return _retag_section_adjusted(out, settings)

    # Parallel path — dispatch one task per feature, walk in PELT order to
    # rebuild byte-identical output. ``ThreadPoolExecutor`` caps workers at
    # the configured value but never spawns more than one per submitted task,
    # so over-provisioning (e.g. ``feature_workers=64`` with 23 features) is
    # harmless — Python's pool just leaves the extras idle.
    from concurrent.futures import ThreadPoolExecutor

    max_workers = min(feature_workers, len(PELT_FEATURE_COLUMNS))
    results: dict[str, list[ChangePoint]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_col = {pool.submit(_run_one, col): col for col in PELT_FEATURE_COLUMNS}
        for future, col in future_to_col.items():
            results[col] = future.result()
    out_parallel: list[ChangePoint] = []
    for col in PELT_FEATURE_COLUMNS:
        out_parallel.extend(results.get(col, []))
    return _retag_section_adjusted(out_parallel, settings)


_SECTION_ADJUSTED_METHOD_MAP: dict[str, str] = {
    "pelt": "pelt_section_adjusted",
    "bocpd": "bocpd_section_adjusted",
}


def _retag_section_adjusted(
    change_points: list[ChangePoint],
    settings: ForensicsSettings,
) -> list[ChangePoint]:
    # Phase 15 J5 — when feature residualization is on, the CPs were detected
    # against section-residualized signals. Tag them so downstream consumers
    # (convergence dispatch, K4 twin-panel renderer) can distinguish them
    # from raw PELT/BOCPD output.
    if not settings.analysis.section_residualize_features:
        return change_points
    return [
        cp.model_copy(update={"method": _SECTION_ADJUSTED_METHOD_MAP[cp.method]})
        if cp.method in _SECTION_ADJUSTED_METHOD_MAP
        else cp
        for cp in change_points
    ]


def run_changepoint_analysis(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    project_root: Path,
    author_slug: str | None = None,
) -> dict[str, Any]:
    """Load Parquet per author; write changepoint and convergence JSON under data/analysis/."""
    paths = AnalysisArtifactPaths.from_project(project_root, db_path)
    # analysis_dir creation handled inside write_json_artifact (RF-DRY-004).

    with Repository(db_path) as repo:
        author_rows = resolve_author_rows(repo, settings, author_slug=author_slug)

    summary: dict[str, Any] = {"authors": [], "changepoint_files": [], "convergence_files": []}

    for author in author_rows:
        feat_path = paths.features_parquet(author.slug)
        if not feat_path.is_file():
            logger.warning("Skipping author %s: missing %s", author.slug, feat_path)
            continue
        df_author = load_feature_frame_for_author(paths.features_dir, author.slug, author.id)
        if df_author is None:
            logger.warning("Skipping author %s: no rows in %s", author.slug, feat_path)
            continue
        write_imputation_stats_artifact(
            paths.imputation_stats_json(author.slug),
            df_author,
            author_id=author.id,
            settings=settings,
        )
        # Deferred import breaks the changepoint ↔ convergence cycle (convergence.py
        # depends on ``PELT_FEATURE_COLUMNS`` from this module).
        from forensics.analysis.convergence import ConvergenceInput, compute_convergence_scores

        raw_cps = analyze_author_feature_changepoints(
            df_author,
            author_id=author.id,
            settings=settings,
        )
        cps = filter_evidence_change_points(raw_cps, settings.analysis)
        conv = compute_convergence_scores(
            ConvergenceInput.from_settings(
                cps,
                [],
                [],
                settings,
                total_feature_count=len(PELT_FEATURE_COLUMNS),
            )
        )

        cp_path = paths.changepoints_json(author.slug)
        conv_path = paths.convergence_json(author.slug)
        write_json_artifact(cp_path, cps)
        write_json_artifact(conv_path, conv)
        summary["authors"].append(author.slug)
        summary["changepoint_files"].append(str(cp_path))
        summary["convergence_files"].append(str(conv_path))
        logger.info(
            "changepoint: author=%s wrote %d change point(s), %d convergence window(s)",
            author.slug,
            len(cps),
            len(conv),
        )

    return summary
