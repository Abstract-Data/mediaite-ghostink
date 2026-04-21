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

---

### Phase 11: Typer CLI Migration Prompt
**Status:** Complete
**Date:** 2026-04-20

#### What Was Done
- Created `prompts/phase11-typer-cli-migration/` with full versioned prompt (v0.1.0) for migrating argparse CLI to Typer.
- Inventoried complete CLI surface area across all 10 phase prompts (30+ flags).
- Designed one-file-per-subcommand package structure (`cli/__init__.py`, `_helpers.py`, `scrape.py`, `extract.py`, `analyze.py`, `report.py`).
- Pre-wired all Phase 6–10 flags as stubs so future phases don't need to restructure the CLI.
- Included complete test rewrites for Typer CliRunner.

#### Files Modified
- `prompts/phase11-typer-cli-migration/current.md` — created (v0.1.0)
- `prompts/phase11-typer-cli-migration/v0.1.0.md` — immutable snapshot
- `prompts/phase11-typer-cli-migration/versions.json` — created
- `prompts/phase11-typer-cli-migration/CHANGELOG.md` — created

#### Decisions Made
- Typer over Click (Typer wraps Click with less boilerplate and Python type annotations).
- `typer[all]>=0.15.0` includes rich for formatted help output.
- Scrape uses `add_typer()` (sub-app with `invoke_without_command=True`); other commands use `app.command()`.
- Placeholder guard raises `typer.BadParameter` instead of `ValueError`.
- Phase 11 runs after all analysis phases are built — retool the CLI as a clean-up pass.

#### Unresolved Questions
- None.

#### Risks & Next Steps
- Run Phase 11 after completing the current phase work to retool the CLI.
- The migration is backward-compatible: `pyproject.toml` entry point and `__main__.py` import path don't change.

---

### Phase 11 Typer CLI Migration (Implementation)
**Status:** Complete
**Date:** 2026-04-21
**Agent/Session:** claude/review-prompts-plan-uWhOn (Scope A)

#### What Was Done
- Replaced the single-file argparse CLI (`src/forensics/cli.py`) with a Typer package at `src/forensics/cli/` (one file per subcommand group).
- Preserved the scrape flag-combination dispatcher byte-for-byte — promoted it to a testable `_dispatch` async function.
- Pre-wired Phase 9/10 flags (`--probability`, `--no-binoculars`, `--device`, `--verify-corpus`) so later scopes only add logic.
- Wired `--verify-corpus` to call the existing `forensics.utils.provenance.verify_corpus_hash` against `data/analysis/corpus_custody.json`.
- Rewrote `tests/integration/test_cli.py` to use `typer.testing.CliRunner` and `tests/integration/test_cli_scrape_dispatch.py` to call `_dispatch` directly.
- Updated `tests/evals/test_core_eval.py` for the Typer API.
- Added `typer>=0.15.0` to core deps; added `probability` and `baseline` optional-extras.

#### Files Modified
- `src/forensics/cli.py` — deleted (replaced by package)
- `src/forensics/cli/__init__.py`, `_helpers.py`, `scrape.py`, `extract.py`, `analyze.py`, `report.py` — created
- `tests/integration/test_cli.py`, `tests/integration/test_cli_scrape_dispatch.py`, `tests/evals/test_core_eval.py` — rewritten for Typer
- `pyproject.toml` — added `typer>=0.15.0` to dependencies; added `probability` and `baseline` optional-extras
- `AGENTS.md` — CLI line argparse → Typer

#### Verification Evidence
```
uv run forensics --help       # Typer-rendered help
uv run forensics --version    # prints "forensics 0.1.0"
uv run python -m forensics --help
uv run pytest tests/ -v       # 145 passed, 15 skipped (spaCy model) — coverage 60.14%
uv run ruff check .           # All checks passed
uv run ruff format --check .  # 89 files already formatted
```

#### Decisions Made
- Kept `--openai-key` and `--llm-model` on the analyze command as deprecated — they will be removed together with the OpenAI baseline path in Scope C (Phase 10).
- `main()` returns an int so `__main__.py` keeps working unchanged; inside, it catches `SystemExit` from `app()`.

#### Unresolved Questions
- None for this scope.

#### Risks & Next Steps
- Scope B (Phase 9 probability features) builds on the wired but stubbed `--probability` / `--no-binoculars` / `--device` flags.
- Scope C (Phase 10 Ollama baseline) will wire `--ai-baseline` and `--verify-corpus` stubs and retire the OpenAI code path.

---

### Phase 9 Probability Features (Implementation)
**Status:** Complete
**Date:** 2026-04-21
**Agent/Session:** claude/review-prompts-plan-uWhOn (Scope B)

