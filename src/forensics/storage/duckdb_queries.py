"""DuckDB helpers over SQLite + Parquet (Phase 5) plus single-file export (Phase 12 §7b)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import polars as pl

logger = logging.getLogger(__name__)


def _sql_string_literal(value: str) -> str:
    """Escape ``value`` for safe use inside a single-quoted SQL string literal."""
    return "'" + value.replace("'", "''") + "'"


def _validated_sqlite_path_for_attach(db_path: Path) -> str:
    """Resolve and validate a local SQLite file path for ``ATTACH`` (P3-SEC-002).

    DuckDB does not support bind parameters on ``ATTACH``, so paths are embedded
    as escaped string literals. This rejects control characters and obvious
    non-filesystem URI prefixes to limit injection and unexpected attach targets.
    """
    resolved = Path(db_path).expanduser().resolve(strict=True)
    if not resolved.is_file():
        msg = f"SQLite attach path must be an existing file: {db_path}"
        raise ValueError(msg)
    raw = str(resolved)
    if "\x00" in raw or "\n" in raw or "\r" in raw:
        msg = "SQLite attach path contains invalid control characters"
        raise ValueError(msg)
    lower = raw.lower()
    for prefix in ("http://", "https://", "s3://", "memory:", ":memory:", "duckdb:"):
        if lower.startswith(prefix):
            msg = f"Unsupported SQLite attach source (local files only): {raw!r}"
            raise ValueError(msg)
    return _sql_string_literal(raw)


def _validate_feature_name(feature_name: str) -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", feature_name):
        msg = f"Invalid feature column name: {feature_name!r}"
        raise ValueError(msg)
    return feature_name


_FORBIDDEN_PATH_PREFIXES: tuple[str, ...] = (
    "http://",
    "https://",
    "s3://",
    "gs://",
    "azure://",
    "hf://",
    "duckdb:",
    "memory:",
    ":memory:",
)


def _validated_parquet_pattern(pattern: str | Path) -> str:
    """Return a SQL-safe literal for a Parquet glob pattern (P1-SEC-001).

    DuckDB does not support bind parameters inside ``read_parquet('...')`` so
    the pattern is inlined as a string literal. This rejects control
    characters and non-local URI prefixes to prevent crafted paths from
    pivoting DuckDB into a remote reader, then delegates to
    :func:`_sql_string_literal` for quote escaping.
    """
    raw = str(pattern)
    if not raw:
        msg = "Parquet pattern must not be empty"
        raise ValueError(msg)
    if "\x00" in raw or "\n" in raw or "\r" in raw:
        msg = "Parquet pattern contains invalid control characters"
        raise ValueError(msg)
    lower = raw.lower()
    for prefix in _FORBIDDEN_PATH_PREFIXES:
        if lower.startswith(prefix):
            msg = f"Unsupported Parquet source (local files only): {raw!r}"
            raise ValueError(msg)
    return _sql_string_literal(raw)


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
    pattern = (features_dir / "*.parquet").resolve()
    db_lit = _validated_sqlite_path_for_attach(db_path)
    pat_lit = _validated_parquet_pattern(pattern)
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH {db_lit} AS articles_db (TYPE sqlite, READ_ONLY)")
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
            FROM read_parquet({pat_lit}) f
            JOIN articles_db.authors a ON f.author_id = a.id
            ORDER BY f.timestamp
        """
        return con.execute(sql).pl()
    finally:
        con.close()


def get_monthly_feature_stats(features_dir: Path, feature_name: str) -> pl.DataFrame:
    """Monthly mean and std for one feature across all Parquet shards."""
    col = _validate_feature_name(feature_name)
    pat_lit = _validated_parquet_pattern((features_dir / "*.parquet").resolve())
    con = duckdb.connect()
    try:
        sql = f"""
            SELECT
                date_trunc('month', CAST(timestamp AS TIMESTAMP)) AS month,
                AVG(f.{col}) AS mean_{col},
                STDDEV_SAMP(f.{col}) AS std_{col},
                COUNT(*) AS n
            FROM read_parquet({pat_lit}) f
            GROUP BY 1
            ORDER BY 1
        """
        return con.execute(sql).pl()
    finally:
        con.close()


