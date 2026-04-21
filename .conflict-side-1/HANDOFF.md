# HANDOFF

## Handoff Protocol

Every handoff should include:

1. Current status (`Complete`, `Partial`, or `Blocked`)
2. Exact command evidence used for verification
3. Files changed and rationale
4. Known risks and recommended next actions

Agents: append a new block below using this template after every multi-step task.

---

## Template (copy this for each new entry)

<!--
### [Task Title]
**Status:** Complete | Partial | Blocked
**Date:** YYYY-MM-DD
**Agent/Session:** [identifier]

#### What Was Done
- [Concise list of changes]

#### Files Modified
- `path/to/file` — [why]

#### Verification Evidence
```
[paste the commands you ran and a summary of output]
```

#### Decisions Made
- [Key choices and rationale]

#### Unresolved Questions
- [Anything left open]

#### Risks & Next Steps
- [What should the next operator know or do]
-->

---

## Completion Log

### Initial Project Setup
**Status:** Complete
**Date:** 2026-04-20

#### What Was Done
- Created handoff template with deterministic transition requirements.
- Standardized what evidence must be recorded for follow-on operators.

#### Files Modified
- `HANDOFF.md` — created canonical handoff structure for task transitions.

#### Decisions Made
- Require command-level verification evidence in every handoff.

#### Unresolved Questions
- None.

#### Risks & Next Steps
- Append a new completion block for each non-trivial task completion.

---

### Project Alignment + Phase Prompts + Gap Analysis
**Status:** Complete
**Date:** 2026-04-20

#### What Was Done
- Applied all 16 items from project-alignment audit (Python 3.13 upgrade, AGENTS.md rewrite, enforcement hooks, CI workflows, doc fixes, missing files).
- Created 10 phase prompt files (phases 1-10) with full versioning infrastructure.
- Applied gap analysis: added POS bigram features (Phase 4), effect size thresholds and FindingStrength enum (Phase 7), methodology appendix (Phase 8), probability features (Phase 9), AI baseline generation (Phase 10).
- Migrated Phase 10 from commercial APIs to local Ollama models.
- Added PydanticAI agent architecture and pydantic-evals quality gate to Phase 10.

#### Files Modified
- `AGENTS.md` — full rewrite with canonical sections
- `CLAUDE.md` — full rewrite with project context
- `docs/ARCHITECTURE.md`, `docs/GUARDRAILS.md`, `docs/TESTING.md`, `docs/RUNBOOK.md`, `docs/NOTES.md` — expanded
- `.claude/hooks.json` + `.claude/hooks/*.sh` — 5 enforcement hooks
- `.github/workflows/*.yml` — CI orchestrator + 3 reusable workflows + release-please
- `config.toml`, `Makefile`, `.gitattributes` — created
- `prompts/phase{1-10}/` — each with current.md, v*.md snapshots, versions.json, CHANGELOG.md

#### Verification Evidence
```
uv run ruff check . — clean
uv run ruff format --check . — clean
uv run pytest tests/ -v — 4/4 passed, 80.12% coverage
```

#### Decisions Made
- Local Ollama models (llama3.1:8b, mistral:7b, gemma2:9b) for AI baseline instead of paid APIs.
- PydanticAI agent architecture for Phase 10 generation with pydantic-evals quality gate.
- Hooks enforce code constraints only; doc updates enforced via CLAUDE.md prompt instructions.
- Phase 9 Binoculars is optional (Falcon-7B pair feasible on M1 32GB but not required).

#### Unresolved Questions
- `.claude/settings.json` still has `pythonVersion: "3.12"` — file is session-protected, needs manual update to "3.13".

#### Risks & Next Steps
- Begin implementing Phase 1 (author config) or Phase 2 (scraper discovery) — the prompt specs are ready.
- Install Ollama and pull the 3 baseline models before Phase 10 implementation.
- Consider adding `pydantic-ai` and `pydantic-evals` to pyproject.toml optional deps now.

---

### Phase 8 v0.3.0 — Forensic Notebook Layout + Phase 10 v0.3.0 — PydanticAI Agents
**Status:** Complete
**Date:** 2026-04-20

#### What Was Done
- Rewrote Phase 8 prompt from 7 to 10 notebooks with forensic layout rules (narrative-first, mandatory header cells, provenance metadata, Quarto book format).
- Added 3 new notebooks: 00_power_analysis (pre-registration), 02_corpus_audit (chain of custody), 08_control_comparison (confound elimination).
- Migrated Phase 10 from commercial APIs to local Ollama models (v0.2.0), then added PydanticAI agent architecture with pydantic-evals quality gate (v0.3.0).
- Fixed agent doc-update enforcement: added "Session Boundaries — REQUIRED" section to CLAUDE.md, updated AGENTS.md Definition of Done.
- Expanded RUNBOOK.md with Ollama setup, model sizes, common issues.
- Created Phase 8 v0.3.0 versioning artifacts (snapshot, versions.json, CHANGELOG.md).

#### Files Modified
- `prompts/phase8-report-and-deployment/current.md` — complete rewrite (v0.2.0 → v0.3.0)
- `prompts/phase8-report-and-deployment/v0.3.0.md` — immutable snapshot
- `prompts/phase8-report-and-deployment/versions.json` — current_version → 0.3.0, v0.2.0 superseded
- `prompts/phase8-report-and-deployment/CHANGELOG.md` — v0.3.0 entry added
- `prompts/phase10-ai-baseline-generation/current.md` — Ollama migration + PydanticAI (v0.1.0 → v0.3.0)
- `prompts/phase10-ai-baseline-generation/v0.2.0.md`, `v0.3.0.md` — immutable snapshots
- `prompts/phase10-ai-baseline-generation/versions.json`, `CHANGELOG.md` — updated
- `CLAUDE.md` — added Session Boundaries section
- `AGENTS.md` — added Always items to Definition of Done
- `HANDOFF.md` — backfilled completion blocks, added template
- `docs/RUNBOOK.md` — expanded with Phase 9/10 operational info

#### Decisions Made
- Local Ollama models for AI baseline instead of paid APIs.
- PydanticAI agent architecture for Phase 10 with pydantic-evals quality gate.
- Folded forensic notebook layout into Phase 8 rather than creating a separate prompt.
- Quarto `type: book` with four parts for logical chapter grouping.

#### Unresolved Questions
- `.claude/settings.json` still has `pythonVersion: "3.12"` — needs manual update to "3.13".

#### Risks & Next Steps
- All 10 phase prompts are now complete and versioned — ready to begin implementation.
- Start with Phase 1 (author config) or Phase 2 (scraper discovery).
- Install Ollama and pull models before Phase 10 implementation.
