# ADR-002: Storage Layer Using SQLite, Parquet, and DuckDB

## Status

Accepted - 2026-04-20

## Context

The current scaffold writes JSON/markdown artifacts into `data/`, but the roadmap expects larger forensic datasets and local analytics workflows. A storage direction is needed before scaling ingestion and analysis.

## Decision

Target a layered storage strategy:

- SQLite for lightweight transactional metadata and run indexing
- Parquet for columnar feature/analysis datasets
- DuckDB for local analytical queries across Parquet/SQLite-backed data

The existing JSON outputs remain valid bootstrap artifacts until migration tasks are implemented.

## Consequences

- Positive:
  - Supports both reproducible pipelines and ad hoc forensic analysis.
  - Keeps local developer ergonomics strong with DuckDB SQL over files.
  - Enables incremental migration from scaffold JSON outputs.
- Negative:
  - Introduces format and schema coordination overhead.
  - Requires migration and compatibility tests when introducing new sinks.

## Follow-Up

- Define storage schemas and migration checkpoints.
- Add storage adapter tests for each target sink.
- Document operator commands in `docs/RUNBOOK.md` when implemented.
