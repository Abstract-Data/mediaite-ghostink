# AGENTS.staging.md
# Version: 0.1.0
# Last Updated: 2026-04-20
# Environment: staging
# Model: gpt-5-3-codex
# Fallback Model: gpt-5.1
# Project: mediaite-ghostink

## Staging Scope
- Read-heavy investigation and validation work is preferred.
- Source edits are limited to low-risk fixes with clear validation steps.
- Any destructive command requires explicit human approval.
- Changes must pass lint and targeted tests before handoff.

## Allowed Commands
- `uv sync`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest tests/ -v`
- `uv run pytest tests/evals/ -v`

## Blocked Actions
- Editing secrets or deployment credentials
- Destructive git operations
- Changing infrastructure or provider architecture without approval
- Broad source refactors without explicit task-level approval

## Staging Evaluation Gate
1. Reproduce behavior with deterministic command(s).
2. Apply minimal diff with no architecture/provider swaps.
3. Re-run lint + relevant unit/integration/eval tests.
4. Capture evidence and remaining risks in `HANDOFF.md`.
