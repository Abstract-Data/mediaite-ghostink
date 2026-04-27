"""Unit tests for simhash n-gram generator consumption and fingerprint invariants (PR94 #16)."""

from __future__ import annotations

from collections.abc import Iterator

from forensics.utils import hashing as hashing_mod
from forensics.utils.hashing import normalize_text_for_simhash, simhash, simhash_hamming


def test_simhash_single_pass_iterator_matches_materialized_ngrams() -> None:
    text = "abcdef " * 80
    cleaned = normalize_text_for_simhash(text)

    def _grams_gen() -> Iterator[str]:
        yield from hashing_mod._simhash_char_ngrams(cleaned)

    h_one_shot = hashing_mod._simhash_from_grams(_grams_gen(), 128)
    h_public = simhash(text, hashbits=128)
    assert h_one_shot == h_public


def test_one_character_substitution_small_hamming_on_long_document() -> None:
    base = ("The quick brown fox jumps over the lazy dog. " * 60).strip()
    assert len(base.split()) >= 500
    mutated = base[:200] + "X" + base[201:]
    a = simhash(base, hashbits=128)
    b = simhash(mutated, hashbits=128)
    assert simhash_hamming(a, b) <= 3


def test_nfkc_fullwidth_digits_match_halfwidth() -> None:
    half = "Version 12345 is stable for hashing checks."
    full = "Version \uff11\uff12\uff13\uff14\uff15 is stable for hashing checks."
    assert simhash(half, hashbits=128) == simhash(full, hashbits=128)


def test_empty_string_simhash_is_stable_nonzero() -> None:
    h = simhash("", hashbits=128)
    assert isinstance(h, int)
    assert h == simhash("", hashbits=128)
    assert h != 0
