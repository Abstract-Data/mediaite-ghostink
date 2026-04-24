# AGENTS.md
# Version: 0.4.0
# Last Updated: 2026-04-23
# Environment: dev
# Model: gpt-5-3-codex
# Fallback Model: gpt-5.1
# Project: mediaite-ghostink
# Maintainer: John Eakin / Abstract Data LLC

You are an expert Python data engineer working on this **forensic analysis pipeline** project.

## Project Profile

- **Name:** mediaite-ghostink
- **Type:** pipeline (forensic analysis)
- **Python:** 3.13
- **Package Manager:** uv
- **Framework:** None (pure pipeline)
- **AI Framework:** pydantic-ai
- **Data Stack:** Polars, DuckDB, SQLite, Parquet, sentence-transformers
- **CLI:** Typer (`uv run forensics`)

## Agent Scope

```
Reads:    src/, tests/, docs/, .env.example, notebooks/, data/, prompts/
Writes:   src/, tests/, docs/, .claude/, prompts/, project config files
Executes: uv, ruff, pytest, git (feature branches only), gh (read + PR creation)
Off-limits: .env, /secrets/, production infrastructure, unrelated repositories
```

Agents must not operate outside declared boundaries without human approval.

---

## Working Rules

Durable operating rules for every agent in this repo.

- **Use `uv run` for every Python command.** Never invoke `python`, `pytest`, or `ruff` directly — it will hit the wrong interpreter.
- **Preserve the stage boundary contract.** `scrape → extract → analyze → report` is load-bearing: do not merge stages, swap data models, or move files between stages without explicit approval.
- **Data goes under `data/` only.** No writes outside `data/`, `src/`, `tests/`, `docs/`, `.claude/`, `prompts/`, or project config files.
- **LazyFrame over DataFrame.** Use Polars `LazyFrame` and defer `.collect()` until the terminal step in a pipeline stage.
- **Embedding model is pinned.** `sentence-transformers/all-MiniLM-L6-v2` (384-dim). Changes require a MAJOR version bump on the relevant prompt.
- **Prompts are immutable once released.** Follow the versioning contract in `prompts/README.md` — new content = new `vX.Y.Z.md`; `current.md` is a copy of the latest release.
- **Minimal diffs, small commits.** Ship fixes surgically; do not refactor adjacent code unless asked.
- **Add tests for behavior changes.** TDD per `docs/TESTING.md`; property-based tests via Hypothesis for hashing/normalization utilities.
- **Update session boundary files:** append a block to `HANDOFF.md` at the end of every multi-step task; log new operational knowledge in `docs/RUNBOOK.md`; append a Sign to `docs/GUARDRAILS.md` on any failure pattern that recurs 3+ times.

---

## Commands

### Development

```bash
uv sync                          # Install/sync dependencies
uv run forensics --help          # Show pipeline CLI help
uv run forensics scrape          # Run scrape stage
uv run forensics extract         # Run feature extraction
uv run forensics analyze         # Run analysis stage
uv run forensics report          # Generate report
uv run forensics all             # Run full pipeline
```

### Quality

```bash
uv run ruff check .              # Lint code
uv run ruff format --check .     # Format check
uv run ruff format .             # Auto-format
uv run pytest tests/ -v          # Run all tests
uv run pytest tests/ -v --cov=src --cov-report=term-missing  # With coverage
uv run pytest -k "test_name"     # Run specific test
```

### Testing Strategy

```bash
# Fast feedback loop
uv run pytest tests/unit -x      # Stop on first failure

# Before commits — comprehensive
uv run pytest --cov=src --cov-report=term-missing

# Property-based testing with Hypothesis
uv run pytest tests/ -v --hypothesis-show-statistics
```

---

## Pipeline Architecture

This is a deterministic forensic pipeline: `scrape → extract → analyze → report`.

### Stage Contracts

- `scraper.scrape(seed_urls)` → `list[ScrapedDocument]` — WordPress REST API + HTML fetch
- `features.extract_features(documents, keywords)` → `list[FeatureVector]` — lexical, structural, content, productivity features
- `analysis.analyze_features(feature_records)` → `list[AnalysisResult]` — change-point detection, embedding drift, convergence
- `pipeline.run_report(config)` → `Path` — generated markdown/notebook report

### Data Flow

