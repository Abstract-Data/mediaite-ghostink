"""Change-point detection (PELT, BOCPD) and convergence windows (Phase 5)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import ruptures as rpt
from scipy.special import logsumexp

from forensics.analysis.statistics import cohens_d
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import ChangePoint, ConvergenceWindow
from forensics.storage.parquet import read_features
from forensics.storage.repository import Repository, init_db
from forensics.utils.datetime import parse_datetime

logger = logging.getLogger(__name__)

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


def detect_pelt(signal: np.ndarray, pen: float = 3.0) -> list[int]:
    """Run PELT change-point detection on a 1D signal (ruptures RBF model)."""
    y = np.asarray(signal, dtype=float).ravel()
    if len(y) < 10:
        return []
    if not np.isfinite(y).all():
        y = np.nan_to_num(y, nan=np.nanmedian(y))
    algo = rpt.Pelt(model="rbf", min_size=5).fit(y.reshape(-1, 1))
    breakpoints = algo.predict(pen=pen)
    return [int(b) for b in breakpoints[:-1]]


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

    sigma2 = float(np.var(x[: min(80, n)]))
    if sigma2 < 1e-12:
        sigma2 = 1e-12
    inv_sig2 = 1.0 / sigma2
    mu0 = float(np.mean(x[: min(10, n)]))
    v0 = sigma2 * 4.0
    inv_v0 = 1.0 / v0
    log_h = float(np.log(hazard_rate))
    log_1mh = float(np.log(max(1e-12, 1.0 - hazard_rate)))

    log_pi = np.array([0.0])
    changepoints: list[tuple[int, float]] = []
    cumsum = np.concatenate((np.zeros(1, dtype=float), np.cumsum(x, dtype=float)))

    for t in range(1, n):
        xt = x[t]
        max_s = t
        log_pi = np.asarray(log_pi, dtype=float)
        if log_pi.size < max_s:
            log_pi = np.concatenate([log_pi, np.full(max_s - log_pi.size, -np.inf)])

        s_idx = np.arange(1, max_s + 1, dtype=np.int64)
        sum_s = cumsum[t] - cumsum[t - s_idx]
        lengths = s_idx.astype(float)
        inv_v = inv_v0 + lengths * inv_sig2
        m = (inv_v0 * mu0 + inv_sig2 * sum_s) / inv_v
        var_pred = 1.0 / inv_v + sigma2
        log_pred = -0.5 * (np.log(2 * np.pi * var_pred) + (xt - m) ** 2 / var_pred)

        log_evidence = logsumexp(log_pi[:max_s] + log_pred)
        log_pi_new = np.full(t + 1, -np.inf)
        log_pi_new[0] = log_h + log_evidence
        for new_len in range(2, t + 2):
            log_pi_new[new_len - 1] = log_1mh + log_pi[new_len - 2] + log_pred[new_len - 2]
        log_pi_new -= logsumexp(log_pi_new)
        log_pi = log_pi_new

        p_cp = float(np.exp(log_pi_new[0]))
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


def changepoints_from_pelt(
    feature_name: str,
    author_id: str,
    values: np.ndarray,
    timestamps: list[datetime],
    pen: float,
) -> list[ChangePoint]:
    breaks = detect_pelt(values, pen=pen)
    out: list[ChangePoint] = []
    y = np.asarray(values, dtype=float).ravel()
    for b in breaks:
        if b <= 0 or b >= len(y):
            continue
        before, after = y[:b], y[b:]
        d = cohens_d(before, after)
        m_before, m_after = float(np.mean(before)), float(np.mean(after))
        direction: str = "increase" if m_after >= m_before else "decrease"
        out.append(
            ChangePoint(
                feature_name=feature_name,
                author_id=author_id,
                timestamp=_breakpoint_timestamp(timestamps, b),
                confidence=_pelt_confidence_from_effect(d),
                method="pelt",
                effect_size_cohens_d=float(d),
                direction=direction,  # type: ignore[arg-type]
            )
        )
    return out


def changepoints_from_bocpd(
    feature_name: str,
    author_id: str,
    values: np.ndarray,
    timestamps: list[datetime],
    hazard_rate: float,
    threshold: float,
) -> list[ChangePoint]:
    raw = detect_bocpd(values, hazard_rate=hazard_rate, threshold=threshold)
    y = np.asarray(values, dtype=float).ravel()
    out: list[ChangePoint] = []
    for idx, prob in raw:
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
                confidence=float(min(1.0, max(0.0, prob))),
                method="bocpd",
                effect_size_cohens_d=float(d),
                direction=direction,  # type: ignore[arg-type]
            )
        )
    return out


def find_convergence_windows(
    change_points: list[ChangePoint],
    window_days: int = 90,
    min_features: float = 0.6,
    total_features: int | None = None,
    *,
    settings: ForensicsSettings | None = None,
) -> list[ConvergenceWindow]:
    """Bin change points into calendar windows; flag windows with enough distinct features."""
    if not change_points:
        return []
    if settings is not None:
        window_days = settings.analysis.convergence_window_days
        min_features = settings.analysis.convergence_min_feature_ratio
    total = total_features if total_features is not None else len(PELT_FEATURE_COLUMNS)
    if total <= 0:
        return []

    start_dates = sorted({cp.timestamp.date() for cp in change_points})
    windows: list[ConvergenceWindow] = []
    for start_d in start_dates:
        end_limit = start_d + timedelta(days=window_days)
        feats: set[str] = set()
        last_d = start_d
        for cp in change_points:
            d = cp.timestamp.date()
            if start_d <= d <= end_limit:
                feats.add(cp.feature_name)
                if d > last_d:
                    last_d = d
        ratio = len(feats) / float(total)
        if ratio >= min_features:
            windows.append(
                ConvergenceWindow(
                    start_date=start_d,
                    end_date=last_d,
                    features_converging=sorted(feats),
                    convergence_ratio=ratio,
                    pipeline_a_score=ratio,
                    pipeline_b_score=0.0,
                )
            )
    return windows


def _load_feature_frame(features_path: Path) -> pl.DataFrame:
    df = read_features(features_path)
    if "timestamp" not in df.columns:
        msg = f"features parquet missing timestamp: {features_path}"
        raise ValueError(msg)
    return df.sort("timestamp")


def analyze_author_feature_changepoints(
    df: pl.DataFrame,
    *,
    author_id: str,
    settings: ForensicsSettings,
) -> list[ChangePoint]:
    """Run configured changepoint methods on each numeric feature column."""
    methods = {m.lower() for m in settings.analysis.changepoint_methods}
    pen = settings.analysis.pelt_penalty
    hazard = settings.analysis.bocpd_hazard_rate
    bocpd_threshold = settings.analysis.bocpd_threshold
    out: list[ChangePoint] = []

    ts_list = df["timestamp"].to_list()
    timestamps = [parse_datetime(t) for t in ts_list]

    for col in PELT_FEATURE_COLUMNS:
        if col not in df.columns:
            continue
        series = df[col].cast(pl.Float64, strict=False).to_numpy()
        if not np.isfinite(series).all():
            series = np.nan_to_num(series, nan=np.nanmedian(series))
        if len(series) < 10:
            continue
        if "pelt" in methods:
            out.extend(changepoints_from_pelt(col, author_id, series, timestamps, pen))
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
    init_db(db_path)
    analysis_dir = project_root / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    from forensics.analysis.utils import resolve_author_rows

    with Repository(db_path) as repo:
        author_rows = resolve_author_rows(repo, settings, author_slug=author_slug)

    summary: dict[str, Any] = {"authors": [], "changepoint_files": [], "convergence_files": []}

    for author in author_rows:
        feat_path = project_root / "data" / "features" / f"{author.slug}.parquet"
        if not feat_path.is_file():
            logger.warning("Skipping author %s: missing %s", author.slug, feat_path)
            continue
        df = _load_feature_frame(feat_path)
        df_author = df.filter(pl.col("author_id") == author.id)
        if df_author.is_empty():
            df_author = df
        cps = analyze_author_feature_changepoints(df_author, author_id=author.id, settings=settings)
        conv = find_convergence_windows(
            cps,
            total_features=len(PELT_FEATURE_COLUMNS),
            settings=settings,
        )

        cp_path = analysis_dir / f"{author.slug}_changepoints.json"
        conv_path = analysis_dir / f"{author.slug}_convergence.json"
        cp_path.write_text(
            json.dumps([c.model_dump(mode="json") for c in cps], indent=2, default=str),
            encoding="utf-8",
        )
        conv_path.write_text(
            json.dumps([c.model_dump(mode="json") for c in conv], indent=2, default=str),
            encoding="utf-8",
        )
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
