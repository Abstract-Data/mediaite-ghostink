# AGENTS.md
# Version: 0.3.0
# Last Updated: 2026-04-20
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
- `src/forensics/cli.py` — command-line interface

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
- Check `forensics/utils/` before implementing any helper function — reuse existing utilities
- Use lazy initialization for module-level mutable state (asyncio.Lock, caches) to avoid stale event-loop binding

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
- Open a new SQLite connection per repository call — use the `Repository` class pattern (see ADR-001)

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

## Learned User Preferences

- When implementing tasks from a numbered repository plan, do not edit the plan markdown file itself; only complete the assigned to-dos.
- For prompt-library work, ship substantive changes as a new immutable `v*.md` snapshot and advance `current.md`, `versions.json`, and `CHANGELOG.md` together instead of rewriting prior frozen versions.
- For Notion-linked specs or reports in this workspace, use the Notion MCP tools when a normal URL fetch returns no page body (Notion pages are often auth-walled to anonymous HTTP).

## Learned Workspace Facts

- Git remote `origin` targets **Abstract-Data/mediaite-ghostink** on GitHub; `git remote -v` may show an SSH form if HTTPS URLs are rewritten in Git config.
- **`requires-python`** in `pyproject.toml` is **`>=3.13,<3.14`** so the declared scientific and ML dependency set resolves against published wheels.
- Phase 2 discovery and metadata scraping persist **`data/authors_manifest.jsonl`**, **`data/scrape_errors.jsonl`**, and **`data/articles.db`** at the repository root (paths resolved via `get_project_root()`).
- GitButler (`but`) from this repo: authenticate the forge once (`but config forge auth`); for GitHub PRs ensure the integration target is **`origin/main`** (not `gb-local/main`). If `but config target` refuses while virtual branches are applied, `but unapply` the stack first, set the target, then `but apply` again before `but push` / `but pr new`.
