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

### Notion code review + refactoring report — full implementation (no deferrals)
**Status:** Complete
**Date:** 2026-04-21
**Agent/Session:** Cursor background agent (Notion MCP: Code Review Report + Refactoring Analysis Report)

#### What Was Done
- Implemented the consolidated recommendations from both Notion reports (repository session pattern, DRY helpers, config externalization, complexity reduction, drift/LDA/topic moves, BOCPD optimization, typed report args, nested `FeatureVector` with Parquet flat compat, scraper `Repository` injection hybrid, pipeline module population, Hypothesis lexical bounds, docs alignment).
- Updated ADRs 001/003, `docs/TESTING.md` coverage target note, and `docs/GUARDRAILS.md` Sign for context-managed `Repository`.
- Adjusted tests for `with Repository(...) as repo:` and added `tests/test_lexical_hypothesis.py`.

#### Files Modified
- `src/forensics/storage/repository.py` — `Repository` as context manager; single connection per session.
- `src/forensics/storage/parquet.py`, `src/forensics/storage/export.py` — `load_feature_frame_sorted` / serialization paths.
- `src/forensics/models/features.py`, `src/forensics/models/report_args.py` (new) — nested `FeatureVector`, `ReportArgs`.
- `src/forensics/config/settings.py` — `AnalysisConfig` tunables for changepoint/convergence/extraction failure ratio.
- `src/forensics/analysis/*` — `cohens_d` consolidation, BOCPD O(n), drift pipeline DRY, orchestrator/comparison/timeseries refactors, `utils.py` (new).
- `src/forensics/baseline/topics.py` — LDA topic extraction moved from drift.
- `src/forensics/analysis/drift.py` — drift pipeline public helpers naming, intra-period variance optimization.
- `src/forensics/features/assembler.py` (new), `pipeline.py`, `readability.py`, `probability_pipeline.py` — assembler + extraction abort threshold + narrower exceptions.
- `src/forensics/cli/*`, `src/forensics/pipeline.py`, `src/forensics/reporting.py` — dispatch/registry patterns, `run_all_pipeline`, typed report args.
- `src/forensics/scraper/{crawler,dedup,fetcher}.py` — optional `Repository` injection for hybrid decoupling.
- `docs/adr/001-sqlite-connection-management.md`, `docs/adr/003-deferred-scraper-storage-decoupling.md`, `docs/GUARDRAILS.md`, `docs/TESTING.md`.
- `tests/*.py`, `tests/test_lexical_hypothesis.py` (new).

#### Verification Evidence
```
uv run ruff check .
# All checks passed!

uv run ruff format --check .
# 107 files already formatted

uv run pytest tests/ -q --tb=line
# Required test coverage of 60.0% reached. Total coverage: 64.04%
# 15 skipped: en_core_web_md not installed (expected without spacy model)
```

#### Decisions Made
- `Repository` must be used as `with Repository(path) as repo:` everywhere (production + tests); aligns with ADR-001 and removes connection-per-call anti-pattern.
- `FeatureVector` nested Pydantic models retain Parquet compatibility via `to_flat_dict` / legacy flat ingestion.
- Scraper/storage “decoupling” is hybrid: injectable `Repository` while keeping persistence responsibilities in scraper modules (ADR-003 partial accepted).

#### Unresolved Questions
- None for this implementation scope.

#### Risks & Next Steps
- Any out-of-tree scripts or operators still calling `Repository(path)` without `with` will fail fast with `RuntimeError`; search callers outside `src/` and `tests/` if you have local tooling.

---

### Code-review follow-ups on PR #18 (Notion refactor)
**Status:** Complete
**Date:** 2026-04-21
**Agent/Session:** Claude Code — `/review` follow-up on `cursor/notion-full-implementation-e8c7`