#### What Was Done
- Added `src/forensics/features/probability.py` with `compute_perplexity`, `split_sentences`, `load_reference_model`, and sliding-window perplexity over torch + transformers.
- Added `src/forensics/features/binoculars.py` with `compute_binoculars_score` and `load_binoculars_models` (CPU-fallback warning, disabled-by-default).
- Added `src/forensics/features/probability_pipeline.py` orchestrator that scores every configured author's articles and writes `data/probability/{slug}.parquet` plus a pinned `data/probability/model_card.json`.
- Added `ProbabilityConfig` to `src/forensics/config/settings.py` and attached it under `ForensicsSettings.probability`.
- Added `[probability]` section to `config.toml` (reference GPT-2 with pinned revision, Binoculars pair, sliding-window settings, low-ppl threshold).
- Wired Phase 11's stubbed `--probability` / `--no-binoculars` / `--device` flags to the new pipeline in `src/forensics/cli/extract.py`.
- Added `tests/test_probability.py` (8 fast tests) with a `@pytest.mark.slow` case for a real GPT-2 smoke run; configured pytest to skip slow tests by default via `-m 'not slow'`.
- Documented the probability extra, artifacts, and slow-test flag in `docs/RUNBOOK.md`.

#### Files Modified / Created
- `src/forensics/features/probability.py` — created
- `src/forensics/features/binoculars.py` — created
- `src/forensics/features/probability_pipeline.py` — created
- `src/forensics/config/settings.py` — added `ProbabilityConfig`
- `src/forensics/cli/extract.py` — wired `--probability` to the new pipeline
- `config.toml` — added `[probability]`
- `pyproject.toml` — registered `slow` marker, default `-m 'not slow'`
- `tests/test_probability.py` — created (8 fast tests + 1 slow)
- `docs/RUNBOOK.md` — probability extra + slow test flag notes

#### Verification Evidence
```
uv run forensics extract --help            # shows --probability/--no-binoculars/--device
uv run pytest tests/test_probability.py -v # 8 passed, 1 deselected (slow)
uv run pytest tests/ -v                    # 153 passed, 15 skipped, 1 deselected — coverage 60.27%
uv run ruff check . && uv run ruff format --check .
```

#### Decisions Made
- Binoculars `enabled=false` by default in `config.toml` because Falcon-7B requires ~28GB. Users flip it on per machine.
- Sentence segmentation uses a regex (not spaCy) so probability features don't require `en_core_web_md`.
- `model_card.json` records a SHA-256 digest of the pinned model identities so cross-run comparability is checked.
- `@pytest.mark.slow` isolates model-download tests; default pytest run stays under a minute on CPU.

#### Unresolved Questions
- None for this scope.

#### Risks & Next Steps
- Scope C (Phase 10 Ollama baseline + chain of custody) is next; it will remove the legacy OpenAI path in `src/forensics/analysis/drift.py`.

---

### Phase 10 AI Baseline (Ollama) + Chain of Custody (Implementation)
**Status:** Complete
**Date:** 2026-04-21
**Agent/Session:** claude/review-prompts-plan-uWhOn (Scope C)

#### What Was Done
- Introduced `src/forensics/baseline/` package with:
  - `agent.py` — `BaselineDeps`, `GeneratedArticle`, `make_baseline_agent` (PydanticAI + Ollama OpenAI-compatible provider, lazy import).
  - `orchestrator.py` — `run_generation_matrix` (models × temperatures × modes × n), `reembed_existing_baseline`, manifest writer.
  - `topics.py` — LDA-based topic stratification (reuses `extract_lda_topic_keywords` from `analysis/drift.py`); word-count sampler.
  - `prompts.py` — template loader + `PromptContext` for `raw_generation` / `style_mimicry`.
  - `preflight.py` — async Ollama connectivity + model availability check.
  - `utils.py` — `sanitize_model_tag`, `get_model_digest`, prompt hash helpers.
- Added `scripts/generate_baseline.py` CLI with `--author`, `--all`, `--model`, `--articles-per-cell`, `--dry-run`, `--preflight`.
- Added `evals/baseline_quality.py` with pydantic-evals harness (WordCountAccuracy, TopicRelevance, RepetitionDetector, PerplexityRangeCheck).
- Added prompt templates under `prompts/baseline_templates/raw_generation.txt` and `style_mimicry.txt`.
- Added `BaselineConfig` and `ChainOfCustodyConfig` pydantic models and wired them into `ForensicsSettings`.
- Added `[baseline]` and `[chain_of_custody]` sections in `config.toml`.
- **Retired the OpenAI baseline path entirely** from `src/forensics/analysis/drift.py`:
  - Removed `_openai_chat_completion` and the entire `generate_ai_baseline` body.
  - Rewrote `run_ai_baseline_command` as a thin dispatch wrapper that calls the new baseline package.
  - Dropped unused imports (`httpx`, `os`, `uuid`, `UTC`).
  - Removed `--openai-key` and `--llm-model` flags from `analyze`; added `--baseline-model` and `--articles-per-cell` in their place.
- Wired `analyze --verify-corpus` to `forensics.utils.provenance.verify_corpus_hash` (fails hard with exit code 1 on mismatch).
- Added `tests/test_baseline.py` with 16 unit tests (agent/prompts/topics/preflight/config/chain-of-custody) — all mocked, no live Ollama required.
- Adjusted `pyproject.toml`: coverage omits `baseline/orchestrator.py` and `baseline/agent.py` (cannot exercise without Ollama + extras).
- Documented the `baseline` extra, generation commands, and eval flow in `docs/RUNBOOK.md`.