```
WordPress REST API → SQLite (write store)
                   → Parquet (feature store via Polars)
                   → DuckDB (analytical queries)
                   → JSONL (transparency export)
                   → Markdown/Notebook (reports)
```

### File Outputs

- `data/raw/documents.json` — scraped article content
- `data/features/features.parquet` — extracted feature vectors
- `data/analysis/analysis.json` — analysis results
- `data/reports/report.md` — generated report
- `data/pipeline/summary.json` — pipeline run metadata

### Key Modules

- `src/forensics/config/` — runtime configuration (pydantic-settings, config.toml + FORENSICS_ env prefix)
- `src/forensics/models/` — stage data models (AuthorManifest, Author, Article, FeatureVector, EmbeddingRecord, ChangePoint, ConvergenceWindow, DriftScores, HypothesisTest, AnalysisResult)
- `src/forensics/scraper/` — WordPress REST API discovery + HTML fetch with BeautifulSoup
- `src/forensics/features/` — feature extraction (lexical, structural, content, productivity, embeddings)
- `src/forensics/analysis/` — change-point detection (PELT, BOCPD, Chow, CUSUM), embedding drift, convergence scoring
- `src/forensics/storage/` — SQLite repository + Parquet persistence + DuckDB queries
- `src/forensics/pipeline.py` — orchestration layer
- `src/forensics/cli/` — command-line interface (Typer)

---

## Model Configuration

```
Primary:  gpt-5-3-codex
Fallback: gpt-5.1
Notes:    Primary used for all generation tasks. Fallback for regression checks
          and validation passes. AI baseline generation (Phase 6) uses GPT-4o
          for synthetic article generation to avoid contaminating analysis.
```

---

## Execution Sequence (include in complex tasks)

Before beginning work on a multi-step task, explicitly state:

1. Which AGENTS.md rules apply to this task
2. Which GUARDRAILS.md Signs are relevant
3. Current scope boundaries (Reads / Writes / Off-limits)
4. Which commands to run for validation

For long sessions, append "Remember: apply all AGENTS.md rules" to prompts when the agent begins drifting.

---

## Risk-Classified Planning

Before editing any code on a multi-step task, require an explicit plan with risk classification.

**Coordinator preface (include at every session start or task handoff):**

> mediaite-ghostink is a forensic analysis pipeline investigating AI writing adoption.
> Stage boundaries (scrape/extract/analyze/report) and data model contracts are architecturally sacred.
> Known landmines: embedding model versioning, WordPress API rate limits, Parquet schema evolution.
>
> Before making any edits, propose a numbered step-by-step plan.
> Classify each step as LOW, MEDIUM, or HIGH risk.

**Risk tier behavior:**

- **LOW** — proceed autonomously; no special gates required
- **MEDIUM** — show planned file changes before applying; confirm approach
- **HIGH** — ask clarifying questions first, propose tests, show exact diffs, require explicit approval

---

## Claude Code Hooks

Hooks enforce hard constraints that language instructions cannot guarantee. Registered in `.claude/hooks.json`:

| Hook | Severity | Description |
|------|----------|-------------|
| Domain Purity Check | WARNING | Flags framework imports in domain/core/logic/services layers |
| SQL Injection Prevention | BLOCKER | Catches f-strings/concat/.format()/% in SQL text() calls |
| Router Boundary Check | WARNING | Flags direct DB operations in router/api layers |
| No print() in Production | BLOCKER | Flags print() in src/ production code. Also enforced by ruff rule `T201`. |
| Environment Variable Leak | WARNING | Flags os.environ usage outside config.py |
| Function Length Guard | WARNING | Flags functions exceeding 50 lines in `src/forensics/`. Excludes algorithm implementations marked `# complexity: justified`. |
| Hand-Built Data Path | WARNING | Flags `/ "data" / "features"` or `/ "data" / "analysis"` path construction outside `AnalysisArtifactPaths`. |

---

## Fluent Patterns — Polars

Fluent method chaining is the standard for all Polars code. Every transformation should read as a top-to-bottom declaration of intent. Break chains at logical boundaries — one operation per line.

