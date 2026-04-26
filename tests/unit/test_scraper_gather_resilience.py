"""Regression tests for ``asyncio.gather(..., return_exceptions=True)`` in scrapers."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_gather_survives_single_runtime_error_without_cancelled_error() -> None:
    """One failing sibling must not cancel successful tasks or raise ``gather`` itself."""

    async def succeed() -> int:
        return 1

    async def fail() -> None:
        raise RuntimeError("simulated sibling failure")

    results = await asyncio.gather(
        succeed(),
        succeed(),
        fail(),
        succeed(),
        return_exceptions=True,
    )

    assert results[0] == 1
    assert results[1] == 1
    assert isinstance(results[2], RuntimeError)
    assert results[3] == 1
    assert not any(isinstance(r, asyncio.CancelledError) for r in results)


@pytest.mark.asyncio
async def test_metadata_parallel_sum_skips_exception_outcomes() -> None:
    """Mirrors ``collect_article_metadata`` zip + sum when one author task raises."""

    async def ingest(slot: int) -> int:
        if slot == 2:
            raise RuntimeError("boom")
        return slot

    slots = [0, 1, 2, 3, 4]
    ingest_results = await asyncio.gather(
        *(ingest(s) for s in slots),
        return_exceptions=True,
    )
    inserted_total = 0
    for _slot, outcome in zip(slots, ingest_results, strict=True):
        if isinstance(outcome, BaseException):
            continue
        inserted_total += int(outcome)
    assert inserted_total == 0 + 1 + 3 + 4