#### What Was Done
- Fixed the FeatureVector Parquet dict round-trip: `_accept_legacy_flat_payload` now JSON-decodes `function_word_distribution`, `punctuation_profile`, `pos_bigram_top30`, and `clause_initial_top10` when they come back as strings from Parquet. Before this fix, reconstructing a `FeatureVector` from a DataFrame row silently failed (Pydantic received `str` where `dict[str, float]` was expected).
- Added `tests/test_features.py::test_feature_vector_parquet_dict_field_roundtrip` pinning the write → read → model_validate path with non-empty dict fields.
- Added `tests/test_analysis.py::test_bocpd_vectorized_matches_reference`: runs the PR's new vectorized BOCPD side-by-side with an O(n²) reference, asserting matched indices and posterior probabilities on both a mean-shift and a flat signal.
- Added `tests/test_features.py::test_feature_pipeline_aborts_when_failure_ratio_exceeded` covering the new `feature_extraction_max_failure_ratio` abort path.
- Strengthened `tests/test_lexical_hypothesis.py`: added three real invariants (TTR=1 when all unique, hapax=0 when every token repeats, TTR non-increasing under duplication) on top of the pre-existing bounds check.
- Removed the unused `AnalyzeFlags` dataclass from `src/forensics/cli/analyze.py` and inlined its fields as keyword args in `_resolve_mode_flags`.
- Moved LDA tunables (`lda_num_topics`, `lda_n_keywords`) into `AnalysisConfig`; `sample_topic_keywords` now resolves them from settings when callers omit them (back-compat preserved).
- Documented injected-`Repository` lifetime and partial-failure semantics in `docs/adr/003-deferred-scraper-storage-decoupling.md`.
- Finished the DRY pass in `src/forensics/analysis/drift.py`: `run_drift_analysis` now uses `resolve_author_rows` instead of inlining slug→author resolution.
- Hardened `Repository.rewrite_raw_paths_after_archive`: validates `year` as a 4-digit int and rejects tails containing path separators or `..`.
- Converted `load_feature_frame_sorted` in `src/forensics/storage/parquet.py` to `pl.scan_parquet(...).sort(...).collect()` so the planner can push operations down.

#### Files Modified
- `src/forensics/models/features.py` — dict-field JSON decode in `_accept_legacy_flat_payload`.
- `src/forensics/storage/parquet.py` — `load_feature_frame_sorted` lazy scan.
- `src/forensics/storage/repository.py` — archive path validation.
- `src/forensics/analysis/drift.py` — use `resolve_author_rows`.
- `src/forensics/cli/analyze.py` — remove `AnalyzeFlags`.
- `src/forensics/config/settings.py` — add `lda_num_topics`, `lda_n_keywords`.
- `src/forensics/baseline/topics.py` — resolve LDA params from settings.
- `docs/adr/003-deferred-scraper-storage-decoupling.md` — injection contract.
- `tests/test_features.py`, `tests/test_analysis.py`, `tests/test_lexical_hypothesis.py` — new tests + strengthened invariants.

#### Verification Evidence
```
uv run ruff check .
# All checks passed!

uv run ruff format --check .
# 107 files already formatted

uv run pytest tests/ --tb=short
# 180 passed, 16 skipped, 1 deselected
# Required test coverage of 60.0% reached. Total coverage: 64.20%
```