```python
# GOOD — Fluent chain
def extract_lexical_features(articles: pl.LazyFrame) -> pl.LazyFrame:
    return (
        articles
        .filter(pl.col("word_count") >= 50)
        .with_columns(
            (pl.col("unique_words") / pl.col("word_count")).alias("ttr"),
            pl.col("text").map_elements(compute_yules_k, return_dtype=pl.Float64).alias("yules_k"),
        )
        .sort("author_id", "publish_date")
    )

# BAD — Intermediate variables
filtered = articles.filter(pl.col("word_count") >= 50)
with_ttr = filtered.with_columns(...)
```

Use `LazyFrame` over `DataFrame` — defer `.collect()` until the end. Use `.pipe()` for composing pipeline stages.

---

## Data Validation

Use Pydantic for row-level validation and Polars expressions for column-level checks.

```python
from pydantic import BaseModel, field_validator

class Article(BaseModel):
    url: str
    author_id: int
    publish_date: datetime
    word_count: int
    text: str

    @field_validator("word_count")
    @classmethod
    def minimum_content(cls, v: int) -> int:
        if v < 50:
            raise ValueError("Article must have at least 50 words")
        return v
```

---

## Tool Permissions by Mode

### dev mode

```
Reads:    src/, tests/, docs/, .env.example, AGENTS.md, ARCHITECTURE.md, prompts/, data/
Writes:   src/, tests/, docs/, prompts/
Executes: uv, ruff, pytest, git (feature branches only), gh (read + PR creation)
```

### review mode

```
Reads:    src/, tests/, docs/, .env.example, AGENTS.md, ARCHITECTURE.md
Writes:   NONE — produce findings only, do not modify source code
Executes: git diff, git log, ruff check, pytest (read-only analysis)
```

### research mode

```
Reads:    ALL project files, external docs via WebSearch/WebFetch
Writes:   docs/research/, HANDOFF.md only
Executes: grep, glob, git log, git blame (exploration only — no builds, no tests)
```

If an agent in `review` mode is about to call `Edit` on a source file, it should stop and note: "Review mode — cannot modify source. Flagging for dev-mode follow-up."

---

## Conflict Resolution Hierarchy

When multiple concerns compete within a single task, resolve conflicts using this priority order (highest wins):

1. **Security** — vulnerabilities override all other concerns
2. **Correctness** — correct behavior overrides performance and style
3. **Data integrity** — schema safety, migration reversibility, referential integrity
4. **Performance** — only when backed by measurement, not speculation
5. **Maintainability** — boring, readable code over clever solutions
6. **Style** — formatting and naming are lowest priority

---

## Definition of Done

A task is complete when **all** of the following are true:

### Code Quality

- All tests pass (`uv run pytest tests/ -v`)
- No linting errors (`uv run ruff check .`)
- No formatting violations (`uv run ruff format --check .`)
- Type hints present on all new public functions

### Documentation Hygiene

- **Always:** Append a completion block to `HANDOFF.md` (status, files changed, decisions, next steps)
- **Always:** If you discovered new debug commands, setup steps, error fixes, or environment knowledge → append to `docs/RUNBOOK.md`
- If behavior or policy changed → ADR updated or new ADR created in `/docs/adr/`
- If ops procedure changed → `docs/RUNBOOK.md` updated with diagnosis/fix
- If new tool or guardrail added → `AGENTS.md` version bumped (MINOR or PATCH)

### Safety & Security

- No secrets, tokens, or credentials in committed code
- No bare `print()` statements — use logging
- No `eval()` or `exec()` with user input

### Rollback Readiness (for risky operations)

- Rollback plan documented in PR description
- Feature flag or kill switch in place if applicable

---

## Core Standards

### Code Style

| Type | Convention | Examples |
|------|-----------|----------|
| Functions/variables | `snake_case` | `extract_features`, `word_count` |
| Classes | `PascalCase` | `FeatureVector`, `AnalysisResult` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `WORDPRESS_API_BASE` |
| Private methods | `_leading_underscore` | `_compute_ttr`, `_parse_html` |

### Git Workflow

Follow conventional commits:

```
feat: add embedding drift analysis
fix: resolve rate limit handling in scraper
refactor: extract validation logic to separate module
test: add property tests for feature extraction
docs: update architecture for new storage layer
```

Before every commit:

```bash
uv run ruff format .              # Format code
uv run ruff check . --fix         # Fix auto-fixable issues
uv run pytest tests/ -v           # All tests must pass
```

