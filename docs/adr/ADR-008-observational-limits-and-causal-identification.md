# ADR-008: Observational limits and causal identification (M-22)

## Status

Accepted — methodology documentation (2026-04-26).

## Context

The pipeline compares stylometric and embedding time series before and after a
calendar split date. It does **not** embed a randomized treatment, an
instrument, or a difference-in-differences design with parallel trends.

## Decision

Findings are **observational**. Outlet-wide CMS changes, beat reassignment,
house style, syndication, and staff-mix shifts are alternative explanations
that cannot be ruled out by the current feature battery alone.

## Consequences

- External control corpora (see M-08 / `config.external_controls.example.toml`)
  and human spot-checks remain necessary for stronger claims.
- Optional DiD or natural-experiment scaffolding may be added later as
  separate ADRs; it is not implied by the existing stage contract.

## Links

- Punch list: M-22 (`prompts/punch-list/current.md`)
- Guardrails — serial correlation caveat (M-16): `docs/GUARDRAILS.md`
