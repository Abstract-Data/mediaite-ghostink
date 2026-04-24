"""Security-focused tests for DuckDB path/pattern validators (F1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from forensics.storage.duckdb_queries import (
    _sql_string_literal,
    _validate_feature_name,
    _validated_parquet_pattern,
    _validated_sqlite_path_for_attach,
)

# ---------------------------------------------------------------------------
# _sql_string_literal
# ---------------------------------------------------------------------------


def test_sql_string_literal_doubles_embedded_quotes() -> None:
    assert _sql_string_literal("foo") == "'foo'"
    assert _sql_string_literal("O'Brien") == "'O''Brien'"
    assert _sql_string_literal("a'b'c") == "'a''b''c'"


# ---------------------------------------------------------------------------
# _validated_sqlite_path_for_attach
# ---------------------------------------------------------------------------


def test_validated_sqlite_path_accepts_existing_file(tmp_path: Path) -> None:
    db = tmp_path / "articles.db"
    db.write_bytes(b"")
    lit = _validated_sqlite_path_for_attach(db)
    assert lit.startswith("'") and lit.endswith("'")
    assert str(db.resolve()) in lit


def test_validated_sqlite_path_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _validated_sqlite_path_for_attach(tmp_path / "does-not-exist.db")


def test_validated_sqlite_path_rejects_directory(tmp_path: Path) -> None:
    # tmp_path itself is a directory — resolve succeeds but is_file fails.
    with pytest.raises(ValueError, match="existing file"):
        _validated_sqlite_path_for_attach(tmp_path)


def test_validated_sqlite_path_escapes_single_quotes(tmp_path: Path) -> None:
    weird = tmp_path / "o'brien.db"
    weird.write_bytes(b"")
    lit = _validated_sqlite_path_for_attach(weird)
    # Single quote in filename must be SQL-escaped.
    assert "''" in lit


# ---------------------------------------------------------------------------
# _validated_parquet_pattern
# ---------------------------------------------------------------------------


def test_validated_parquet_pattern_accepts_plain_glob(tmp_path: Path) -> None:
    pattern = tmp_path / "*.parquet"
    lit = _validated_parquet_pattern(pattern)
    assert str(pattern) in lit


def test_validated_parquet_pattern_rejects_empty() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        _validated_parquet_pattern("")


@pytest.mark.parametrize(
    "bad",
    [
        "http://evil/data.parquet",
        "https://evil/data.parquet",
        "s3://bucket/x.parquet",
        "gs://bucket/x.parquet",
        "azure://container/x.parquet",
        "hf://dataset/x.parquet",
        "duckdb:remote",
        "memory:foo",
        ":memory:",
    ],
)
def test_validated_parquet_pattern_rejects_remote_uris(bad: str) -> None:
    with pytest.raises(ValueError, match="local files only"):
        _validated_parquet_pattern(bad)


@pytest.mark.parametrize("ctrl", ["\x00", "\n", "\r"])
def test_validated_parquet_pattern_rejects_control_chars(tmp_path: Path, ctrl: str) -> None:
    with pytest.raises(ValueError, match="control characters"):
        _validated_parquet_pattern(str(tmp_path / f"x{ctrl}y.parquet"))


def test_validated_parquet_pattern_escapes_single_quotes(tmp_path: Path) -> None:
    pattern = tmp_path / "o'brien-*.parquet"
    lit = _validated_parquet_pattern(pattern)
    assert "''" in lit


# ---------------------------------------------------------------------------
# _validate_feature_name (SQL-column injection guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["ttr", "mattr_30d", "_private", "col0", "x_y_z"])
def test_validate_feature_name_accepts_identifiers(name: str) -> None:
    assert _validate_feature_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "1starts_with_digit",
        "has space",
        "has-dash",
        "semi;colon",
        "ttr; DROP TABLE authors",
        "",
        "utf8-π",
    ],
)
def test_validate_feature_name_rejects_invalid_identifiers(name: str) -> None:
    with pytest.raises(ValueError, match="Invalid feature column name"):
        _validate_feature_name(name)