### Environment Variables

```python
# GOOD — Use pydantic-settings
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FORENSICS_",
        toml_file="config.toml",
    )
    data_dir: Path = Path("./data")
    report_path: Path = Path("./data/reports/report.md")

settings = Settings()
```

---

## Boundaries & Guardrails

**GUARDRAILS.md** holds persistent safety constraints and "Signs" (failure patterns to avoid). When working on this repo:

- Load and apply GUARDRAILS.md for safety-critical or schema work. Respect all Signs.
- **Append learned signs:** When you detect a failure pattern (3+ consecutive identical errors, circular tool loops, or context pollution), append a new Sign to the Agent-Learned Signs section in GUARDRAILS.md.

**RUNBOOK.md** is the operational quick reference. When you resolve a new recurring issue or add a new debug command, update RUNBOOK.md.

### ALWAYS DO

- Write type hints for all functions and classes
- Use async/await for I/O operations (httpx calls, file I/O)
- Add docstrings to public functions
- Write tests for new features
- Run `ruff format` before committing
- Validate all external input with Pydantic models
- Use `LazyFrame` over `DataFrame` — defer `.collect()` until the end
- Chain fluently — one operation per line in a single expression
- Log row counts at each pipeline stage
- Check `forensics/utils/` and `forensics/analysis/utils.py` before implementing any helper function — reuse existing utilities
- Use lazy initialization for module-level mutable state (asyncio.Lock, caches) to avoid stale event-loop binding
- Use `AnalysisArtifactPaths` for all paths under `data/` — never hand-build `project_root / "data" / ...` paths
- Use `ensure_repo(db_path, repo)` context manager when a function accepts an optional `Repository` — never duplicate the `if repo / else open` branching
- Use `load_feature_frame_for_author()` from `analysis/utils.py` — never inline the load-filter-fallback pattern
- Keep functions under 50 lines (excluding docstrings). If an algorithm justifies more, add `# complexity: justified` and document why.

### ASK FIRST

- Adding new dependencies (check with `uv add`)
- Changing data model contracts or stage boundaries
- Modifying the storage layer schema
- Switching between Polars and Pandas
- Materializing large datasets in memory (`.collect()` on 10M+ rows)
- Altering CI/CD configuration

### NEVER DO

- Commit secrets, API keys, or credentials
- Use `print()` instead of logging
- Swallow exceptions with bare `except:`
- Modify code in `site-packages/` or `.venv/`
- Use `eval()` or `exec()` with user input
- Use intermediate variables where a fluent chain works
- Call `.collect()` mid-pipeline then re-wrap as `LazyFrame`
- Hardcode file paths — always parameterize
- Silently drop rows without logging counts
- Break stage boundaries or data model contracts without approval
- Re-implement utilities that already exist in `forensics/utils/` — check before writing private helpers
- Create module-level `asyncio.Lock`, `asyncio.Event`, or `asyncio.Semaphore` instances eagerly at import time — use lazy initialization or pass as parameters
- Open a new SQLite connection per repository call — use the `Repository` class pattern (see ADR-005)
- Construct `data/` paths manually — use `AnalysisArtifactPaths` methods (see GUARDRAILS Sign)
- Duplicate the `if repo is not None: ... else: with Repository(db_path)` pattern — use `ensure_repo()` (see Phase 13)
- Add C901 suppressions to `pyproject.toml` without a decomposition plan or tracking comment

---

## Prompt Artifact Management

Agent system prompts are versioned artifacts in `/prompts/`. Each prompt family follows:

```
prompts/
  {agent-name}/
    v{MAJOR.MINOR.PATCH}.md    # versioned snapshot (immutable)
    current.md                 # copy of active version
    versions.json              # machine-readable version index
    CHANGELOG.md               # append-only history
```

See `prompts/README.md` for the full versioning contract, bump rules, and release workflow.

---

## Environment-Specific Variants

| File | Purpose |
|------|---------|
| `AGENTS.md` | Dev/local — canonical base, most permissive |
| `AGENTS.staging.md` | Staging — pre-prod validation, restricted writes |

---

## Architectural Constraints

- Use `uv run` for all Python execution
- Preserve stage boundaries and data model contracts
- Keep writes contained under `data/` unless requirements explicitly expand storage targets
- Prefer additive, low-risk changes over broad rewrites
- Use deterministic, testable modules over notebook-only logic