def get_ai_marker_spike_detection(features_dir: Path) -> pl.DataFrame:
    """Months where ``ai_marker_frequency`` mean exceeds global mean + 2 * between-month std."""
    pat_lit = _validated_parquet_pattern((features_dir / "*.parquet").resolve())
    con = duckdb.connect()
    try:
        sql = f"""
            WITH monthly AS (
                SELECT
                    date_trunc('month', CAST(timestamp AS TIMESTAMP)) AS month,
                    AVG(ai_marker_frequency) AS m
                FROM read_parquet({pat_lit})
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


# ---------------------------------------------------------------------------
# Single-file DuckDB export (Phase 12 §7b)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExportReport:
    """Summary of a :func:`export_to_duckdb` run.

    ``tables`` maps table name to row count; tables that were skipped (because
    their source artifacts were absent) are simply omitted.
    """

    output_path: Path
    bytes_written: int
    tables: dict[str, int]

    @property
    def total_rows(self) -> int:
        return sum(self.tables.values())


def export_to_duckdb(
    db_path: Path,
    output: Path,
    *,
    include_features: bool = True,
    include_analysis: bool = True,
) -> ExportReport:
    """Export the forensic corpus into a single DuckDB file for ad-hoc team queries.

    Reads ``articles`` and ``authors`` directly from the SQLite ``articles.db``
    via DuckDB's ``sqlite`` extension. Optionally folds in the Parquet feature
    shards under ``data/features/`` as a ``features`` table and the per-author
    ``*_result.json`` analysis artifacts under ``data/analysis/`` as an
    ``analysis_results`` table.

    The output is a single ``.duckdb`` file; no Parquet pipeline is involved.

    Parameters
    ----------
    db_path:
        SQLite ``articles.db`` source (must exist).
    output:
        Destination ``.duckdb`` path. Overwritten if present.
    include_features:
        When True, attempts to read ``<project_root>/data/features/*.parquet``
        (derived from ``db_path.parent``). Skipped silently if no shards exist.
    include_analysis:
        When True, attempts to read ``<project_root>/data/analysis/*_result.json``.
        Skipped silently if no files exist.
    """
    sqlite_path = Path(db_path).expanduser().resolve(strict=True)
    if not sqlite_path.is_file():
        msg = f"SQLite source not found: {sqlite_path}"
        raise FileNotFoundError(msg)

    out_path = Path(output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    data_dir = sqlite_path.parent
    features_dir = data_dir / "features"
    analysis_dir = data_dir / "analysis"

    tables: dict[str, int] = {}
    con = duckdb.connect(str(out_path))
    try:
        con.execute("INSTALL sqlite")
        con.execute("LOAD sqlite")
        db_lit = _validated_sqlite_path_for_attach(sqlite_path)
        con.execute(f"ATTACH {db_lit} AS src (TYPE sqlite, READ_ONLY)")
        try:
            con.execute("CREATE TABLE authors AS SELECT * FROM src.authors")
            con.execute("CREATE TABLE articles AS SELECT * FROM src.articles")
            tables["authors"] = con.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
            tables["articles"] = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        finally:
            con.execute("DETACH src")

        if include_features and features_dir.is_dir():
            parquets = sorted(features_dir.glob("*.parquet"))
            if parquets:
                pat_lit = _validated_parquet_pattern((features_dir / "*.parquet").resolve())
                con.execute(
                    f"""
                    CREATE TABLE features AS
                    SELECT * FROM read_parquet({pat_lit}, union_by_name=true)
                    """
                )
                tables["features"] = con.execute("SELECT COUNT(*) FROM features").fetchone()[0]
            else:
                logger.info("No feature parquet shards found at %s; skipping.", features_dir)

        if include_analysis and analysis_dir.is_dir():
            rows = _collect_analysis_rows(analysis_dir)
            if rows:
                _register_analysis_results(con, rows)
                tables["analysis_results"] = len(rows)
            else:
                logger.info("No analysis *_result.json files at %s; skipping.", analysis_dir)
    finally:
        con.close()

    size = out_path.stat().st_size if out_path.exists() else 0
    report = ExportReport(output_path=out_path, bytes_written=size, tables=dict(tables))
    logger.info(
        "DuckDB export complete: %s (%d bytes, %d rows across %d tables)",
        out_path,
        size,
        report.total_rows,
        len(tables),
    )
    return report


def _collect_analysis_rows(analysis_dir: Path) -> list[dict[str, object]]:
    """Flatten per-author ``*_result.json`` files into one row per author."""
    rows: list[dict[str, object]] = []
    for path in sorted(analysis_dir.glob("*_result.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping unreadable analysis file %s: %s", path, exc)
            continue
        if not isinstance(payload, dict):
            logger.warning("Skipping non-object analysis payload at %s", path)
            continue
        rows.append(
            {
                "author_id": str(payload.get("author_id", "")),
                "run_id": str(payload.get("run_id", "")),
                "run_timestamp": str(payload.get("run_timestamp", "")),
                "config_hash": str(payload.get("config_hash", "")),
                "change_points_json": json.dumps(payload.get("change_points", [])),
                "convergence_windows_json": json.dumps(payload.get("convergence_windows", [])),
                "drift_scores_json": json.dumps(payload.get("drift_scores")),
                "hypothesis_tests_json": json.dumps(payload.get("hypothesis_tests", [])),
                "source_file": path.name,
            }
        )
    return rows


def _register_analysis_results(
    con: duckdb.DuckDBPyConnection, rows: list[dict[str, object]]
) -> None:
    """Create ``analysis_results`` in ``con`` from flattened per-author rows."""
    df = pl.DataFrame(rows)
    con.register("analysis_results_src", df)
    try:
        con.execute("CREATE TABLE analysis_results AS SELECT * FROM analysis_results_src")
    finally:
        con.unregister("analysis_results_src")
