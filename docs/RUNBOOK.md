# Runbook

Operational quick reference. Agents: append new sections here whenever you discover debug techniques, resolve recurring errors, add CLI commands, or learn environment facts that future operators need.

## Local Setup

1. Install dependencies: `uv sync`
2. For Phase 10 (baseline generation): `uv sync --extra baseline`
3. Validate environment: `uv run ruff check . && uv run ruff format --check .`
4. Run tests: `uv run pytest tests/ -v`
5. Run with coverage: `uv run pytest tests/ -v --cov-report=term-missing` (coverage target `forensics` is configured in [`pyproject.toml`](../pyproject.toml) `addopts`)

## Pipeline Operations

- Run full pipeline: `uv run forensics all` — implementation: `src/forensics/pipeline.py` (`run_all_pipeline`). It runs **full scrape** (same as bare `forensics scrape` when no scrape flags are set), then extract, then `run_analyze(timeseries=True, convergence=True)` (**not** changepoint/drift unless you change the pipeline), then Quarto report. See [`docs/ARCHITECTURE.md`](ARCHITECTURE.md#forensics-all-end-to-end).
- Stage-by-stage (recommended when debugging):
  - `uv run forensics scrape` (use `--discover` / `--metadata` / `--fetch` etc. as needed; see `--help`)
  - `uv run forensics extract`
  - `uv run forensics analyze` (add `--changepoint`, `--drift`, … as needed). Each analyze run calls `verify_preregistration(settings)` before stages (see `src/forensics/cli/analyze.py`); threshold drift vs `data/preregistration/preregistration_lock.json` logs at WARNING, and `data/analysis/run_metadata.json` records `preregistration_status` (`ok` / `missing` / `mismatch`).
  - `uv run forensics report` (requires **Quarto** on `PATH`; output under `data/reports/` per `quarto.yml`)
- Extract probability features (Phase 9): `uv run forensics extract --probability`
- Generate AI baseline (Phase 10): `uv run python scripts/generate_baseline.py --author {slug}`
- Validate environment before a run: `uv run forensics preflight` (pass `--strict` to promote warnings to failures). Hard-fails on Python < 3.13, missing `en_core_web_sm`, disk < 5 GB, config parse errors, or placeholder authors; warns for Quarto/Ollama/sentence-transformers cache misses.
- Lock pre-registration thresholds: `uv run forensics lock-preregistration` writes `data/preregistration/preregistration_lock.json` (SHA256-hashed canonical JSON). Run **before** first `analyze` to convert the run from exploratory to confirmatory. Re-running simply overwrites with the current thresholds. Analyze always invokes `verify_preregistration` (same return statuses). See `src/forensics/preregistration.py`.
- Convergence permutation null (Phase 12 §5b): under `[analysis]` in `config.toml`, set `convergence_use_permutation = true` to draw an empirical null for each convergence window (p-values are **logged only**; detected windows are unchanged). Defaults: `convergence_use_permutation = false` (CPU), `convergence_permutation_iterations = 1000`, `convergence_permutation_seed = 42`. Wired from `src/forensics/config/settings.py` into `compute_convergence_scores` in `src/forensics/analysis/orchestrator.py` and `src/forensics/analysis/comparison.py`.
- Blind newsroom survey (Phase 12 §1): `uv run forensics survey` runs the full pipeline across every qualified author on the manifest and ranks them by composite AI-adoption signal. Options: `--dry-run` (list qualified authors, no analysis), `--resume <run_id>` (skip authors already in `data/survey/run_<id>/checkpoint.json`), `--skip-scrape` (reuse existing corpus), `--author <slug>` (single-author debug run), `--min-articles` / `--min-span-days` (override `[survey]` thresholds). Output lands under `data/survey/run_<id>/` with `checkpoint.json` (written after each author) and `survey_results.json` (ranked, with the natural control cohort). Thresholds default to `SurveyConfig` in `config.toml` (`min_articles=50`, `min_span_days=730`, `min_words_per_article=200`, `min_articles_per_year=12.0`, `require_recent_activity=true`, `recent_activity_days=180`). Natural controls are authors whose composite score ≤ 0.2 AND `SignalStrength.NONE`; see `src/forensics/survey/scoring.py::identify_natural_controls`.
- Calibration suite (Phase 12 §4): `uv run forensics calibrate` validates detector accuracy against synthetic ground truth. Options: `--positive-trials <n>` (spliced-corpus trials, default 5), `--negative-trials <n>` (unmodified-corpus trials, default 5), `--author <slug>` (target author; otherwise most prolific), `--seed <int>` (splice-date RNG, default 42), `--output <path>` (override report path), `--dry-run` (emit an empty report without touching the DB — smoke-test only). Positive trials substitute post-splice articles with Phase 10 baseline AI text loaded from `data/ai_baseline/<slug>/articles.json`; missing file triggers a warning and a best-effort no-op splice. Each trial runs in an isolated `data/calibration/run_<ts>/{positive,negative}_NN/` tree with its own `articles.db`. Final metrics (`sensitivity`, `specificity`, `precision`, `f1_score`, `median_date_error_days`) land in `data/calibration/calibration_<ts>.json`. A real calibration run is expensive (extract + full analysis per trial); the `--help` + pytest suite (`tests/test_calibration.py`) is the CI smoke test.
- Validate config + environment (Phase 12 §7a): `uv run forensics validate` parses `config.toml`, reports author count, runs `run_all_preflight_checks(settings)`, and prints PASS/WARN/FAIL per check. Exits `1` when any preflight check hard-fails (spaCy model missing, placeholder authors, disk < 5 GB, config parse error, Python < 3.13). Pass `--check-endpoints` to also probe `https://www.mediaite.com/wp-json/wp/v2/types` and `http://localhost:11434/api/tags` with a 3s timeout — endpoint results are reported as PASS/WARN but **do not** affect the exit code. Use as a pre-commit or CI gate before running the pipeline. Preflight logic lives in `src/forensics/preflight.py`; the probes live in `src/forensics/cli/__init__.py::_probe_endpoint`.
- Single-file DuckDB export (Phase 12 §7b): `uv run forensics export [--output PATH] [--no-features] [--no-analysis]` folds `data/articles.db` (authors + articles via DuckDB's `sqlite` extension), optional `data/features/*.parquet`, and optional `data/analysis/*_result.json` into a single `.duckdb` file (default `data/forensics_export.duckdb`). Query it with any DuckDB client (`duckdb data/forensics_export.duckdb` then `SHOW TABLES`). `ExportReport` returns `output_path`, `bytes_written`, and a `tables` dict of per-table rowcounts. The export lives in `src/forensics/storage/duckdb_queries.py::export_to_duckdb`; `*.duckdb` is gitignored.
- Interactive setup wizard (Phase 12 §2): `uv sync --extra tui` once (installs `textual>=1.0.0` + `rich>=13.0`), then `uv run forensics setup` (or the bundled `forensics-setup` script) launches a 5-step Textual wizard: **Dependencies** (Python / spaCy / sentence-transformers / Quarto / Ollama status with pass/warn/fail icons), **Discovery** (probes `articles.db` for existing authors and lets you pick blind-survey vs hand-pick mode), **Config** (generates a complete `config.toml` from user inputs with timestamped backup of any existing file), **Preflight** (re-runs `run_all_preflight_checks(settings)` against the freshly written config), and **Launch** (emits the recommended next CLI command — `forensics survey` or `forensics all` — and exits so the user runs it in the shell with live logs). Keybindings: `q` quit, `n` next, `b` back. Module lives at `src/forensics/tui/`; core helpers (`check_dependencies`, `generate_config`, `write_config`, `discover_authors_summary`) are unit-testable without the Textual runtime (see `tests/test_tui.py`). The `forensics setup` Typer subcommand exits `1` when the `tui` extra is not installed and prints a friendly install hint.
- Survey dashboard + calibration notebooks (Phase 12 §6a+§6c): after `forensics survey` or `forensics calibrate`, render the team-facing dashboard with Quarto — `quarto render notebooks/10_survey_dashboard.ipynb --to html` (top-10 ranked authors, composite-score histogram with natural-controls overlay, earliest-convergence-window timeline, preregistration verification) or `quarto render notebooks/11_calibration.ipynb --to html` (sensitivity/specificity/precision/F1/median-date-error table, confusion-matrix heatmap, date-error histogram). Both notebooks locate the most recent `data/survey/run_*/survey_results.json` / `data/calibration/calibration_*.json` automatically, and degrade gracefully (printing a `run forensics survey/calibrate first` hint) when no data is present — safe to re-render at any time.
- Per-author drill-down renders (Phase 12 §6b): notebooks 05-07 now carry a `parameters`-tagged cell. To render a per-author drill-down, pass the slug via Quarto parameters — `quarto render notebooks/05_change_point_detection.ipynb -P author_slug:some-slug --to html` (same for `06_embedding_drift.ipynb`, `07_statistical_evidence.ipynb`). Default is `author_slug = "all"` so existing renders are unchanged.
- Evidence-chain narrative (Phase 12 §6d): `from forensics.reporting.narrative import generate_evidence_narrative; generate_evidence_narrative(analysis_result, "jane-doe")` returns a deterministic ~200-400 word factual paragraph suitable for inclusion in the published report. Pass `score=`, `control_count=`, and `preregistration=` (a `VerificationResult` from `verify_preregistration()`) to enrich the output. The function is pure — same inputs always produce byte-identical text — so it is safe to paste verbatim in confirmatory contexts.

### Exit codes and warnings

- Stages return **non-zero** on fatal errors (scrape failure, missing Quarto, analysis `typer.Exit`, report subprocess failure). `forensics all` propagates the first non-zero code.
- `forensics all` returns exit code **`2`** when preflight hard-fails (distinct from `1` used by analyze).
- `insert_analysis_run` at the start of `all` / scrape / extract / analyze is **best-effort**: SQLite permission or I/O errors log **`Could not record analysis_runs row`** and the stage still continues where the code path allows.

## Expected Artifacts

After a successful full run, verify (paths depend on configured authors):

- `data/articles.db` — corpus + `analysis_runs`
- `data/authors_manifest.jsonl` — post–discover manifest
- `data/features/{slug}.parquet` — per-author features
- `data/embeddings/{slug}/batch.npz` — embeddings when not skipped
- `data/analysis/` — per-author `*_result.json`, `run_metadata.json`, and other stage JSON as enabled
- `data/reports/` — Quarto HTML/PDF outputs (not a single `report.md` at repo root)

Phase 9 outputs: `data/probability/{author_slug}.parquet`, `data/probability/model_card.json`  
Phase 10 outputs: `data/ai_baseline/{author_slug}/`, `data/ai_baseline/generation_manifest.json`

Legacy checklists that mention `data/raw/documents.json`, `data/analysis/analysis.json`, or `data/pipeline/summary.json` are **obsolete** for this codebase.

## Ollama Setup (Phase 10)

Required for AI baseline generation. Not needed for Phases 1-9.

```bash
# Install
brew install ollama

# Pull models (~14GB total)
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull gemma2:9b

# Verify
ollama list

# Preflight check from the pipeline
uv run python scripts/generate_baseline.py --preflight
```

Hardware: M1 Mac with 32GB unified memory runs all three 7-9B models comfortably (one at a time, ~5GB each). Ollama keeps the last-used model in memory; expect ~10-15s cold load when switching.

### Running baseline generation

```
uv sync --extra baseline                     # install pydantic-ai + pydantic-evals
uv run python scripts/generate_baseline.py --preflight
uv run python scripts/generate_baseline.py --author <slug> --dry-run
uv run python scripts/generate_baseline.py --author <slug> --articles-per-cell 5
uv run python scripts/generate_baseline.py --all

# Via the analyze CLI:
uv run forensics analyze --ai-baseline --author <slug>
uv run forensics analyze --ai-baseline --skip-generation --author <slug>
uv run forensics analyze --verify-corpus
```

Artifacts land under `data/ai_baseline/{slug}/{model}/{mode}_{temp}/*.json`
plus a top-level `generation_manifest.json` and per-cell `embeddings/`.

### Quality-gate evals

```
uv sync --extra baseline
uv run python evals/baseline_quality.py --model llama3.1:8b
uv run python evals/baseline_quality.py --all-models --output /tmp/reports.json
```

The `PerplexityRangeCheck` evaluator silently passes when the Phase 9 extra
(`probability`) is not installed — install both extras together for the full
gate: `uv sync --extra probability --extra baseline`.

## Model Downloads (Phase 9)

- GPT-2 reference model: ~500MB (auto-downloads on first `--probability` run)
- Falcon-7B pair (Binoculars, optional): ~28GB full / ~8GB quantized
- Embedding model (all-MiniLM-L6-v2): ~80MB (auto-downloads on first embedding run)

Throughput expectations:

- Article-level perplexity only: ~10 articles/min on CPU with GPT-2.
- Sentence-level perplexity (computed alongside) is ~5× slower because each
  sentence triggers its own forward pass; budget ~2 articles/min on CPU for
  a full `compute_perplexity` run. GPU throughput is ~50 articles/min.
- Binoculars (Falcon-7B pair) is GPU-only for practical runs; on CPU plan for
  ~1 article/min.

### Running probability features

```
uv sync --extra probability            # install torch + transformers + accelerate
uv run forensics extract --probability --author <slug>
uv run forensics extract --probability --no-binoculars --device cpu
cat data/probability/model_card.json   # pinned model revisions + digest
```

Artifacts: `data/probability/{author_slug}.parquet` + `data/probability/model_card.json`.

### Running tests with the slow gate

The default `uv run pytest` run skips tests marked `@pytest.mark.slow` (real
GPT-2 load + inference). To run them explicitly:

```
uv run pytest -m slow tests/test_probability.py -v
uv run pytest -m "not slow" tests/ -v       # default behavior
```

## Common Issues

### Command not found: `uv`

- Install uv with the official script:
  - `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Load uv into the current shell:
  - `source "$HOME/.local/bin/env"`
- Verify:
  - `uv --version`

### Command not found: `forensics`

- Confirm dependencies are synced: `uv sync`
- Re-run via `uv run forensics --help`

### Missing output files

- Re-run a focused stage command and inspect terminal output.
- Confirm the process has write access to the repository `data/` directory.

### Failing tests

- Start with focused test runs:
  - `uv run pytest tests/unit -v`
  - `uv run pytest tests/integration -v`
- Run specific test: `uv run pytest -k "test_name" -v`
- Fix regressions before adding new feature behavior.

### Ollama connection refused

- Start the Ollama server: `ollama serve`
- Check it's running: `curl http://localhost:11434/api/tags`
- If port conflict, check for existing process: `lsof -i :11434`

### uv sync fails on torch/transformers

- These are large deps (~2GB for torch). Ensure enough disk space.
- On M1 Mac, torch installs the MPS-compatible version automatically.
- If resolution fails, try: `uv sync --refresh`

### Parquet schema mismatch

- If feature extraction schema changed, delete old Parquet files: `rm data/features/*.parquet`
- Re-run extraction: `uv run forensics extract`
- See GUARDRAILS.md Sign: "Parquet Schema Evolution"

### Embedding model version mismatch

- Embedding model is pinned to `all-MiniLM-L6-v2` (384-dim).
- If embeddings look wrong, verify model: check `config.toml` [features] section.
- See GUARDRAILS.md Sign: "Embedding Model Version Mismatch"

## Quality Checks

```bash
# Full pre-commit validation
uv run ruff format .
uv run ruff check . --fix
uv run pytest tests/ -v

# Coverage report
uv run pytest tests/ -v --cov=src --cov-report=term-missing

# Property-based tests with stats
uv run pytest tests/ -v --hypothesis-show-statistics
```

## Migrations (Phase 15)

Storage-layer migrations now land through the Typer CLI rather than the old
``scripts/`` only path. Two entry points, both idempotent:

```bash
# SQLite: authors.is_shared_byline, schema_version bookkeeping
uv run forensics migrate

# Feature parquets: stamp forensics.schema_version + add section column
uv run forensics features migrate              # in place (writes backup copy)
uv run forensics features migrate --dry-run    # preview only, no writes
```

- ``forensics migrate`` calls ``Repository.apply_migrations()``; the same
  runner also fires on every ``Repository`` context-manager open, so
  operators rarely need to invoke it directly — but it's the canonical
  surface for a ``migrate-then-analyze`` deploy script.
- ``forensics features migrate`` walks ``data/features/*.parquet`` and runs
  the Phase-15 Step-0.3 helper. Backups land under
  ``data/features/_pre_phase15_backup/`` (filename-preserving). Rollback is
  a straight ``mv`` of the backup copy.
- Both commands tolerate missing target dirs (``data/``, ``data/features/``)
  with a friendly stderr message and exit code ``0``.

### Typer subcommand registration pattern (Phase 15 L6)

New CLI subcommands follow this pattern so the dispatch table in
``src/forensics/cli/__init__.py`` stays the single registration surface:

```python
# src/forensics/cli/foo.py
from typing import Annotated
import typer

foo_app = typer.Typer(name="foo", help="One-line description.", no_args_is_help=True)

@foo_app.command(name="bar")
def bar(
    flag: Annotated[bool, typer.Option("--flag", help="...")] = False,
) -> None:
    """Subcommand docstring."""
    # imports inside the function body keep CLI startup fast
    ...

# Simple top-level command (no sub-app):
def my_cmd(
    arg: Annotated[str | None, typer.Option("--arg", help="...")] = None,
) -> None:
    """Docstring — this is what shows in --help."""
    ...
```

And register inside ``src/forensics/cli/__init__.py``:

```python
from forensics.cli.foo import foo_app, my_cmd  # noqa: E402

app.add_typer(foo_app, name="foo")        # nested sub-app
app.command(name="mycmd")(my_cmd)         # top-level command
```

This is what Phase-15 L6 uses for ``forensics features migrate`` (sub-app)
and ``forensics migrate`` (top-level).

## Git workflow (GitButler)

Use GitButler CLI (`but`) for writes (commit, push, branch, merge, stash, rebase-style edits). The full command map and recipes live in the repo-local skill:

- `.claude/skills/gitbutler/SKILL.md` (Claude Code)
- `.cursor/skills/gitbutler/SKILL.md` (Cursor — same mirror)

Notion playbook add-on (parallel agents, `but status --json`, `--json --status-after`): `.claude/skills/gitbutler-workflow/SKILL.md` (mirrored under `.cursor/skills/gitbutler-workflow/`).

Project-specific notes (forge target, PRs) are in `AGENTS.md` under **Learned Workspace Facts** (GitButler bullet).

```bash
# Preflight before you commit (quality bar — run with git or but read-only)
uv run ruff format .
uv run ruff check . --fix
uv run pytest tests/ -v

# Then use but for the actual commit/push (see gitbutler skill — e.g. but status -fv, but commit ... --status-after; optional JSON flow in gitbutler-workflow skill)

# Conventional commit prefixes for messages
# feat: fix: refactor: test: docs: chore:
```

## Incident Handoff

When handing off active work:

- Record the exact command(s) run.
- Capture failing tests or observed error text.
- Add status and next steps in `HANDOFF.md` (required — see CLAUDE.md Session Boundaries).
