"""Property-based checks for hashing helpers (P3-TEST-001)."""

from __future__ import annotations

import pytest
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


@pytest.mark.parametrize("hashbits", [64, 128, 192, 256])
def test_simhash_supports_up_to_256_bits(hashbits: int) -> None:
    """``hashbits`` up to 256 is accepted (extended via a second xxh128 seed)."""
    fp = simhash("quick brown fox over the lazy dog", hashbits=hashbits)
    assert 0 <= fp < (1 << hashbits)


@pytest.mark.parametrize("bad", [0, -1, 257, 1000])
def test_simhash_rejects_out_of_range_hashbits(bad: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 256"):
        simhash("sample", hashbits=bad)


def test_simhash_high_bits_differ_between_128_and_256() -> None:
    """The 129..256 bits come from a second seed, so extending to 256 changes the value."""
    text = "some-sample-text"
    fp128 = simhash(text, hashbits=128)
    fp256 = simhash(text, hashbits=256)
    assert fp128 != fp256  # extra 128 bits of entropy must show up
