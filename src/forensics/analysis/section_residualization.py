"""Section-residualized feature frames for sensitivity analysis."""

from __future__ import annotations

import logging

import polars as pl

from forensics.utils.url import section_from_url

logger = logging.getLogger(__name__)

__all__ = ["residualize_features_by_section"]


def _frame_with_section(df: pl.DataFrame) -> pl.DataFrame | None:
    if "section" in df.columns:
        return df
    if "url" not in df.columns:
        return None
    return df.with_columns(
        pl.col("url")
        .cast(pl.Utf8, strict=False)
        .map_elements(section_from_url, return_dtype=pl.Utf8)
        .alias("section")
    )


def residualize_features_by_section(
    df: pl.DataFrame,
    *,
    feature_columns: list[str],
    min_articles_per_section: int,
) -> pl.DataFrame:
    """Subtract section means while preserving each feature's global mean."""
    with_section = _frame_with_section(df)
    if with_section is None or "section" not in with_section.columns:
        logger.info("section residualization skipped: no section or url column")
        return df

    eligible_sections = (
        with_section.group_by("section")
        .len()
        .filter(pl.col("len") >= min_articles_per_section)
        .get_column("section")
        .to_list()
    )
    if len(eligible_sections) < 2:
        logger.info(
            "section residualization skipped: only %d eligible section(s)",
            len(eligible_sections),
        )
        return df

    columns = [col for col in feature_columns if col in with_section.columns]
    if not columns:
        return df

    residualized = with_section
    eligible_mask = pl.col("section").is_in(eligible_sections)
    for col in columns:
        global_mean = pl.col(col).cast(pl.Float64, strict=False).mean()
        section_mean = pl.col(col).cast(pl.Float64, strict=False).mean().over("section")
        residual_expr = pl.col(col).cast(pl.Float64, strict=False) - section_mean + global_mean
        residualized = residualized.with_columns(
            pl.when(eligible_mask)
            .then(residual_expr)
            .otherwise(pl.col(col).cast(pl.Float64, strict=False))
            .alias(col)
        )
    return residualized
