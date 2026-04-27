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
- `docs/RUNBOOK.md` — operational quick reference and debug commands (includes GitButler-oriented git workflow)
- `.claude/skills/gitbutler/SKILL.md` — GitButler (`but`) version-control skill (mirrored under `.cursor/skills/gitbutler/`)
- `.claude/skills/gitbutler-workflow/SKILL.md` — Notion playbook add-on: virtual branches vs worktrees, JSON status workflow (mirrored under `.cursor/skills/gitbutler-workflow/`)
- `.claude/skills/adversarial-review/SKILL.md` — adversarial architecture review adapted for this pipeline's stack (mirrored under `.cursor/skills/adversarial-review/`)
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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **mediaite-ghostink** (7579 symbols, 15619 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/mediaite-ghostink/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/mediaite-ghostink/context` | Codebase overview, check index freshness |
| `gitnexus://repo/mediaite-ghostink/clusters` | All functional areas |
| `gitnexus://repo/mediaite-ghostink/processes` | All execution flows |
| `gitnexus://repo/mediaite-ghostink/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
