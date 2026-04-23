"""Unit tests for DuckDB Parquet-pattern validation (D1 / P1-SEC-001)."""

from __future__ import annotations

import pytest

from forensics.storage.duckdb_queries import _validated_parquet_pattern


def test_validated_parquet_pattern_accepts_plain_path() -> None:
    out = _validated_parquet_pattern("/tmp/data/features/*.parquet")
    # Wrapped in single quotes for safe inlining.
    assert out.startswith("'/tmp/data/features/") and out.endswith(".parquet'")


def test_validated_parquet_pattern_escapes_single_quotes() -> None:
    out = _validated_parquet_pattern("/path/with'quote/*.parquet")
    assert "''" in out  # escaped single quote


@pytest.mark.parametrize(
    "bad",
    [
        "http://evil/a.parquet",
        "https://evil/a.parquet",
        "s3://bucket/a.parquet",
        "hf://model/a.parquet",
        "duckdb:evil",
        "memory:bad",
    ],
)
def test_validated_parquet_pattern_rejects_remote_uri(bad: str) -> None:
    with pytest.raises(ValueError):
        _validated_parquet_pattern(bad)


@pytest.mark.parametrize("ctl", ["\x00", "\n", "\r"])
def test_validated_parquet_pattern_rejects_control_chars(ctl: str) -> None:
    with pytest.raises(ValueError):
        _validated_parquet_pattern(f"/tmp/{ctl}/a.parquet")


def test_validated_parquet_pattern_rejects_empty() -> None:
    with pytest.raises(ValueError):
        _validated_parquet_pattern("")