---

## Notion References

- Tasks database: https://www.notion.so/abstractdata/mediaite-ghostink-tasks
- Project page: https://www.notion.so/abstractdata/Colby-Hall-AI-Use-Investigation-34a7d7f56298807a8e38e05e30edc3d5
- Client page: https://www.notion.so/abstractdata/Mediaite-2f47d7f5629880659e33d3eed6e2b498
- GitButler skill template (Claude Code + Cursor): https://www.notion.so/34a7d7f56298816eae8be56c8fd8c4aa
- GitButler playbook — virtual branches for parallel agent work: https://www.notion.so/34a7d7f56298816fa6d2cd77b6cebfc8

## Learned User Preferences

- When implementing tasks from a numbered repository plan or an attached Cursor plan artifact, do not edit the plan markdown file itself; only complete the assigned to-dos.
- When the user explicitly asks to mark work in progress on an attached Cursor plan, change only status or checkbox metadata; do not rewrite the plan body or task descriptions.
- For prompt-library work, ship substantive changes as a new immutable `v*.md` snapshot and advance `current.md`, `versions.json`, and `CHANGELOG.md` together instead of rewriting prior frozen versions.
- For Notion-linked specs or reports in this workspace, use the Notion MCP tools when a normal URL fetch returns no page body (Notion pages are often auth-walled to anonymous HTTP).
- When syncing GitButler guidance from Notion into this repo, add a companion skill under a distinct name (for example `gitbutler-workflow`) rather than replacing the existing GitButler skill wholesale.
- For Typer/Rich CLI help tests that assert literal `--flag` substrings, disable color on `CliRunner.invoke` and strip ANSI escape sequences so Rich markup does not break contiguous flag text.
- Prefer refactoring long functions and shared helpers over adding new McCabe C901 suppressions; if a suppression is unavoidable, pair it with a short decomposition plan or tracking comment rather than silent noqa growth.
- When expanding README or onboarding docs for this repo, document which models and measurements the pipeline uses, how to run it locally, and chain-of-custody style forensic expectations; add diagrams or flow figures when they materially clarify stages or data flow.

## Learned Workspace Facts

