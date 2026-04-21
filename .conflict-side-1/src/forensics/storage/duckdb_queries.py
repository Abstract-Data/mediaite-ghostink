"""DuckDB helpers over SQLite + Parquet (Phase 5)."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import polars as pl


def _validate_feature_name(feature_name: str) -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", feature_name):
        msg = f"Invalid feature column name: {feature_name!r}"
        raise ValueError(msg)
    return feature_name


def get_rolling_feature_comparison(
    db_path: Path,
    features_dir: Path,
    feature_name: str,
    window: int = 90,
) -> pl.DataFrame:
    """Cross-author rolling average for one feature (SQLite authors + Parquet features)."""
    col = _validate_feature_name(feature_name)
    if window < 1:
        msg = "window must be >= 1"
        raise ValueError(msg)
    pattern = str((features_dir / "*.parquet").resolve())
    db_uri = str(db_path.resolve()).replace("'", "''")
    pat_esc = pattern.replace("'", "''")
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{db_uri}' AS articles_db (TYPE sqlite)")
        sql = f"""
            SELECT
                a.name AS author,
                a.role,
                f.timestamp,
                AVG(f.{col}) OVER (
                    PARTITION BY f.author_id
                    ORDER BY f.timestamp
                    ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW
                ) AS rolling_avg
            FROM read_parquet('{pat_esc}') f
            JOIN articles_db.authors a ON f.author_id = a.id
            ORDER BY f.timestamp
        """
        return con.execute(sql).pl()
    finally:
        con.close()


def get_monthly_feature_stats(features_dir: Path, feature_name: str) -> pl.DataFrame:
    """Monthly mean and std for one feature across all Parquet shards."""
    col = _validate_feature_name(feature_name)
    pattern = str((features_dir / "*.parquet").resolve()).replace("'", "''")
    con = duckdb.connect()
    try:
        sql = f"""
            SELECT
                date_trunc('month', CAST(timestamp AS TIMESTAMP)) AS month,
                AVG(f.{col}) AS mean_{col},
                STDDEV_SAMP(f.{col}) AS std_{col},
                COUNT(*) AS n
            FROM read_parquet('{pattern}') f
            GROUP BY 1
            ORDER BY 1
        """
        return con.execute(sql).pl()
    finally:
        con.close()


def get_ai_marker_spike_detection(features_dir: Path) -> pl.DataFrame:
    """Months where ``ai_marker_frequency`` mean exceeds global mean + 2 * between-month std."""
    pattern = str((features_dir / "*.parquet").resolve()).replace("'", "''")
    con = duckdb.connect()
    try:
        sql = f"""
            WITH monthly AS (
                SELECT
                    date_trunc('month', CAST(timestamp AS TIMESTAMP)) AS month,
                    AVG(ai_marker_frequency) AS m
                FROM read_parquet('{pattern}')
                GROUP BY 1
            ),
            stats AS (
                SELECT AVG(m) AS grand_mean, STDDEV_SAMP(m) AS month_std FROM monthly
            )
            SELECT mo.month, mo.m AS monthly_mean,
                   s.grand_mean,
                   s.month_std,
                   (mo.m > s.grand_mean + 2 * COALESCE(s.month_std, 0)) AS spike
            FROM monthly mo
            CROSS JOIN stats s
            ORDER BY mo.month
        """
        return con.execute(sql).pl()
    finally:
        con.close()
