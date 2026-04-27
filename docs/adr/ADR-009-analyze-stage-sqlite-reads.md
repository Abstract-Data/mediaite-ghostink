# ADR-009 — Analyze stage reads vs SQLite `Repository` (C-06 gate)

## Status

Proposed — **no default change** until product owner approves.

## Context

The punch list (C-06) asks the analyze stage to stop opening SQLite
`Repository` and read only Parquet / JSON artifacts. Today several paths
still query SQLite for author resolution, article lists, and chain-of-custody
helpers while feature frames and embeddings are Parquet-backed.

## Decision (pending)

Options to evaluate:

1. **Documented exception (status quo)** — Keep narrow SQLite reads for roster
   and corpus metadata; document them explicitly as an exception to the
   “analyze reads artifacts” mental model.
2. **Extract-time export** — During extract, materialize scrape-time slices
   (authors manifest, article index) to versioned Parquet/JSON under `data/`
   and teach analyze to consume only those exports.
3. **Read-only snapshot** — Open SQLite in read-only URI mode against an
   immutable snapshot path so analyze never shares a write-capable handle with
   scrape.

## Consequences

- (2) and (3) touch stage contracts and deployment; they require preregistration
  / amendment and migration notes for existing workspaces.
- (1) is lowest engineering risk but leaves dual read paths.

## Links

- `docs/ARCHITECTURE.md` — stage boundaries
- `ADR-002-storage-layer-sqlite-parquet-duckdb.md`
