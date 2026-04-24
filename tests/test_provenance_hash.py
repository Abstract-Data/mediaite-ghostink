"""Tests for :mod:`forensics.utils.provenance` hashing helpers (RF-DRY-003)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from forensics.utils.provenance import compute_model_config_hash


class _Sample(BaseModel):
    a: int = 1
    b: str = "x"


def test_compute_model_config_hash_stable_for_equal_models() -> None:
    m1 = _Sample()
    m2 = _Sample(a=1, b="x")
    assert compute_model_config_hash(m1) == compute_model_config_hash(m2)


def test_compute_model_config_hash_respects_length() -> None:
    m = _Sample()
    short = compute_model_config_hash(m, length=8)
    long = compute_model_config_hash(m, length=16)
    assert len(short) == 8
    assert len(long) == 16
    assert long.startswith(short)


def test_compute_model_config_hash_exclude_changes_digest() -> None:
    class _WithVolatile(BaseModel):
        stable: int = 1
        volatile: int = Field(default=0)

    base = compute_model_config_hash(_WithVolatile(volatile=0))
    other = compute_model_config_hash(_WithVolatile(volatile=99))
    assert base != other
    excl = frozenset({"volatile"})
    same = compute_model_config_hash(_WithVolatile(volatile=99), exclude=excl)
    assert same == compute_model_config_hash(_WithVolatile(volatile=0), exclude=excl)
