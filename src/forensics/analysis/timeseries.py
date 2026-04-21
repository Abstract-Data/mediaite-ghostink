"""Rolling statistics, STL-style decomposition, Chow, CUSUM, burst heuristics (Phase 5)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS
from forensics.config.settings import ForensicsSettings
from forensics.storage.parquet import read_features
from forensics.storage.repository import Repository, init_db
from forensics.utils.datetime import parse_datetime

logger = logging.getLogger(__name__)


def compute_rolling_stats(
    timestamps: list[datetime],
    values: list[float],
    windows: list[int] | None = None,
) -> dict[int, dict[str, Any]]:
    """Rolling mean, std, and approximate 95% bands per window size (Polars)."""
    wdef = windows if windows is not None else [30, 90]
    if not timestamps or not values:
        return {w: {"mean": [], "std": [], "low95": [], "high95": []} for w in wdef}
    df = pl.DataFrame({"timestamp": timestamps, "value": values}).sort("timestamp")
    out: dict[int, dict[str, Any]] = {}
    for w in wdef:
        if w < 2:
            continue
        rolled = df.with_columns(
            [
                pl.col("value").rolling_mean(window_size=w, min_samples=1).alias("mean"),
                pl.col("value").rolling_std(window_size=w, min_samples=1).alias("std"),
            ]
        )
        mean = rolled["mean"].to_list()
        std = [float(s) if s is not None else 0.0 for s in rolled["std"].to_list()]
        low = [float(m - 1.96 * s) for m, s in zip(mean, std, strict=False)]
        high = [float(m + 1.96 * s) for m, s in zip(mean, std, strict=False)]
        out[w] = {
            "mean": [float(x) if x is not None else float("nan") for x in mean],
            "std": std,
            "low95": low,
            "high95": high,
        }
    return out


def stl_decompose(
    timestamps: list[datetime],
    values: list[float],
    period: int = 30,
) -> dict[str, list[float]]:
    """Trend / seasonal / residual via rolling trend + cyclic seasonal (no statsmodels)."""
    y = np.asarray(values, dtype=float).ravel()
    n = len(y)
    if n == 0:
        return {"trend": [], "seasonal": [], "residual": []}
    p = max(3, min(period, max(3, n // 2)))
    kernel = np.ones(p) / p
    pad = p // 2
    ext = np.pad(y, (pad, pad), mode="edge")
    trend = np.convolve(ext, kernel, mode="valid")
    if trend.size > n:
        trend = trend[:n]
    elif trend.size < n:
        trend = np.pad(trend, (0, n - trend.size), mode="edge")
    detrended = y - trend[:n]
    seasonal = np.zeros(n)
    for i in range(n):
        pos = i % p
        mask = np.arange(n)[(np.arange(n) % p) == pos]
        seasonal[i] = float(np.mean(detrended[mask])) if mask.size else 0.0
    residual = (y - trend[:n] - seasonal).tolist()
    return {
        "trend": trend[:n].tolist(),
        "seasonal": seasonal.tolist(),
        "residual": residual,
    }


def chow_test(values: list[float], breakpoint_idx: int) -> tuple[float, float]:
    """Chow F-test for a break in linear trend (intercept + slope on time index)."""
    from scipy.stats import f as f_dist

    y = np.asarray(values, dtype=float).ravel()
    n = y.size
    k = 2
    b = int(breakpoint_idx)
    if n < 2 * k + 2 or b < k or n - b < k:
        return 0.0, 1.0
    t = np.arange(n, dtype=float)
    x_design = np.column_stack([np.ones(n), t])

    def rss(seg: slice) -> float:
        yy = y[seg]
        xx = x_design[seg]
        if yy.size < k:
            return float(np.sum(yy**2))
        beta, *_ = np.linalg.lstsq(xx, yy, rcond=None)
        pred = xx @ beta
        return float(np.sum((yy - pred) ** 2))

    rss_p = rss(slice(None))
    rss_1 = rss(slice(0, b))
    rss_2 = rss(slice(b, None))
    num = (rss_p - rss_1 - rss_2) / k
    den = (rss_1 + rss_2) / (n - 2 * k)
    if den <= 0 or not np.isfinite(den):
        return 0.0, 1.0
    f_stat = num / den
    df1, df2 = k, n - 2 * k
    p_val = float(1.0 - f_dist.cdf(f_stat, df1, df2))
    return float(f_stat), p_val


def cusum_test(
    values: list[float],
    threshold: float = 4.0,
) -> list[tuple[int, float]]:
    """Two-sided CUSUM on deviations from an in-control mean (head of series)."""
    y = np.asarray(values, dtype=float).ravel()
    n = len(y)
    if n < 2:
        return []
    k0 = min(20, max(5, n // 4))
    mean = float(np.mean(y[:k0]))
    cusum_pos = np.zeros(n)
    cusum_neg = np.zeros(n)
    out: list[tuple[int, float]] = []
    half = threshold / 2.0
    for i in range(1, n):
        cusum_pos[i] = max(0.0, cusum_pos[i - 1] + y[i] - mean - half)
        cusum_neg[i] = max(0.0, cusum_neg[i - 1] - y[i] + mean - half)
        v = max(cusum_pos[i], cusum_neg[i])
        if v > threshold:
            out.append((i, float(v)))
    return out


def detect_bursts(
    timestamps: list[datetime],
    s: float = 2.0,
) -> list[tuple[datetime, datetime, int]]:
    """Heuristic burst windows from inter-arrival gaps (Kleinberg-style intensity levels)."""
    if len(timestamps) < 3:
        return []
    ts = sorted(parse_datetime(t) if not isinstance(t, datetime) else t for t in timestamps)
    gaps = np.diff([t.timestamp() for t in ts])
    if gaps.size == 0:
        return []
    med = float(np.median(gaps))
    if med <= 0:
        med = 1.0
    bursts: list[tuple[datetime, datetime, int]] = []
    i = 0
    while i < len(gaps):
        if gaps[i] < med / s:
            j = i
            while j < len(gaps) and gaps[j] < med / s:
                j += 1
            level = 2 if np.mean(gaps[i:j]) < med / (s * 1.5) else 1
            bursts.append((ts[i], ts[min(j, len(ts) - 1)], level))
            i = j + 1
        else:
            i += 1
    return bursts


def run_timeseries_analysis(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    project_root: Path,
    author_slug: str | None = None,
) -> dict[str, Any]:
    """Write ``data/analysis/{slug}_timeseries.parquet`` with rolling + STL per numeric feature."""
    init_db(db_path)
    repo = Repository(db_path)
    analysis_dir = project_root / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    windows = settings.analysis.rolling_windows or [30, 90]

    if author_slug:
        au = repo.get_author_by_slug(author_slug)
        if au is None:
            msg = f"Unknown author slug: {author_slug}"
            raise ValueError(msg)
        author_rows = [au]
    else:
        author_rows = []
        for a in settings.authors:
            au = repo.get_author_by_slug(a.slug)
            if au is not None:
                author_rows.append(au)

    summary: dict[str, Any] = {"authors": [], "timeseries_files": []}
    numeric_cols = list(PELT_FEATURE_COLUMNS)

    for author in author_rows:
        feat_path = project_root / "data" / "features" / f"{author.slug}.parquet"
        if not feat_path.is_file():
            logger.warning("Skipping timeseries for %s: missing %s", author.slug, feat_path)
            continue
        df = read_features(feat_path).sort("timestamp")
        df_a = df.filter(pl.col("author_id") == author.id)
        if df_a.is_empty():
            df_a = df
        ts_list = df_a["timestamp"].to_list()
        timestamps = [parse_datetime(t) for t in ts_list]
        rows: list[dict[str, Any]] = []
        for col in numeric_cols:
            if col not in df_a.columns:
                continue
            vals = df_a[col].cast(pl.Float64, strict=False).to_list()
            floats = [float(v) if v is not None else float("nan") for v in vals]
            if not floats:
                continue
            roll = compute_rolling_stats(timestamps, floats, windows=windows)
            stl = stl_decompose(timestamps, floats, period=min(30, max(3, len(floats) // 3)))
            for i in range(len(timestamps)):
                rec: dict[str, Any] = {
                    "author_id": author.id,
                    "feature": col,
                    "timestamp": timestamps[i].isoformat(),
                    "value": floats[i],
                }
                for w, parts in roll.items():
                    rec[f"rolling_{w}d_mean"] = parts["mean"][i] if i < len(parts["mean"]) else None
                    rec[f"rolling_{w}d_std"] = parts["std"][i] if i < len(parts["std"]) else None
                rec["stl_trend"] = stl["trend"][i] if i < len(stl["trend"]) else None
                rec["stl_seasonal"] = stl["seasonal"][i] if i < len(stl["seasonal"]) else None
                rec["stl_residual"] = stl["residual"][i] if i < len(stl["residual"]) else None
                rows.append(rec)

        out_path = analysis_dir / f"{author.slug}_timeseries.parquet"
        if rows:
            pl.DataFrame(rows).write_parquet(out_path)
        else:
            pl.DataFrame(
                {
                    "author_id": [],
                    "feature": [],
                    "timestamp": [],
                    "value": [],
                }
            ).write_parquet(out_path)
        summary["authors"].append(author.slug)
        summary["timeseries_files"].append(str(out_path))
        pub_ts = [parse_datetime(t) for t in ts_list]
        burst_path = analysis_dir / f"{author.slug}_bursts.json"
        bursts = detect_bursts(pub_ts, s=2.0)
        burst_path.write_text(
            json.dumps(
                [
                    {"start": a.isoformat(), "end": b.isoformat(), "level": lev}
                    for a, b, lev in bursts
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("timeseries: author=%s wrote %s", author.slug, out_path)

    return summary
