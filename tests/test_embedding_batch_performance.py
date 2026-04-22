"""Embedding batch I/O performance guards (P2-PERF-001 / Phase 5 benchmark gap)."""

from __future__ import annotations

import statistics
import time
from pathlib import Path

import numpy as np
import pytest

from forensics.storage.parquet import write_author_embedding_batch


def _median_time_batch_write(tmp_path: Path, n: int, dim: int, repeats: int) -> float:
    times: list[float] = []
    ids = [f"art-{i}" for i in range(n)]
    mat = np.random.default_rng(42).random((n, dim), dtype=np.float32)
    for _ in range(repeats):
        path = tmp_path / f"batch-{len(times)}.npz"
        t0 = time.perf_counter()
        write_author_embedding_batch(path, ids, mat)
        times.append(time.perf_counter() - t0)
    return float(statistics.median(times))


def _median_time_legacy_npy_saves(tmp_path: Path, n: int, dim: int, repeats: int) -> float:
    times: list[float] = []
    mat = np.random.default_rng(43).random((n, dim), dtype=np.float32)
    for _ in range(repeats):
        d = tmp_path / f"legacy-{len(times)}"
        d.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        for i in range(n):
            np.save(d / f"art-{i}.npy", mat[i])
        times.append(time.perf_counter() - t0)
    return float(statistics.median(times))


def test_batch_npz_faster_than_per_article_npy_writes(tmp_path: Path) -> None:
    """Regression guard: one batched write should beat N separate np.save calls."""
    n, dim, repeats = 400, 128, 5
    batch_s = _median_time_batch_write(tmp_path / "a", n, dim, repeats)
    legacy_s = _median_time_legacy_npy_saves(tmp_path / "b", n, dim, repeats)
    assert batch_s < legacy_s, (
        f"batch median {batch_s:.4f}s should be < legacy median {legacy_s:.4f}s "
        f"(n={n}, dim={dim}, repeats={repeats})"
    )


@pytest.mark.slow
def test_large_synthetic_embedding_batch_write_and_load_under_ceiling(tmp_path: Path) -> None:
    """Large-matrix write+read ceiling (opt-in slow marker)."""

    # uv run pytest tests/test_embedding_batch_performance.py -m slow --no-cov
    n, dim = 12_000, 384
    ids = [f"id-{i}" for i in range(n)]
    mat = np.random.default_rng(7).standard_normal((n, dim), dtype=np.float32)
    path = tmp_path / "big_batch.npz"

    t0 = time.perf_counter()
    write_author_embedding_batch(path, ids, mat)
    write_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    loaded = np.load(path, allow_pickle=True)
    got_ids = loaded["article_ids"]
    got_vec = loaded["vectors"]
    read_s = time.perf_counter() - t1

    assert got_vec.shape == (n, dim)
    assert len(got_ids) == n
    assert np.allclose(got_vec, mat, rtol=1e-5, atol=1e-5)

    total_s = write_s + read_s
    # Generous: cold CI runners, compressed I/O; tune only if consistently failing.
    assert total_s < 90.0, f"write+read {total_s:.1f}s exceeds ceiling (n={n}, dim={dim})"
