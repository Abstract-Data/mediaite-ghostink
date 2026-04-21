# ADR-001: Hybrid Forensics Methodology

## Status

Accepted - 2026-04-20

## Context

The project needs a clear baseline method for forensic processing while remaining easy to test and evolve. Early implementation should avoid overfitting to one source type or one analysis method.

## Decision

Adopt a hybrid methodology that separates the workflow into four deterministic stages:

1. scrape raw source material
2. extract lexical/structural features
3. analyze features into confidence labels
4. report findings in human-readable markdown

## Consequences

- Positive:
  - Stage boundaries remain stable while implementations improve.
  - Unit and integration tests map cleanly to each stage.
  - Outputs are auditable by intermediate artifacts.
- Negative:
  - Initial implementation may appear simplistic until richer models are added.
  - Repeated stage execution can duplicate work in scaffold mode.

## Follow-Up

- Introduce cache/reuse between stages once artifact contracts are finalized.
- Add eval cases that assert behavior across realistic claim/evidence scenarios.
