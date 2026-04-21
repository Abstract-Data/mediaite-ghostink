"""Property-based checks for hashing helpers (P3-TEST-3)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from forensics.utils.hashing import simhash, simhash_hamming


@given(st.text(min_size=1, max_size=400))
def test_simhash_self_distance_zero(text: str) -> None:
    fp = simhash(text)
    assert simhash_hamming(fp, fp) == 0


@given(st.text(min_size=3, max_size=200), st.text(min_size=3, max_size=200))
def test_simhash_symmetric_distance(a: str, b: str) -> None:
    fa, fb = simhash(a), simhash(b)
    assert simhash_hamming(fa, fb) == simhash_hamming(fb, fa)
