"""Deduplication helpers for scraped documents."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from forensics.storage.repository import Repository
from forensics.utils.hashing import simhash, simhash_hamming

logger = logging.getLogger(__name__)

_NEAR_DUP_HAMMING = 3
# For 128-bit simhash and Hamming distance <= 3, four 32-bit bands guarantee a shared band
# between any two fingerprints within threshold (pigeonhole on bit positions).
_BAND_BITS = 32
_NUM_BANDS = 4


def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _union(parent: list[int], i: int, j: int) -> None:
    ri, rj = _find(parent, i), _find(parent, j)
    if ri != rj:
        parent[rj] = ri


def _band_candidate_pairs(fingerprints: list[int]) -> set[tuple[int, int]]:
    """Indices that share at least one 32-bit band (LSH-style candidate generation)."""
    mask = (1 << _BAND_BITS) - 1
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, fp in enumerate(fingerprints):
        for band in range(_NUM_BANDS):
            band_val = (fp >> (band * _BAND_BITS)) & mask
            buckets[(band, band_val)].append(idx)
    pairs: set[tuple[int, int]] = set()
    for members in buckets.values():
        if len(members) < 2:
            continue
        ordered = sorted(members)
        for a in range(len(ordered)):
            for b in range(a + 1, len(ordered)):
                i, j = ordered[a], ordered[b]
                if i > j:
                    i, j = j, i
                pairs.add((i, j))
    return pairs


def _partition_roots(
    fingerprints: list[int], hamming_threshold: int, *, use_banding: bool
) -> tuple[int, ...]:
    """Canonical union-find root per index (for tests: banding vs brute equivalence)."""
    n = len(fingerprints)
    parent = list(range(n))
    if use_banding and hamming_threshold <= 3 and n > 0:
        candidates = _band_candidate_pairs(fingerprints)
        for i, j in candidates:
            if simhash_hamming(fingerprints[i], fingerprints[j]) <= hamming_threshold:
                _union(parent, i, j)
    else:
        for i in range(n):
            for j in range(i + 1, n):
                if simhash_hamming(fingerprints[i], fingerprints[j]) <= hamming_threshold:
                    _union(parent, i, j)
    return tuple(_find(parent, i) for i in range(n))


def deduplicate_articles(db_path: Path, *, hamming_threshold: int = _NEAR_DUP_HAMMING) -> list[str]:
    """
    Mark near-duplicate articles (simhash Hamming distance <= threshold).

    Uses union-find over the similarity graph, then keeps the earliest ``published_date``
    per component. Returns IDs that are marked duplicate (excluding canonical rows).
    """
    with Repository(db_path) as repo:
        pool_ids: list[str] = []
        pool_dates: list = []
        pool_titles: list[str] = []
        fingerprints: list[int] = []

        for aid, pub_date, title, clean_text in repo.iter_dedup_source_rows():
            pool_ids.append(aid)
            pool_dates.append(pub_date)
            pool_titles.append(title)
            fingerprints.append(simhash(clean_text))

        if not pool_ids:
            return []

        n = len(pool_ids)
        indices = list(range(n))
        parent = list(indices)

        if n > 500:
            logger.info(
                "dedup: banded simhash over %d articles (Hamming <= %s)",
                n,
                hamming_threshold,
            )

        if hamming_threshold <= 3:
            candidates = _band_candidate_pairs(fingerprints)
            for i, j in candidates:
                if simhash_hamming(fingerprints[i], fingerprints[j]) <= hamming_threshold:
                    _union(parent, i, j)
        else:
            for i in indices:
                for j in range(i + 1, n):
                    if simhash_hamming(fingerprints[i], fingerprints[j]) <= hamming_threshold:
                        _union(parent, i, j)

        groups: dict[int, list[int]] = defaultdict(list)
        for i in indices:
            groups[_find(parent, i)].append(i)

        duplicate_ids: list[str] = []
        repo.clear_duplicate_flags(pool_ids)
        for members in groups.values():
            canonical_i = min(members, key=lambda i: pool_dates[i])
            can_title = pool_titles[canonical_i]
            can_date = pool_dates[canonical_i]
            for i in members:
                if i == canonical_i:
                    continue
                art_id = pool_ids[i]
                duplicate_ids.append(art_id)
                logger.info(
                    "DUPLICATE: '%s' (%s) ≈ '%s' (%s)",
                    pool_titles[i],
                    pool_dates[i].date().isoformat(),
                    can_title,
                    can_date.date().isoformat(),
                )
        if duplicate_ids:
            repo.mark_duplicates(duplicate_ids)

        return duplicate_ids
