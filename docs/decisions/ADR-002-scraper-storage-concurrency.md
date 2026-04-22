# ADR-002: Scraper storage concurrency — writer-queue vs aiosqlite

- **Status:** Proposed (no implementation until explicitly approved)
- **Date:** 2026-04-21
- **Scope:** Forensics scraper pipeline after incremental Phases A–C (narrow `db_lock` sections, `asyncio.to_thread` for short SQL, parallel discovery/metadata where bounded, streaming dedup/export). This ADR addresses the *next* structural step if further throughput or simplicity is required.

## Context

The scraper uses a single `sqlite3` connection owned by `Repository`, with an `asyncio.Lock` (`db_lock`) serializing access from async tasks. Phases A–C reduce how much work runs under that lock and shrink memory for dedup/export, but the fundamental pattern remains: many concurrent producers (HTTP, parse, disk) funnel into one synchronous database API on one connection.

Two common ways to evolve this are:

1. **Writer-queue (producer/consumer):** Fetch coroutines enqueue completed write intents; one writer task drains the queue and executes SQL (optionally in batched transactions).
2. **`aiosqlite`:** Replace direct `sqlite3` usage in `Repository` with async database calls so coroutines await I/O instead of blocking the event loop or using `asyncio.to_thread` per statement.

The project constraint (per planning) is to preserve `Repository`, the schema contract, resumability, and JSONL side-channels unless a future ADR explicitly changes them.

## Candidate 1: Writer-queue pattern

### Sketch

- Producers (`_fetch_one_article_html`, metadata ingest, etc.) build immutable or copy-on-write “write commands” (e.g. upsert payload, or a small enum + fields).
- They `await queue.put(cmd)` and continue; a single **writer task** loops `cmd = await queue.get()`, runs `repo` methods on the one connection, and may batch: `BEGIN;` … N upserts … `COMMIT`.
- Shutdown uses a sentinel on the queue and `asyncio.gather` of the writer with producers so errors propagate deterministically.

### Pros

- **Preserves the `Repository` surface** and synchronous semantics for non-async callers (dedup, export, CLI paths that stay sync).
- **Removes lock contention** from fetchers: producers rarely block each other on `db_lock`; the queue absorbs bursts.
- **Natural batching:** the writer can commit every *k* rows or every *t* ms, improving SQLite amortization without changing HTTP or parse code.
- **Keeps `sqlite3`:** no new dependency, no wholesale rewrite of `repository.py`.

### Cons

- **Coordination layer:** queue depth limits, backpressure, and cancellation must be designed (maxsize, `asyncio.wait_for`, structured concurrency).
- **Error propagation:** a failed batch must decide whether to retry, dead-letter, or fail the run; partial batches need clear semantics with resumability.
- **Ordering:** if any invariant depended on strict global ordering of writes, the queue must preserve per-entity ordering (e.g. one queue per shard, or sequence numbers per article id).

## Candidate 2: `aiosqlite` swap

### Sketch

- `Repository` methods become `async def` (or a parallel `AsyncRepository`) using `aiosqlite` with a single connection.
- Callers `await repo.upsert_article(...)`; the event loop is not blocked by SQLite in the same way as blocking `sqlite3` calls.

### Pros

- **Idiomatic async:** fewer `to_thread` wrappers; mental model aligns with asyncio-first scraper code.
- **Single dependency** with a well-trodden path for async SQLite.

### Cons

- **Large diff:** `repository.py` and every async caller must change; anything that assumed sync `Repository` needs an async boundary or duplication.
- **Contract change:** “Is `Repository` sync or async?” becomes a cross-cutting design decision for tests and CLI.
- **Throughput ceiling:** one connection still serializes writes under the hood; moving to `aiosqlite` mainly improves event-loop fairness and code style, not raw write parallelism, unless combined with batching or multiple connections (which would violate the current single-connection model without a new ADR).

## Decision (recommendation)

**Recommend Candidate 1 (writer-queue)** as the next structural step *after* Phases A–C land and prove stable.

**Rationale:** Writer-queue attacks the dominant remaining bottleneck—many small transactions and lock-shaped work—while keeping `Repository` synchronous and reusable. Batched commits are a direct lever on SQLite performance. An `aiosqlite` migration is a broad API churn for incremental ergonomic gain on a single connection; it does not by itself deliver the same win as a dedicated writer with explicit batching.

**Non-goals for this ADR:** Changing WordPress endpoints, retry policy, schema, `raw/` layout, or removing `db_lock` until a follow-up design explicitly replaces it with queue semantics.

## Consequences

- **If approved:** Implement writer-queue in a focused PR: define command types, writer loop, graceful shutdown, and tests for backpressure and failure isolation. Keep `Repository` implementation on `sqlite3` initially.
- **If deferred:** Continue with Phases A–C only; revisit when profiling shows commit overhead or writer starvation despite smaller critical sections.
- **If `aiosqlite` is chosen instead:** Expect a wider migration (all repository consumers), strong test coverage for async transaction boundaries, and explicit documentation of the async contract.

## Implementation gate

**Do not implement** writer-queue, `aiosqlite`, or hybrid approaches based on this ADR until stakeholders explicitly approve the chosen candidate (expected: writer-queue per above).
