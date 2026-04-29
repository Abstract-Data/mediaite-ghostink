# ADR-003: Agent Governance and Hooks

## Status

Accepted - 2026-04-20

## Context

This repository is developed with AI-assisted workflows. Without explicit governance, changes can become non-deterministic, insufficiently validated, or too broad in scope.

## Decision

Adopt governance artifacts as first-class project controls:

- `AGENTS.md` for dev-mode authority and operating rules
- `AGENTS.staging.md` for staging restrictions and validation gates
- Prompt artifacts under `prompts/core-agent/`
- Operational coordination through [`docs/TASK.md`](../TASK.md) (internal queue) and `HANDOFF.md`
- Hook/eval integration through `.claude/` configuration and test execution

## Consequences

- Positive:
  - Standardized execution and review behavior across sessions.
  - Lower risk of accidental architectural drift.
  - Better task continuity through documented handoffs.
- Negative:
  - Documentation overhead increases with project changes.
  - Governance drift can occur if artifacts are not updated alongside code.

## Follow-Up

- Keep governance files synchronized with implementation and CI checks.
- Add explicit hook scripts and eval specs as enforcement depth increases.
