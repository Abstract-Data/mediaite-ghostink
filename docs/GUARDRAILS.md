# Guardrails

## Core Operating Rules

- Use `uv run` for all Python commands.
- Keep changes incremental and architecture-preserving.
- Do not edit secrets (`.env`, credentials) without explicit approval.
- Avoid destructive git commands unless explicitly requested.
- Preserve stage boundaries (scrape → extract → analyze → report) — do not merge or bypass stages.

## Data Safety

- Treat scraped content as untrusted input — validate and sanitize before processing.
- Avoid logging sensitive source material in plain text.
- Persist outputs only through `forensics.storage` helpers unless a task requires another sink.
- Never expose author PII (email addresses, phone numbers) in reports or logs.
- Scrape only public content; respect robots.txt and rate limits.

### Stored raw HTML (P2-SEC-1)

Raw HTML is written under `data/raw/` for reproducibility and parsed locally with BeautifulSoup. Treat these files as **untrusted data at rest**: do not serve them over HTTP without a dedicated sanitizer, do not `eval` or embed them in rich clients, and keep the dataset off shared drives without access controls. Text extraction strips tags for `clean_text`, but the on-disk HTML is unchanged from the origin server.

## PII Handling

- Author names are public data (bylines) — acceptable in analysis and reports.
- Author contact information (email, phone, social handles) must not be stored or logged.
- If PII is discovered in scraped content, redact before persisting to storage.
- Never include PII in error messages, logs, or exception tracebacks.

## Error Classification

| Severity | Description | Action |
|----------|-------------|--------|
| CRITICAL | Data corruption, security breach, PII exposure | Stop immediately. Alert human. Do not retry. |
| HIGH | Pipeline stage failure, storage write error | Log error. Retry once with backoff. Escalate if retry fails. |
| MEDIUM | API rate limit, transient network error | Log warning. Retry with exponential backoff (max 3 attempts). |
| LOW | Missing optional field, non-critical validation warning | Log info. Continue processing. Flag in report. |

## Signs Architecture

Signs are documented failure patterns that agents must recognize and avoid. They encode lessons learned from past mistakes and serve as guardrails against known pitfalls.

Each Sign has:
- **Trigger:** The condition or pattern that activates this Sign
- **Instruction:** What to do when the trigger is detected
- **Reason:** Why this matters
- **Provenance:** Where the Sign came from (Initial or Agent-learned)

### Initial Signs

**Sign: WordPress API Pagination Drift**
- Trigger: Scraper receives fewer results than expected from paginated API calls
- Instruction: Always verify total page count from `X-WP-TotalPages` header. Do not assume fixed page sizes. Re-fetch if count changes mid-scrape.
- Reason: WordPress REST API pagination can shift when posts are published/unpublished during scraping.
- Provenance: Initial — known WordPress API behavior.

**Sign: Embedding Model Version Mismatch**
- Trigger: Feature extraction produces embeddings with unexpected dimensions or cosine similarities outside [0, 1] range
- Instruction: Verify `sentence-transformers` model version matches `all-MiniLM-L6-v2`. Check embedding dimensionality (should be 384). Never mix embeddings from different model versions.
- Reason: Model updates can silently change embedding space, invalidating all downstream drift analysis.
- Provenance: Initial — known sentence-transformers behavior.

**Sign: Parquet Schema Evolution**
- Trigger: Writing features to Parquet fails with schema mismatch error
- Instruction: Never modify existing Parquet column types. Add new columns only. If schema must change, create a new versioned file and update the pipeline config.
- Reason: Parquet is columnar and schema changes corrupt existing data or break downstream readers.
- Provenance: Initial — Polars/Parquet constraint.

**Sign: Rate Limit Cascade**
- Trigger: Multiple scraper threads hitting rate limits simultaneously
- Instruction: Use single-threaded scraping with jitter (0.5-2.0s). If rate limited, back off exponentially starting at 5s. Log all rate limit events.
- Reason: Aggressive retry without backoff can trigger IP-level blocks on WordPress sites.
- Provenance: Initial — WordPress hosting behavior.

**Sign: Collect-in-Middle Anti-Pattern**
- Trigger: Code calls `.collect()` on a Polars LazyFrame mid-pipeline then re-wraps as LazyFrame
- Instruction: Defer `.collect()` to the end of the pipeline. Use `.pipe()` for stage composition. If materialization is truly needed (e.g., for row count logging), use `.fetch()` for sampling or log after final collect.
- Reason: Materializing mid-pipeline defeats lazy evaluation, wastes memory, and breaks query optimization.
- Provenance: Initial — Polars best practice.

### Agent-Learned Signs

<!-- Agents: append new Signs here when you detect failure patterns (3+ consecutive identical errors, circular tool loops, or context pollution). Use the format above. -->