- Git remote `origin` targets **Abstract-Data/mediaite-ghostink** on GitHub; `git remote -v` may show an SSH form if HTTPS URLs are rewritten in Git config.
- Architectural decision records live under **`docs/adr/`**; keep a single ADR-style tree rather than reintroducing a parallel `docs/decisions/` layout unless the repo convention is explicitly changed.
- Ruff: this repo’s **`.ruff.toml`** only **`extend`s `pyproject.toml`**, so lint rules (including **`C901`**) come from **`[tool.ruff.lint]`** in `pyproject.toml`. If you add **`[tool.ruff.lint.per-file-ignores]`** in `pyproject.toml`, keep valid TOML (for example a multi-line table); inline tables cannot span lines and will break parsing. CI (`.github/workflows/ci-tests.yml`) uses **`uv sync --extra dev --extra tui`** and relies on **`addopts`** for **`--cov=forensics`** so **`coverage.json`** matches a local **`uv run pytest`** (no second **`--cov=src`** flag).
- Phase 2 discovery and metadata scraping persist **`data/authors_manifest.jsonl`**, **`data/scrape_errors.jsonl`**, and **`data/articles.db`** at the repository root (paths resolved via `get_project_root()`).
- GitButler (`but`): follow the repo-local skill at `.claude/skills/gitbutler/SKILL.md` (mirrored at `.cursor/skills/gitbutler/SKILL.md`). For the Notion playbook add-on (parallel agents, JSON workflow), see `.claude/skills/gitbutler-workflow/SKILL.md` (mirrored under `.cursor/skills/gitbutler-workflow/`). From this repo: authenticate the forge once (`but config forge auth`); for GitHub PRs ensure the integration target is **`origin/main`** (not `gb-local/main`). If `but config target` refuses while virtual branches are applied, `but unapply` the stack first, set the target, then `but apply` again before `but push` / `but pr new`.
- The `forensics` console script imports the **`forensics.cli` package** (`src/forensics/cli/` Typer app); the old monolithic `src/forensics/cli.py` was removed after the Typer migration—treat package modules as the CLI source of truth when updating docs or tracing dispatch.
- `forensics scrape --all-authors` walks **every** author in `data/authors_manifest.jsonl` for metadata (and skips the placeholder guard on scrape-like invocations); `extract` / `analyze` / reporting still resolve study authors from `config.toml` via `resolve_author_rows` unless narrowed with `--author`. Survey scrape paths accept **`--post-year-min`** and **`--post-year-max`** (inclusive calendar years) to bound WordPress article pulls without ingesting full site history.
- **`forensics dashboard`** runs the Textual full-screen pipeline view (install the **`tui`** extra); it conflicts with **`--no-progress`**. For non-TUI runs, root **`--no-progress`** turns off Rich live progress (including on `forensics all`, `forensics survey`, scrape, and extract); only one live UI mode should be active at a time.
- README-aligned local modeling and reporting expect **`uv run python -m spacy download en_core_web_md`** for extraction and **Quarto on `PATH`** when running **`forensics report`** or **`forensics all`** (plus non-placeholder `config.toml` authors for guarded scrape paths).
- In `collect_article_metadata`, author ingestion runs **concurrently** up to **`scraping.max_concurrent`**, all tasks share one **`RateLimiter`**, SQLite writes go through a per-run **`asyncio.Lock`**, and per-author failures append to **`data/scrape_errors.jsonl`** without stopping the whole batch.
- Each **`forensics analyze`** run invokes **`verify_preregistration(settings)`** before downstream stages; **`data/analysis/run_metadata.json`** records **`preregistration_status`** (`ok`, `missing`, or `mismatch`). Optional convergence permutation nulls are configured on **`AnalysisConfig`** (`convergence_use_permutation` defaults false, plus iteration count and seed) and are passed into **`compute_convergence_scores`** from the analysis orchestrator and comparison paths; when enabled, empirical p-values are **logged only** and do not change detected windows.
- Survey **`validate_against_controls`** in the shipped Phase 12 contract returns composite-level **`ControlValidation`** summaries for the natural-control cohort; per-feature two-sample tests against loaded feature frames are **out of scope** unless added as a separate tracked task.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **mediaite-ghostink** (5304 symbols, 11108 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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
| Work in the Tests area (467 symbols) | `.claude/skills/generated/tests/SKILL.md` |
| Work in the Unit area (222 symbols) | `.claude/skills/generated/unit/SKILL.md` |
| Work in the Features area (83 symbols) | `.claude/skills/generated/features/SKILL.md` |
| Work in the Analysis area (66 symbols) | `.claude/skills/generated/analysis/SKILL.md` |
| Work in the Scraper area (53 symbols) | `.claude/skills/generated/scraper/SKILL.md` |
| Work in the Cli area (49 symbols) | `.claude/skills/generated/cli/SKILL.md` |
| Work in the Survey area (45 symbols) | `.claude/skills/generated/survey/SKILL.md` |
| Work in the Forensics area (44 symbols) | `.claude/skills/generated/forensics/SKILL.md` |
| Work in the Integration area (35 symbols) | `.claude/skills/generated/integration/SKILL.md` |
| Work in the Screens area (33 symbols) | `.claude/skills/generated/screens/SKILL.md` |
| Work in the Storage area (32 symbols) | `.claude/skills/generated/storage/SKILL.md` |
| Work in the Baseline area (30 symbols) | `.claude/skills/generated/baseline/SKILL.md` |
| Work in the Tui area (29 symbols) | `.claude/skills/generated/tui/SKILL.md` |
| Work in the Scripts area (21 symbols) | `.claude/skills/generated/scripts/SKILL.md` |
| Work in the Progress area (20 symbols) | `.claude/skills/generated/progress/SKILL.md` |
| Work in the Calibration area (19 symbols) | `.claude/skills/generated/calibration/SKILL.md` |
| Work in the Reporting area (14 symbols) | `.claude/skills/generated/reporting/SKILL.md` |
| Work in the Evals area (14 symbols) | `.claude/skills/generated/evals/SKILL.md` |
| Work in the Migrations area (6 symbols) | `.claude/skills/generated/migrations/SKILL.md` |
| Work in the Config area (4 symbols) | `.claude/skills/generated/config/SKILL.md` |

<!-- gitnexus:end -->