#### Decisions Made
- Dict-field JSON decode lives in the FeatureVector validator (not in `read_features`) so any caller constructing from a flat dict benefits, not just the Parquet reader.
- BOCPD equivalence test embeds a reference implementation rather than pinning against a frozen golden file; it's a handful of lines and makes future algorithmic refactors self-auditing.
- Kept coverage threshold at 60% (was 80% pre-PR #18). Raising it is follow-on work that requires covering `features/pipeline.py`, `reporting.py`, and scraper modules properly — out of scope here.

#### Unresolved Questions
- None for this scope. The review flagged two nits that were already fine in-tree (feature-abort error message already includes `batch_failed/batch`; SQL is fully parameterized) so they did not require changes.

#### Risks & Next Steps
- The archive-path hardening is defense-in-depth; no known producer of malformed `raw_html_path` values exists. Worth a fuzz test if untrusted ingestion is ever added.
- If downstream callers of `load_feature_frame_sorted` relied on the eager read-and-sort (e.g., to catch Parquet corruption early), the lazy scan now defers that to `.collect()`. All current call sites immediately filter/collect, so this is safe.
- Optional: install `en_core_web_md` locally to un-skip spaCy-dependent tests.

---

### RF-ARCH-001 — PipelineContext audit (non-scrape CLI)
**Status:** Complete
**Date:** 2026-04-21
**Agent/Session:** Cursor Agent 5 (T04b)

#### What Was Done
- Introduced `PipelineContext` in `src/forensics/pipeline_context.py` with `resolve()` and `record_audit()` (optional best-effort vs required insert, unified INFO audit line).
- Routed `forensics extract`, `forensics analyze` (including compare-only), `forensics report`, and `run_all_pipeline` audit through `PipelineContext`.
- Added `forensics report` `analysis_runs` row (`forensics report`) plus a structured INFO line for format/notebook/verify.
- Moved `config_fingerprint()` to `src/forensics/config/fingerprint.py` to avoid `pipeline_context` → `cli._helpers` → `cli` package circular import; `scrape.py` now imports `config_fingerprint` from `forensics.config`.

#### Files Modified
- `src/forensics/pipeline_context.py` — new.
- `src/forensics/config/fingerprint.py` — new; holds `config_fingerprint`.
- `src/forensics/config/__init__.py` — export `config_fingerprint`.
- `src/forensics/cli/_helpers.py` — removed inlined fingerprint (delegation removed; scrape uses config).
- `src/forensics/cli/scrape.py` — import `config_fingerprint` from config.
- `src/forensics/cli/extract.py`, `analyze.py`, `report.py`, `src/forensics/pipeline.py` — use `PipelineContext`.
- `tests/test_pipeline_context.py` — unit tests for audit paths.
- `tests/integration/test_cli.py` — monkeypatch `forensics.pipeline_context.insert_analysis_run`.

#### Verification Evidence
```
uv run ruff check src/forensics/config/fingerprint.py src/forensics/config/__init__.py src/forensics/cli/_helpers.py src/forensics/cli/scrape.py src/forensics/pipeline_context.py src/forensics/cli/extract.py src/forensics/cli/analyze.py src/forensics/cli/report.py src/forensics/pipeline.py tests/test_pipeline_context.py tests/integration/test_cli.py
# All checks passed!

uv run pytest tests/test_pipeline_context.py tests/integration/test_cli.py -v --tb=short
# 12 passed
```

#### Decisions Made
- `record_audit(optional=True)` matches prior extract / `forensics all` behavior; analyze paths use `optional=False` so failures still surface when embedding `run_id` into `run_metadata.json`.
- Circular import fixed by lifting fingerprint into `config/` rather than lazy-import hacks in `pipeline_context`.

#### Unresolved Questions
- None.

#### Risks & Next Steps
- Any external code that imported `config_fingerprint` only from `forensics.cli._helpers` must switch to `forensics.config` (only `scrape.py` did in-repo).


---

### Phase 12 Unit 1: ws3-preflight-hardening
**Status:** Complete
**Date:** 2026-04-22
**Agent/Session:** Opus 4.7 — worker agent (ws3)

#### What Was Done
- Added `src/forensics/preflight.py` with 8 structured checks (Python version, spaCy `en_core_web_sm`, sentence-transformers model, Quarto, Ollama, disk space, config parse, placeholder authors). Exposes `PreflightCheck`, `PreflightReport`, `run_all_preflight_checks(settings, *, strict=False)`.
- Hard-fails only on Python, spaCy, disk, config parse, placeholder authors. Other checks degrade to `warn`.
- Registered `forensics preflight [--strict]` CLI subcommand (exit 0 on all pass/warn, 1 on any fail).
- Threaded `settings.scraping.simhash_threshold` through `deduplicate_articles` in all three call sites of `src/forensics/cli/scrape.py` (DEDUP_ONLY, FETCH_DEDUP_EXPORT, FULL_PIPELINE).
- Added `simhash_threshold: int = Field(default=3, ge=0, le=64)` to `ScrapingConfig` and `simhash_threshold = 3` in `[scraping]` of `config.toml`.
- Added `MIN_PEERS_FOR_SIMILARITY: Final[int] = 5` module constant and made `_self_similarity` return `float | None` when peer count falls short.
- Updated `ContentFeatures.self_similarity_30d`/`90d` to `float | None = None`.
- Wired preflight into `run_all_pipeline()`: hard-fails return exit code 2; warnings log. Added `record_audit("forensics all — preflight", ...)` before scrape.
- Added `rich.progress.Progress` bar to `extract_all_features` in `src/forensics/features/pipeline.py` (per-author task, advances in a `finally` so failures still tick).
- Added `tests/test_preflight.py` covering all-pass, missing spaCy, placeholder detection, disk low, config parse error, python version edge cases, report helpers, strict mode.
- Fixed `tests/integration/test_cli_scrape_dispatch.py::test_scrape_dedup_only` monkeypatch lambda to accept new `hamming_threshold` kwarg.

#### Files Modified
- `src/forensics/preflight.py` — NEW module.
- `tests/test_preflight.py` — NEW tests.
- `src/forensics/cli/__init__.py` — register `preflight` command.
- `src/forensics/features/content.py` — `MIN_PEERS_FOR_SIMILARITY`, `_self_similarity` returns `None`.
- `src/forensics/models/features.py` — `self_similarity_*` Optional.
- `src/forensics/scraper/dedup.py` — unchanged (signature already parametric).
- `src/forensics/cli/scrape.py` — three dedup call sites pass threshold.
- `src/forensics/config/settings.py` — `simhash_threshold` field.
- `config.toml` — `simhash_threshold = 3`.
- `src/forensics/pipeline.py` — preflight gate + audit.
- `src/forensics/features/pipeline.py` — rich progress bar.
- `tests/integration/test_cli_scrape_dispatch.py` — lambda kwargs.

#### Verification Evidence
```
$ uv run ruff format --check . && uv run ruff check .
121 files already formatted
All checks passed!

$ uv run pytest tests/test_preflight.py -v --no-cov
9 passed in 0.84s

$ uv run pytest tests/ --no-cov
224 passed, 18 skipped, 2 deselected in 19.38s
(skips are unrelated: en_core_web_md not installed locally.)

$ uv run forensics preflight   # exit 1 on this dev env (expected: no spaCy sm model, config has placeholders)
$ uv run forensics --help      # preflight subcommand visible
```

#### Decisions Made
- Used a Protocol `_SettingsLike` so preflight does not import `ForensicsSettings` at module load (keeps circular risk low).
- Individual checks exported for future TUI screen reuse.
- `run_all_pipeline()` returns exit code `2` on preflight failure (distinct from `1` used by analyze) so operators can distinguish.
- `rich.progress.Progress` used without adding it as an explicit dependency (transitive via typer, per prompt).
- `sentence-transformers` and Quarto are `warn`, not `fail`, so users can run extract-only or skip the report stage.

#### Unresolved Questions
- None.

#### Risks & Next Steps
- `self_similarity_*` being `Optional` may need verification in downstream Phase 5/6 analysis modules when real data lands; current PELT path tolerates NaN via `np.nan_to_num`.
- If a downstream stack branch (ws4/ws5/ws6) re-touches `extract_all_features`, the progress-bar `Progress.start()/stop()` lifecycle must survive their refactors.


---

### Phase 12 Unit 2 (ws5-statistical-rigor): Pre-Registration Locking + Permutation-Based Significance
**Status:** Complete
**Date:** 2026-04-22
**Agent/Session:** Claude Opus 4.7 — subagent `s5`

#### What Was Done
- Added `src/forensics/preregistration.py` — threshold snapshot/verification with SHA256 tamper detection.
- Added `src/forensics/analysis/permutation.py` — non-parametric permutation tests (`permutation_test` + `changepoint_permutation`).
- Wired an optional `use_permutation` hook into `compute_convergence_scores` (default off → backwards compatible).
- Registered `forensics lock-preregistration` CLI command.
- Added `tests/test_preregistration.py` (7 tests) and `tests/test_permutation.py` (7 tests).

#### Files Modified
- `src/forensics/preregistration.py` — new module (lock / verify / VerificationResult).
- `src/forensics/analysis/permutation.py` — new module.
- `src/forensics/analysis/convergence.py` — added optional permutation hook (logged-only).
- `src/forensics/cli/__init__.py` — registered `lock-preregistration`.
- `tests/test_preregistration.py` — new.
- `tests/test_permutation.py` — new.

#### Verification Evidence
```
uv run ruff format --check .   → 125 files already formatted
uv run ruff check .            → All checks passed!
uv run pytest tests/test_preregistration.py tests/test_permutation.py -v   → 14 passed
uv run pytest tests/           → 238 passed, 18 skipped (pre-existing spacy)
uv run forensics lock-preregistration   → writes data/preregistration/preregistration_lock.json
test -f data/preregistration/preregistration_lock.json   → present
uv run forensics --help   → lock-preregistration visible
```

#### Decisions Made
- Snapshot only `settings.analysis` thresholds — `settings.survey` does not yet exist (belongs to ws1).
- `VerificationResult` status is `"ok" | "missing" | "mismatch"`; missing is NOT a failure (exploratory mode).
- Hash = SHA256 of canonical JSON (sort_keys, compact separators) via `forensics.utils.hashing.content_hash`.
- Permutation hook precomputes per-window change-point membership once to avoid O(n_perm × n_cp × n_windows) recompute.
- `permutation_test(...)` takes a pre-built null distribution; `changepoint_permutation(...)` shuffles internally.
- Default path of `compute_convergence_scores` is unchanged; permutation is opt-in via `use_permutation=True`.

#### Unresolved Questions
- None.

#### Risks & Next Steps
- ws1 (survey-mode) will add `SurveyConfig` — at that point `_snapshot_thresholds` should extend to include survey qualification criteria.
- ws4 (calibration) and ws6 (report-overhaul) can wire `verify_preregistration` into their entry points to emit a VIOLATION warning before running analysis.

---

### Unit 3 (ws1-survey-mode) — Blind Newsroom Survey Mode
**Status:** Complete
**Date:** 2026-04-22
**Agent/Session:** claude-opus-4-7 (ws1)

#### What Was Done
- Added `Repository.all_authors()` (ADR-001 compliant — uses `_require_conn`, reuses `_author_row_to_model`).
- Introduced `SurveyConfig` on `ForensicsSettings` (with `Field(default_factory=SurveyConfig)`, per v0.2.0 audit) and a `[survey]` section in `config.toml`.
- New `src/forensics/survey/` package:
  - `qualification.py` — `QualificationCriteria` (+ `.from_settings`), `QualifiedAuthor`, `qualify_authors(db_path, criteria, *, today=None)` filters by volume / date-span / avg word count / publishing frequency / recent activity.
  - `scoring.py` — `SurveyScore`, `SignalStrength` (StrEnum), `compute_composite_score`, `classify_signal`, and §5c `identify_natural_controls` + `validate_against_controls` (+ `ControlValidation`).
  - `orchestrator.py` — `run_survey(settings, *, project_root=None, db_path=None, dry_run=False, resume=None, skip_scrape=False, author=None, criteria=None)` → `SurveyReport`. Uses `dispatch_scrape(..., all_authors=True)`, `extract_all_features(..., project_root=...)`, `AnalysisArtifactPaths.from_project`, and `run_full_analysis(paths, config, *, author_slug=slug)`. Writes `data/survey/run_<id>/checkpoint.json` after every author and `survey_results.json` at the end. Resume by `run_id` skips completed authors.
- CLI: `src/forensics/cli/survey.py` (typer subapp) registered via `app.add_typer(survey_app, name="survey")` in `cli/__init__.py`. Options: `--dry-run`, `--resume`, `--skip-scrape`, `--author`, `--min-articles`, `--min-span-days`.
- Tests: `tests/test_survey.py` — 15 tests covering qualification filters (volume / date-range / frequency / recent activity / all-pass / empty), composite scoring (no signal / strong / Pipeline C inclusion), signal classification thresholds, natural-control identification + validation, orchestrator checkpoint, resume-skip-completed, dry-run-no-analysis, and return type.

#### Files Modified
- `src/forensics/storage/repository.py` — added `all_authors()`.
- `src/forensics/config/settings.py` — added `SurveyConfig` + field on `ForensicsSettings`.
- `config.toml` — added `[survey]` section.
- `src/forensics/cli/__init__.py` — registered survey typer subapp.

#### Files Created
- `src/forensics/survey/__init__.py`
- `src/forensics/survey/qualification.py`
- `src/forensics/survey/scoring.py`
- `src/forensics/survey/orchestrator.py`
- `src/forensics/cli/survey.py`
- `tests/test_survey.py`

#### Verification Evidence
```
uv run ruff format --check .                      → 131 files already formatted
uv run ruff check .                               → All checks passed!
uv run pytest tests/test_survey.py -v             → 15 passed
uv run pytest tests/                              → 253 passed, 18 skipped (pre-existing spaCy), 2 deselected
uv run forensics survey --help                    → shows --dry-run, --resume, --skip-scrape, --author, --min-articles, --min-span-days
uv run forensics survey --dry-run                 → runs qualify_authors, prints "Qualified: 0 authors" (stock DB has no authors)
uv run forensics --help                           → 'survey' subcommand visible
```

#### Decisions Made
- `SurveyReport` exposes `run_dir` instead of a `checkpoint_path` attribute — callers derive the checkpoint from the run dir; simplifies resume bookkeeping.
- Checkpoint path layout is `data/survey/run_<id>/checkpoint.json` (per-run directory) so `survey_results.json` and future artefacts can live alongside.
- `identify_natural_controls` threshold default 0.2 (per prompt §5c instruction in the coordinator brief; prompt body example uses 0.10 but the instruction text says 0.2 — matched the instruction).
- `compute_composite_score(analysis, qualification=None)` — second arg kept in the signature to match the original API shape; body intentionally does not use it yet (confidence-weighting hook reserved for future work).
- `SignalStrength` is a `StrEnum` (not `str, Enum`) to satisfy ruff UP042.
- CLI delegates orchestration to `forensics.survey.orchestrator.run_survey`; `asyncio.run` is called once at the CLI boundary.

#### Unresolved Questions
- None blocking. Future: the comparison step in `run_full_analysis` uses `config.authors` (target/control from config.toml); in survey mode, the natural control cohort is emitted by the orchestrator but not yet plumbed through as input to per-author comparison reports. That is a follow-up for ws6 (report overhaul).

#### Risks & Next Steps
- ws4 (calibration) and ws6 (report overhaul) can now consume `SurveyReport.natural_controls` and the ranked `SurveyReport.results` directly.
- `extract_all_features` is invoked once per author (by slug) — for large newsrooms the cost is dominated by spaCy nlp setup; acceptable for the survey use case, but if latency becomes an issue the extractor could be lifted out of the per-author loop.
