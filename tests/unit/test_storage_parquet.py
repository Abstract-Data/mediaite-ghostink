"""Parquet storage helpers (PR94 merge metadata atomicity)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import polars as pl
import pyarrow.parquet as pq
import pytest

from forensics.storage.parquet import merge_parquet_metadata


def test_merge_parquet_metadata_atomic_success(tmp_path: Path) -> None:
    path = tmp_path / "f.parquet"
    pl.DataFrame({"a": [1]}).write_parquet(path)
    merge_parquet_metadata(path, {"forensics.ai_marker_list_version": "9.9.9"})
    meta = pq.read_metadata(path).metadata or {}
    assert meta[b"forensics.ai_marker_list_version"] == b"9.9.9"
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_merge_parquet_metadata_atomic_rollback_on_write_failure(tmp_path: Path) -> None:
    path = tmp_path / "f.parquet"
    pl.DataFrame({"a": [1]}).write_parquet(path)
    before = path.read_bytes()
    tmp = path.with_suffix(path.suffix + ".tmp")

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    with patch("pyarrow.parquet.write_table", side_effect=boom):
        with pytest.raises(OSError, match="disk full"):
            merge_parquet_metadata(path, {"forensics.ai_marker_list_version": "1"})
    assert path.read_bytes() == before
    assert not tmp.exists()