#### Files Modified / Created
- `src/forensics/baseline/__init__.py`, `agent.py`, `orchestrator.py`, `topics.py`, `prompts.py`, `preflight.py`, `utils.py` — created
- `scripts/generate_baseline.py` — created
- `evals/baseline_quality.py` — created
- `prompts/baseline_templates/raw_generation.txt`, `style_mimicry.txt` — created
- `src/forensics/config/settings.py` — added `BaselineConfig`, `ChainOfCustodyConfig`, attached to `ForensicsSettings`
- `config.toml` — added `[baseline]` and `[chain_of_custody]` sections
- `src/forensics/analysis/drift.py` — removed OpenAI generator; `run_ai_baseline_command` now dispatches to `baseline.orchestrator`
- `src/forensics/cli/analyze.py` — `--openai-key` / `--llm-model` → `--baseline-model` / `--articles-per-cell`; `--verify-corpus` now actually verifies
- `src/forensics/cli/__init__.py` — `run_all` helper updated for new analyze signature
- `pyproject.toml` — coverage omit for baseline orchestrator/agent
- `tests/test_baseline.py` — created
- `docs/RUNBOOK.md` — baseline generation + evals section

#### Verification Evidence
```
grep -rn "_openai_chat_completion\|api.openai.com" src/        # zero matches
uv run forensics analyze --help                                 # shows --verify-corpus, --baseline-model, --articles-per-cell
uv run pytest tests/ -v                                         # 169 passed, 15 skipped, 1 deselected, coverage 61.81%
uv run ruff check . && uv run ruff format --check .             # all clean
```

#### Decisions Made
- Ollama is accessed through its OpenAI-compatible `/v1` endpoint via `pydantic_ai.providers.openai.OpenAIProvider` — same pattern used across `pydantic-ai[openai]`. This lets the `baseline` extra ship without a separate `ollama` extra of pydantic-ai.
- `baseline/orchestrator.py` and `baseline/agent.py` are omitted from coverage because they require a live Ollama server. All logic around them (preflight, prompts, topics, utils, chain of custody) is fully tested.
- `verify_corpus_hash` returns `(bool, str)` — the CLI uses both the ok flag and the message so operators get a specific reason on failure.

#### Unresolved Questions
- None for this scope.

#### Risks & Next Steps
- Manual end-to-end run of `uv run python scripts/generate_baseline.py --author <slug> --articles-per-cell 1` on a host with Ollama + pulled models is the next verification step; CI can't exercise it.

---

### Development Environment Bootstrap + Runtime Validation
**Status:** Complete
**Date:** 2026-04-21
**Agent/Session:** codex/cloud-c958

#### What Was Done
- Installed `uv` in the cloud environment, synced project dependencies (including `dev` extra), validated CLI/test tooling, and executed representative application commands to confirm runtime health.
- Verified expected template guard behavior on `forensics all` / scrape-discovery and confirmed a successful executable stage run with `forensics scrape --dedup`.
- Added an operational runbook note for environments where `uv` is missing from `PATH`.

#### Files Modified
- `docs/RUNBOOK.md` — added “Command not found: `uv`” recovery steps discovered during bootstrap.
- `HANDOFF.md` — appended this completion record with command evidence.

#### Verification Evidence
```
source "$HOME/.local/bin/env" && uv --version
# uv 0.11.7

source "$HOME/.local/bin/env" && uv sync
# success: virtualenv created, project deps installed

source "$HOME/.local/bin/env" && uv sync --extra dev
# success: installed pytest/ruff/dev tooling

source "$HOME/.local/bin/env" && uv run forensics --help
# success: Typer CLI renders commands

source "$HOME/.local/bin/env" && uv run ruff check .
# All checks passed

source "$HOME/.local/bin/env" && uv run ruff format --check .
# 103 files already formatted

source "$HOME/.local/bin/env" && uv run pytest tests/ -v
# 174 passed, 15 skipped, 1 deselected (coverage 62.93%)

source "$HOME/.local/bin/env" && uv run forensics all
# expected failure: placeholder authors guard in config.toml

source "$HOME/.local/bin/env" && uv run forensics scrape --dedup
# success: dedup stage executed, marked 0 near-duplicates
```

#### Decisions Made
- Did not replace template placeholder authors because that would alter project analysis scope and requires real author inputs.
- Used `forensics scrape --dedup` as the successful runtime proof path that does not require live WordPress author configuration.

#### Unresolved Questions
- Who are the real target/control authors for `config.toml` to enable full scrape/all pipeline execution in this environment?

#### Risks & Next Steps
- Until placeholder authors are replaced, networked scrape commands (`forensics scrape --discover` and `forensics all`) will intentionally fail fast.
- Next operator can enable full end-to-end run by updating `config.toml` author rows, then rerunning `uv run forensics all`.
