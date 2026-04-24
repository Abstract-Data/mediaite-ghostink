"""Change-point detection (PELT, BOCPD) and convergence windows (Phase 5)."""

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

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.statistics import cohens_d
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import ChangePoint
from forensics.paths import load_feature_frame_for_author, resolve_author_rows
from forensics.storage.json_io import write_json_artifact
from forensics.storage.repository import Repository
from forensics.utils.datetime import timestamps_from_frame

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
    """
    y = np.asarray(signal, dtype=float).ravel()
    if len(y) < 10:
        return []
    if not np.isfinite(y).all():
        y = np.nan_to_num(y, nan=np.nanmedian(y))
    algo = rpt.Pelt(model=cost_model, min_size=5).fit(y.reshape(-1, 1))
    breakpoints = algo.predict(pen=pen)
    return [int(b) for b in breakpoints[:-1]]


@dataclass(frozen=True, slots=True)
class _BocpdPrior:
    """Prior hyperparameters computed once per signal (RF-CPLX-004 split).

    ``sigma2``/``inv_sig2``: known observation variance estimated from the first
    ``min(80, n)`` samples.
    ``mu0``/``inv_v0``: Normal prior mean + inverse variance (seeded from the
    first ``min(10, n)`` samples).
    ``log_h``/``log_1mh``: log-hazard and log-1-hazard for the constant-rate prior.
    ``cumsum``: prefix sums of ``x`` for O(1) segment sums.
    """

    sigma2: float
    inv_sig2: float
    mu0: float
    inv_v0: float
    log_h: float
    log_1mh: float
    cumsum: np.ndarray


def _bocpd_init_prior(x: np.ndarray, hazard_rate: float) -> _BocpdPrior:
    n = len(x)
    sigma2 = float(np.var(x[: min(80, n)]))
    if sigma2 < 1e-12:
        sigma2 = 1e-12
    mu0 = float(np.mean(x[: min(10, n)]))
    v0 = sigma2 * 4.0
    return _BocpdPrior(
        sigma2=sigma2,
        inv_sig2=1.0 / sigma2,
        mu0=mu0,
        inv_v0=1.0 / v0,
        log_h=float(np.log(hazard_rate)),
        log_1mh=float(np.log(max(1e-12, 1.0 - hazard_rate))),
        cumsum=np.concatenate((np.zeros(1, dtype=float), np.cumsum(x, dtype=float))),
    )


def _bocpd_step(
    t: int,
    xt: float,
    log_pi: np.ndarray,
    prior: _BocpdPrior,
) -> tuple[np.ndarray, float]:
    """One forward update of the run-length posterior. Returns ``(log_pi_new, p_cp)``."""
    max_s = t
    log_pi = np.asarray(log_pi, dtype=float)
    if log_pi.size < max_s:
        log_pi = np.concatenate([log_pi, np.full(max_s - log_pi.size, -np.inf)])

    s_idx = np.arange(1, max_s + 1, dtype=np.int64)
    sum_s = prior.cumsum[t] - prior.cumsum[t - s_idx]
    lengths = s_idx.astype(float)
    inv_v = prior.inv_v0 + lengths * prior.inv_sig2
    m = (prior.inv_v0 * prior.mu0 + prior.inv_sig2 * sum_s) / inv_v
    var_pred = 1.0 / inv_v + prior.sigma2
    log_pred = -0.5 * (np.log(2 * np.pi * var_pred) + (xt - m) ** 2 / var_pred)

    log_evidence = logsumexp(log_pi[:max_s] + log_pred)
    log_pi_new = np.full(t + 1, -np.inf)
    log_pi_new[0] = prior.log_h + log_evidence
    log_pi_new[1 : t + 1] = prior.log_1mh + log_pi[:t] + log_pred[:t]
    log_pi_new -= logsumexp(log_pi_new)

    return log_pi_new, float(np.exp(log_pi_new[0]))


def detect_bocpd(
    signal: np.ndarray,
    hazard_rate: float = 1 / 250.0,
    threshold: float = 0.5,
) -> list[tuple[int, float]]:
    """BOCPD with Normal prior on mean, known observation variance, constant hazard.

    ``log_pi_new[0]`` is the posterior log-probability that the segment restarts at ``t``
    (i.e. a changepoint immediately before the current observation). Returns ``(t, p_cp)``
    when that probability exceeds ``threshold`` (typically sparse).

    Segment sums use prefix sums so the inner loop over segment lengths is O(1) amortized
    per timestep (vectorized over ``s``).
    """
    x = np.asarray(signal, dtype=float).ravel()
    n = len(x)
    if n < 6:
        return []

    prior = _bocpd_init_prior(x, hazard_rate)
    log_pi = np.array([0.0])
    changepoints: list[tuple[int, float]] = []

    for t in range(1, n):
        log_pi, p_cp = _bocpd_step(t, float(x[t]), log_pi, prior)
        if p_cp >= threshold:
            changepoints.append((t, p_cp))

    return changepoints


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
        out.append(
            ChangePoint(
                feature_name=feature_name,
                author_id=author_id,
                timestamp=_breakpoint_timestamp(timestamps, idx),
                confidence=confidence_for_break(idx, before, after, d),
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
    breaks = detect_pelt(values, pen=pen, cost_model=cost_model)
    return _changepoints_from_breaks(
        feature_name,
        author_id,
        values,
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
    threshold: float,
) -> list[ChangePoint]:
    raw = detect_bocpd(values, hazard_rate=hazard_rate, threshold=threshold)
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


def analyze_author_feature_changepoints(
    df: pl.DataFrame,
    *,
    author_id: str,
    settings: ForensicsSettings,
) -> list[ChangePoint]:
    """Run configured changepoint methods on each numeric feature column."""
    methods = {m.lower() for m in settings.analysis.changepoint_methods}
    pen = settings.analysis.pelt_penalty
    pelt_cost_model = settings.analysis.pelt_cost_model
    hazard = settings.analysis.bocpd_hazard_rate
    # Phase 15 Unit 1 — ``bocpd_threshold`` removed from settings because the
    # quantity it thresholds (``P(r=0)``) is algebraically pinned to the hazard
    # rate under constant-hazard A&M BOCPD (see docs/GUARDRAILS.md). Phase A
    # replaces this with a MAP-run-length-reset rule and swaps the setting;
    # until that ships, the legacy threshold is inlined here at its previous
    # default so existing callers behave identically.
    bocpd_threshold = 0.5
    out: list[ChangePoint] = []

    timestamps = timestamps_from_frame(df)

    for col in PELT_FEATURE_COLUMNS:
        if col not in df.columns:
            continue
        series = df[col].cast(pl.Float64, strict=False).to_numpy()
        if not np.isfinite(series).all():
            series = np.nan_to_num(series, nan=np.nanmedian(series))
        if len(series) < 10:
            continue
        if "pelt" in methods:
            out.extend(
                changepoints_from_pelt(
                    col,
                    author_id,
                    series,
                    timestamps,
                    pen,
                    cost_model=pelt_cost_model,
                )
            )
        if "bocpd" in methods:
            out.extend(
                changepoints_from_bocpd(
                    col,
                    author_id,
                    series,
                    timestamps,
                    hazard_rate=hazard,
                    threshold=bocpd_threshold,
                )
            )
    return out


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
        # Deferred import breaks the changepoint ↔ convergence cycle (convergence.py
        # depends on ``PELT_FEATURE_COLUMNS`` from this module).
        from forensics.analysis.convergence import ConvergenceInput, compute_convergence_scores

        cps = analyze_author_feature_changepoints(df_author, author_id=author.id, settings=settings)
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
