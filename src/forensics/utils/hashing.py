"""Content fingerprints for deduplication."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator

import xxhash


def content_hash(text: str) -> str:
    """SHA-256 hex digest of the normalized string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def simhash_hamming(a: int, b: int) -> int:
    """Hamming distance between two simhash fingerprints."""
    return (a ^ b).bit_count()


# Second xxh128 seed used to extend the 128-bit digest to 256 bits when
# callers request ``hashbits > 128``. The constant is arbitrary but fixed so
# fingerprints are deterministic across runs.
_SIMHASH_HIGH_SEED: int = 0x9E3779B97F4A7C15


def _gram_digest(gram_bytes: bytes, hashbits: int) -> int:
    """Return a deterministic ``hashbits``-wide digest of ``gram_bytes``.

    For ``hashbits <= 128`` one ``xxh128`` is enough. For ``129..256`` the
    digest is the concatenation of two ``xxh128`` hashes with different seeds,
    giving 256 independent bits; we slice to the requested width.
    """
    lo = xxhash.xxh128(gram_bytes).intdigest()
    if hashbits <= 128:
        return lo
    hi = xxhash.xxh128(gram_bytes, seed=_SIMHASH_HIGH_SEED).intdigest()
    return (hi << 128) | lo


def _simhash_char_ngrams(cleaned: str) -> Iterator[str]:
    yielded = False
    for n in (3, 4):
        if len(cleaned) < n:
            continue
        for i in range(len(cleaned) - n + 1):
            yielded = True
            yield cleaned[i : i + n]
    if not yielded:
        yield cleaned or "\x00"


def _simhash_from_grams(grams: Iterable[str], hashbits: int) -> int:
    top_bit = hashbits - 1
    vector = [0] * hashbits
    for gram in grams:
        value = _gram_digest(gram.encode("utf-8"), hashbits)
        for i in range(hashbits):
            if value & (1 << (top_bit - i)):
                vector[i] += 1
            else:
                vector[i] -= 1
    fingerprint = 0
    for i, weight in enumerate(vector):
        if weight > 0:
            fingerprint |= 1 << i
    return fingerprint


def simhash(text: str, hashbits: int = 128) -> int:
    """Character n-gram simhash for near-duplicate detection (up to 256 bits).

    Uses xxhash-128 per n-gram instead of SHA-256 for a ~10–50× speedup on the
    fingerprinting step (P3-PERF-001). When ``hashbits > 128``, two xxh128
    digests with different seeds are concatenated to supply up to 256 bits, so
    the old 256-bit API surface is preserved. The mathematical properties
    (Hamming distance preservation under near-duplicate perturbations) are
    unchanged; hash *values* are not comparable to pre-migration SHA-256
    fingerprints, so any stored ``dedup_simhash`` columns must be recomputed.
    """
    if hashbits < 1 or hashbits > 256:
        msg = "hashbits must be between 1 and 256"
        raise ValueError(msg)
    cleaned = text.replace("\n", " ")
    return _simhash_from_grams(_simhash_char_ngrams(cleaned), hashbits)
