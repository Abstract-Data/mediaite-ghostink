"""Property-based checks for embedding batch UTF-8 id packing (P3-TEST-003)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from forensics.storage.parquet import (
    unpack_article_ids_from_embedding_batch,
    write_author_embedding_batch,
)


@settings(max_examples=25, deadline=None)
@given(
    n=st.integers(min_value=1, max_value=14),
    dim=st.integers(min_value=1, max_value=24),
    data=st.data(),
)
def test_write_author_embedding_batch_roundtrip_numeric_ids(
    n: int,
    dim: int,
    data: st.DataObject,
) -> None:
    """ASCII ids + finite float rows survive ``savez`` and ``allow_pickle=False`` reload."""
    ids = [f"id-{i}" for i in range(n)]
    rows: list[list[float]] = []
    for _ in range(n):
        rows.append(
            [
                data.draw(
                    st.floats(
                        min_value=-1e3,
                        max_value=1e3,
                        allow_nan=False,
                        allow_infinity=False,
                    )
                )
                for _ in range(dim)
            ]
        )
    mat = np.asarray(rows, dtype=np.float32)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "batch.npz"
        write_author_embedding_batch(path, ids, mat)
        z = np.load(path, allow_pickle=False)
        got = unpack_article_ids_from_embedding_batch(
            z["article_id_lengths"],
            z["article_id_bytes"],
        )
        assert got == ids
        assert np.allclose(np.asarray(z["vectors"], dtype=np.float32), mat)


@settings(max_examples=20, deadline=None)
@given(
    id_texts=st.lists(
        st.text(
            st.characters(
                codec="utf-8",
                min_codepoint=1,
                max_codepoint=0xFFFF,
                blacklist_categories=("Cs",),
            ),
            min_size=1,
            max_size=12,
        ),
        min_size=1,
        max_size=6,
        unique=True,
    ),
    dim=st.integers(min_value=1, max_value=12),
    data=st.data(),
)
def test_write_author_embedding_batch_roundtrip_unicode_ids(
    id_texts: list[str],
    dim: int,
    data: st.DataObject,
) -> None:
    n = len(id_texts)
    rows: list[list[float]] = []
    for _ in range(n):
        rows.append(
            [
                data.draw(
                    st.floats(
                        min_value=-500.0,
                        max_value=500.0,
                        allow_nan=False,
                        allow_infinity=False,
                    )
                )
                for _ in range(dim)
            ]
        )
    mat = np.asarray(rows, dtype=np.float32)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "unicode.npz"
        write_author_embedding_batch(path, id_texts, mat)
        z = np.load(path, allow_pickle=False)
        got = unpack_article_ids_from_embedding_batch(
            z["article_id_lengths"],
            z["article_id_bytes"],
        )
        assert got == id_texts
        assert np.allclose(np.asarray(z["vectors"], dtype=np.float32), mat)
