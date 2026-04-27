"""Load monthly :class:`ProbabilityTrajectory` series for Pipeline C (Phase 9).

Article-level perplexity / burstiness (and optional Binoculars) may live either on
the per-author feature parquet under ``paths.features_dir`` (when those columns
are present) or in ``<project_root>/data/probability/<slug>.parquet`` after
``forensics extract --probability``. Analyze aggregates both sources to monthly
``YYYY-MM`` tuples expected by :func:`compute_probability_pipeline_score`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import polars as pl

from forensics.analysis.convergence import ProbabilityTrajectory
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.parquet import SchemaMigrationRequired, load_feature_frame_sorted

logger = logging.getLogger(__name__)

_REQUIRED = ("mean_perplexity", "perplexity_variance")


def _schema_has_probability(names: set[str]) -> bool:
    return all(c in names for c in _REQUIRED)


def _aggregated_trajectory(df: pl.DataFrame) -> ProbabilityTrajectory | None:
    """Reduce article-level rows to sorted monthly means for convergence."""
    if df.is_empty() or not _schema_has_probability(set(df.columns)):
        return None

    cols = set(df.columns)
    if "timestamp" in cols:
        month_expr = pl.col("timestamp").dt.strftime("%Y-%m")
    elif "publish_date" in cols:
        month_expr = pl.col("publish_date").cast(pl.Date).dt.strftime("%Y-%m")
    else:
        logger.warning(
            "probability_trajectories: missing timestamp/publish_date; cannot build monthly keys"
        )
        return None

    # Monthly ``avg_ppl`` / ``avg_var`` are unweighted means over articles in
    # that calendar month (equal weight per article, not token-weighted).
    agg_exprs: list[pl.Expr] = [
        pl.col("mean_perplexity").mean().alias("avg_ppl"),
        pl.col("perplexity_variance").mean().alias("avg_var"),
    ]
    has_binoculars = "binoculars_score" in cols
    if has_binoculars:
        agg_exprs.append(pl.col("binoculars_score").mean().alias("avg_bx"))

    grouped = (
        df.lazy()
        .with_columns(month_expr.alias("month_key"))
        .group_by("month_key")
        .agg(agg_exprs)
        .sort("month_key")
        .collect()
    )
    months = grouped["month_key"].to_list()
    monthly_perplexity = list(
        zip(months, grouped["avg_ppl"].cast(pl.Float64).to_list(), strict=True)
    )
    monthly_burstiness = list(
        zip(months, grouped["avg_var"].cast(pl.Float64).to_list(), strict=True)
    )

    monthly_binoculars: list[tuple[str, float]] | None = None
    if has_binoculars and "avg_bx" in grouped.columns:
        bx_vals = grouped["avg_bx"]
        pairs: list[tuple[str, float]] = []
        for m, v in zip(months, bx_vals.to_list(), strict=True):
            if v is None:  # Sparse Binoculars months are OK; series need not align ppl/bx lengths.
                continue
            vf = float(v)
            pairs.append((m, vf))
        monthly_binoculars = pairs or None

    return ProbabilityTrajectory(
        monthly_perplexity=monthly_perplexity,
        monthly_burstiness=monthly_burstiness,
        monthly_binoculars=monthly_binoculars,
    )


def _load_article_probability_frame(paths: AnalysisArtifactPaths, slug: str) -> pl.DataFrame | None:
    """Prefer feature parquet with probability columns; else ``data/probability/<slug>.parquet``."""
    feat_path = paths.features_parquet(slug)
    if feat_path.is_file():
        try:
            lf = load_feature_frame_sorted(feat_path)
            names = set(lf.collect_schema().names())
            if _schema_has_probability(names):
                want = [
                    c
                    for c in (
                        "timestamp",
                        "publish_date",
                        "mean_perplexity",
                        "perplexity_variance",
                        "binoculars_score",
                    )
                    if c in names
                ]
                if "timestamp" not in want and "publish_date" not in want:
                    return None
                return lf.select(want).collect()
        except (OSError, ValueError, SchemaMigrationRequired) as exc:
            logger.debug(
                "probability_trajectories: could not scan feature parquet for slug=%s (%s)",
                slug,
                exc,
            )

    prob_path = paths.project_root / "data" / "probability" / f"{slug}.parquet"
    if not prob_path.is_file():
        return None
    try:
        df = pl.read_parquet(prob_path)
    except OSError as exc:
        logger.warning("probability_trajectories: unreadable %s (%s)", prob_path, exc)
        return None
    if not _schema_has_probability(set(df.columns)):
        return None
    return df


def build_probability_trajectory_by_slug(
    paths: AnalysisArtifactPaths,
    author_slugs: Sequence[str],
) -> dict[str, ProbabilityTrajectory]:
    """Build a slug → trajectory map for every slug that has usable probability rows."""
    out: dict[str, ProbabilityTrajectory] = {}
    for slug in author_slugs:
        df = _load_article_probability_frame(paths, slug)
        if df is None:
            continue
        traj = _aggregated_trajectory(df)
        if traj is not None:
            out[slug] = traj
    return out


__all__ = ["build_probability_trajectory_by_slug"]
