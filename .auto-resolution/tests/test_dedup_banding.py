"""Banded simhash candidate generation matches brute-force union-find (P1-PERF-1)."""

from __future__ import annotations

import random

import pytest

from forensics.scraper.dedup import _partition_roots


@pytest.mark.parametrize("seed", range(30))
def test_banded_partition_matches_brute_random_fingerprints(seed: int) -> None:
    rng = random.Random(seed)
    n = rng.randint(2, 50)
    fingerprints = [rng.getrandbits(128) for _ in range(n)]
    for hamming_threshold in range(0, 4):
        banded = _partition_roots(fingerprints, hamming_threshold, use_banding=True)
        brute = _partition_roots(fingerprints, hamming_threshold, use_banding=False)
        assert banded == brute, (seed, hamming_threshold, n)
