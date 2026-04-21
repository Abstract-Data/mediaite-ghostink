# CLAUDE.md

## Project
- Name: `mediaite-ghostink`
- Description: Hybrid forensic pipeline investigating AI writing adoption at Mediaite.com
- Type: `pipeline` (scrape → extract → analyze → report)

## Stack and Execution
- Python: `3.13`
- Package manager/runtime: `uv`
- Primary command: `uv run forensics`
- Data stack: Polars, DuckDB, SQLite, Parquet, sentence-transformers
- Config: pydantic-settings (`config.toml` + `FORENSICS_` env prefix)

## Core Commands
- Sync: `uv sync`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format --check .`
- Test: `uv run pytest tests/ -v`
- Coverage: `uv run pytest tests/ -v --cov=src --cov-report=term-missing`
- Pipeline: `uv run forensics all`

## Key Documentation
- `AGENTS.md` — scope, governance, standards, conflict resolution, definition of done
- `AGENTS.staging.md` — staging-mode constraints
- `docs/ARCHITECTURE.md` — pipeline design, stage contracts, storage architecture, data models
- `docs/GUARDRAILS.md` — safety boundaries, Signs (failure patterns), PII handling, escalation
- `docs/TESTING.md` — TDD workflow, property-based testing, benchmarks, fixture strategy
- `docs/RUNBOOK.md` — operational quick reference and debug commands
- `prompts/README.md` — prompt versioning contract (semver, immutability, release workflow)
- `config.toml` — pipeline configuration (scraper, features, analysis settings)

## Persistent Guidance
- Follow `AGENTS.md` for scope, governance, and definition of done.
- Follow `AGENTS.staging.md` constraints when running in staging mode.
- Load `docs/GUARDRAILS.md` for safety-critical or schema work. Respect all Signs.
- Keep incremental fixes; do not redesign stage boundaries or data model contracts without approval.
- When writing new code or reviewing conventions, reference the Core Standards in `AGENTS.md`.
- When detecting a failure pattern (3+ consecutive errors, circular loops), append a Sign to `docs/GUARDRAILS.md`.

## Session Boundaries — REQUIRED

### HANDOFF.md (update at the END of every multi-step task or session)
Before reporting a task as complete, append a new completion block to `HANDOFF.md`. This is not optional. The block must include: status, what was done (with file list), decisions made, unresolved questions, and recommended next steps. If you modified code, include the verification commands you ran and their output summary. Follow the template already in the file.

### docs/RUNBOOK.md (update whenever you produce new operational knowledge)
If during a task you discover a new debug technique, resolve a recurring error, add a new CLI command, change a setup step, or learn something about the environment that a future operator would need, append it to `docs/RUNBOOK.md` under the appropriate section. Examples: new `uv run` commands, Ollama setup steps, model download sizes, environment variable requirements, common error messages and their fixes.

### docs/GUARDRAILS.md (update when you detect a failure pattern)
If you hit the same error 3+ times, encounter a circular tool loop, or discover a footgun that could trap future agents, append a new Sign to the Agent-Learned Signs section in `docs/GUARDRAILS.md`.

## Architectural Constraints
- Stage boundaries are sacred: scrape → extract → analyze → report
- Storage writes go under `data/` only
- Use `LazyFrame` over `DataFrame` — defer `.collect()` until the end
- Embedding model pinned to `all-MiniLM-L6-v2` (384-dim)
- All Python execution via `uv run`
