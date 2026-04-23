"""Content fingerprints for deduplication."""

from __future__ import annotations

import hashlib

import xxhash


def content_hash(text: str) -> str:
    """SHA-256 hex digest of the normalized string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def simhash_hamming(a: int, b: int) -> int:
    """Hamming distance between two simhash fingerprints."""
    return (a ^ b).bit_count()


def simhash(text: str, hashbits: int = 128) -> int:
    """Character n-gram simhash for near-duplicate detection (up to 128 bits).

    Uses xxhash-128 per n-gram instead of SHA-256 for a ~10–50× speedup on the
    fingerprinting step (P3-PERF-001). The mathematical properties (Hamming
    distance is preserved under near-duplicate perturbations) are unchanged;
    the hash values themselves are not comparable to pre-migration fingerprints
    and any stored ``dedup_simhash`` columns need to be recomputed.
    """
    if hashbits < 1 or hashbits > 128:
        msg = "hashbits must be between 1 and 128"
        raise ValueError(msg)
    grams: list[str] = []
    cleaned = text.replace("\n", " ")
    for n in (3, 4):
        if len(cleaned) < n:
            continue
        for i in range(len(cleaned) - n + 1):
            grams.append(cleaned[i : i + n])
    if not grams:
        grams = [cleaned or "\x00"]
    vector = [0] * hashbits
    for gram in grams:
        value = xxhash.xxh128(gram.encode("utf-8")).intdigest()
        for i in range(hashbits):
            if value & (1 << (127 - i)):
                vector[i] += 1
            else:
                vector[i] -= 1
    fingerprint = 0
    for i, weight in enumerate(vector):
        if weight > 0:
            fingerprint |= 1 << i
    return fingerprint
