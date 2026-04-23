"""Unit tests for self-similarity cache keying (Phase 13 F1)."""

from __future__ import annotations

import pytest

from forensics.features import content as c


@pytest.fixture(autouse=True)
def _clear_self_similarity_cache() -> None:
    c._self_similarity_cache.clear()
    yield
    c._self_similarity_cache.clear()


def test_peer_tuple_fingerprint_order_sensitive() -> None:
    a = ("hello world", "foo bar baz")
    b = ("foo bar baz", "hello world")
    assert c._peer_tuple_fingerprint(a) != c._peer_tuple_fingerprint(b)


def test_peer_tuple_fingerprint_distinct_texts() -> None:
    x = ("alpha " * 10, "beta " * 10, "gamma " * 10, "delta " * 10, "epsilon " * 10)
    y = ("alpha " * 10, "beta " * 10, "gamma " * 10, "delta " * 10, "zeta " * 10)
    assert c._peer_tuple_fingerprint(x) != c._peer_tuple_fingerprint(y)


def test_self_similarity_cache_reuses_entry() -> None:
    current = "article body " * 30
    peers = tuple(f"peer {i} " * 25 for i in range(5))
    v1 = c._self_similarity_cached(current, peers)
    v2 = c._self_similarity_cached(current, peers)
    assert v1 == pytest.approx(v2, rel=0, abs=1e-9)
    assert len(c._self_similarity_cache) == 1


def test_self_similarity_cache_evicts_oldest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(c, "_SELF_SIM_CACHE_MAX", 2)
    c._self_similarity_cache.clear()

    p = tuple(f"p{i} " * 20 for i in range(5))
    c._self_similarity_cached("one " * 30, p)
    c._self_similarity_cached("two " * 30, p)
    assert len(c._self_similarity_cache) == 2
    first_key = next(iter(c._self_similarity_cache))

    c._self_similarity_cached("three " * 30, p)
    assert len(c._self_similarity_cache) == 2
    assert first_key not in c._self_similarity_cache