**Sign: Repository Used Outside an Active Session**
- Trigger: Code calls `Repository(db_path).upsert_*` without entering `with Repository(db_path) as repo:` (or passes `db_path` into ad-hoc `sqlite3.connect` helpers outside `repository.py`).
- Instruction: Always use ``with Repository(path) as repo:`` for SQLite writes/reads. For scrape orchestration, prefer injecting the same `repo` into `collect_article_metadata` / `fetch_articles` when multiple operations should share one transaction. See ADR-001.
- Reason: Session-scoped connections enable WAL + DEFERRED transactions and batch commits; using a closed or non-entered repository raises `RuntimeError` and prevents silent autocommit sprawl.
- Provenance: Agent-learned — 2026-04-20 code review (P1-ARCH-1, RF-SMELL-001), updated 2026-04-21 after `Repository` context manager landed.

**Sign: Stage Directly Imports Another Stage's Internals**
- Trigger: A module in `scraper/` imports from `storage/repository.py` directly (e.g., `from forensics.storage.repository import upsert_article`), or any stage module imports internal functions from a different stage.
- Instruction: Stages should return data structures to the orchestration layer (`forensics/cli/` or `pipeline.py`), which handles persistence. If a stage needs to read data, it should receive it as a parameter, not reach into another stage's storage layer.
- Reason: Stage boundaries are architecturally sacred (ARCHITECTURE.md §Stage Contracts). Direct cross-stage imports create tight coupling that makes stages untestable in isolation and prevents swapping storage backends.
- Provenance: Agent-learned — 2026-04-20 code review (P2-ARCH-3).

**Sign: God Function Exceeding 50 Lines in CLI/Orchestration**
- Trigger: Any function in `forensics/cli/` or `pipeline.py` exceeds 50 lines (excluding docstrings and blank lines), or a single function handles more than 3 distinct flag/command combinations via sequential `if` blocks.
- Instruction: Decompose into a command registry or strategy mapping (see ADR-002). Each pipeline operation should be a separate callable registered in a dispatch table. New phases must slot in via registration, not by adding more `if` branches.
- Reason: The 117-line `_async_scrape` function with ~18 cyclomatic complexity was flagged as the single most critical refactoring issue. Adding Phase 4–7 flags to this pattern would make it unmaintainable.
- Provenance: Agent-learned — 2026-04-20 code review (RF-CPLX-001, P2-CQ-2).

**Sign: Hand-Built Data Paths Instead of Centralized Helpers**
- Trigger: Code constructs paths like `project_root / "data" / "features" / f"{slug}.parquet"` or `project_root / "data" / "analysis" / ...` manually instead of using `AnalysisArtifactPaths` methods.
- Instruction: Always use `AnalysisArtifactPaths.features_parquet(slug)`, `.analysis_json(slug)`, `.drift_dir(slug)`, etc. If the method doesn't exist, add it to `AnalysisArtifactPaths` first. Never hand-build paths to `data/` subdirectories.
- Reason: Flagged in 3 of 5 review runs (RF-DRY-003). Hand-built paths create shotgun surgery when directory layout changes and are a recurring source of DRY violations.
- Provenance: Agent-learned — 2026-04-22 cross-run pattern analysis (5 reviews).

**Sign: Inlined Feature Frame Loading Instead of Utility**
- Trigger: Code calls `pl.scan_parquet(path).filter(pl.col("author_id") == ...)` or equivalent outside of `analysis/utils.py`.
- Instruction: Use `load_feature_frame_for_author()` from `forensics.analysis.utils`. If the utility doesn't meet your needs, extend it — don't duplicate inline.
- Reason: Flagged in 3 of 5 review runs (RF-DRY-002). The load-filter-fallback pattern was duplicated in 5 locations.
- Provenance: Agent-learned — 2026-04-22 cross-run pattern analysis.

**Sign: C901 Suppression Added Without Decomposition Plan**
- Trigger: A new `per-file-ignores` entry for C901 is added to `pyproject.toml` without a corresponding decomposition task.
- Instruction: Before adding a C901 suppression, first attempt to decompose the complex function. If decomposition is deferred, add an inline `# TODO(phase13): decompose — see RF-CX-NNN` comment AND create a tracking issue. Never suppress C901 silently.
- Reason: C901 suppressions grew from 7 to 9 across review runs without corresponding reduction effort. Each suppression hides real complexity debt.
- Provenance: Agent-learned — 2026-04-22 cross-run pattern analysis.

## Agent and Change Management

- Follow `AGENTS.md` in dev mode and `AGENTS.staging.md` in staging mode.
- Prefer small diffs with explicit validation steps.
- Document unresolved risks in `HANDOFF.md`.

## Validation Checklist

Before handoff or merge:

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run pytest tests/ -v`
4. If evals exist: `uv run pytest tests/evals/ -v`

## Escalation Triggers

Stop and request explicit approval before:

- Changing provider/system-level architecture
- Modifying deployment credentials or infrastructure bindings
- Introducing non-deterministic runtime dependencies into core pipeline paths
- Changing data model contracts or stage boundaries
- Modifying storage layer schema (SQLite, Parquet, DuckDB)
- Any operation classified as CRITICAL severity
