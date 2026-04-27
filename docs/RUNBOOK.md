# Runbook

Operational quick reference. Agents: append new sections here whenever you discover debug techniques, resolve recurring errors, add CLI commands, or learn environment facts that future operators need.

## Local Setup

1. Install dependencies: `uv sync`
2. For Phase 10 (baseline generation): `uv sync --extra baseline`
3. Validate environment: `uv run ruff check . && uv run ruff format --check .`
4. Run tests: `uv run pytest tests/ -v`
5. Run with coverage: `uv run pytest tests/ -v --cov-report=term-missing` (coverage target `forensics` is configured in [`pyproject.toml`](../pyproject.toml) `addopts`)
6. Optional Textual TUI: `uv sync --extra tui` enables `tests/test_tui.py` and related progress tests. A plain `uv sync` skips them; coverage config **omits** `forensics/tui/*` from the aggregate denominator so `fail_under=75` still passes without the extra.

### Automated pipeline E2E (`tests/integration/test_pipeline_end_to_end.py`)

- **What it covers:** Seeded `articles.db` (two authors: `fixture-target` + `fixture-control`), `FORENSICS_CONFIG_FILE` pointing at `tests/integration/fixtures/e2e/config.toml`, and `importlib.import_module("forensics.config.settings")` + `monkeypatch` on that module’s `_project_root` so `get_settings().db_path` and artifact paths resolve under a disposable workspace (avoids the `forensics.config.settings` name shadowing the real settings submodule). **Scrape is not run** (DB is populated in-process). Stages: `extract_all_features(..., skip_embeddings=True)` → `run_full_analysis(..., exploratory=True)` → optional Quarto `run_report(ReportArgs(notebook="index.qmd", report_format="html"))` when `quarto` is on `PATH` (copies repo `index.qmd` + `quarto.yml` into the temp root first).
- **Regression gate:** `data/analysis/comparison_report.json` must contain a **non-empty** `targets["fixture-target"]` entry (guards the “no configured target → empty comparison” failure mode). The seeded corpus asserts changepoint / convergence signal vs control (see `tests/integration/fixtures/e2e/corpus_seed.py`).
- **Markers:** `@pytest.mark.integration` only (not `slow`). Default `uv run pytest tests/` still runs this file as part of the unit job; **CI** also runs a dedicated **`integration`** workflow job (`pytest tests/ -m integration -v --no-cov` after `uv run python -m spacy download en_core_web_md`). For a local slice matching CI: `uv run pytest tests/ -m integration -v --no-cov` (always pass `--no-cov` when selecting only integration tests so `fail_under` is not measured on a tiny denominator).

### Running integration tests locally

1. Sync deps: `uv sync` (and extras your branch’s CI uses — the integration job installs spaCy `en_core_web_md`).
2. Install the model CI uses: `uv run python -m spacy download en_core_web_md`.
3. Run the integration-marked suite: `uv run pytest tests/ -m integration -v --no-cov`.
4. Single-file E2E only: `uv run pytest tests/integration/test_pipeline_end_to_end.py -m integration -v --no-cov`.

If you need the default `addopts` out of the way for a one-off: `uv run pytest tests/integration/test_pipeline_end_to_end.py -v --override-ini "addopts=-ra -q --strict-markers" --no-cov`.

## Phase 16 hash-break migration

Phase 16 intentionally changes the analysis-config hash, corpus fingerprint, and embedding revision contract. Treat any pre–Phase-16 `data/analysis/*_result.json` and preregistration locks as **stale** relative to a Phase-16 `config.toml` until you re-lock and re-run (see GUARDRAILS Sign: *Pre-Phase-16 locked artifacts must be re-locked*).

### Pre-registration lock (template → confirmatory)

1. **Write or refresh the lock** from the current `config.toml` thresholds: `uv run forensics lock-preregistration` → updates `data/preregistration/preregistration_lock.json` with `locked_at` (UTC ISO), `analysis` snapshot, and `content_hash`.
2. **Template / exploratory state:** the committed repo default is an unfilled lock (`{"locked_at": null}` only). `verify_preregistration` reports `status="missing"` — confirmatory `analyze` exits non-zero until you run `lock-preregistration` or pass `--exploratory`.
3. **Verify after a run:** read `data/analysis/run_metadata.json` → `preregistration_status` is `ok`, `missing`, or `mismatch`. A **mismatch** means the live settings no longer match the lock; confirmatory analyze **hard-fails** (exit code 1) after writing run metadata under `rid=preregistration-blocked`.

### Embeddings (quarantine + re-extract)

- **Default operator policy:** when `analysis.embedding_model` / `embedding_model_version` / `embedding_model_revision` no longer match the first row of `data/embeddings/manifest.jsonl`, feature extraction **archives** the entire `data/embeddings/` tree to `data/embeddings_archive_<UTC>/` and starts clean (quarantine + re-extract). Re-run `uv run forensics extract` after updating the HF revision pin in `config.toml`.
- **SentenceTransformer revision:** vectors are produced with `SentenceTransformer(model, revision=…)` using `[analysis] embedding_model_revision` (commit SHA or branch). Each manifest row stores `model_revision` next to the legacy `model_version` label.
- **Analyze without re-extracting:** there is no supported path to silently mix revisions in confirmatory mode. For **exploratory** runs only, `forensics analyze --exploratory --allow-pre-phase16-embeddings` loads batches whose manifest revision differs from config, emitting a **WARNING** per article instead of raising. Confirmatory runs (default) always hard-fail on mismatch so drift and downstream statistics cannot blend incompatible embedding spaces.

### Corpus custody (`corpus_custody.json`) — one-cycle v1 / v2

- **`schema_version: 2`:** `corpus_hash` fingerprints the **analyzable** corpus: non-duplicates only, ordered by `content_hash` (stable under insert order).
- **`corpus_hash_v1`:** legacy fingerprint (`ORDER BY id`, all rows) kept for one transition cycle so older verification semantics can be compared; see GUARDRAILS for removal timing (Phase 17).
- **`verify_corpus_hash`:** dispatches on `schema_version` (missing field → treat as v1).

### Quick E2E spot-check (single author, exploratory)

When `data/articles.db` already has rows for a slug (skip live scrape if you prefer): `uv run forensics extract --author <slug>` → `uv run forensics analyze --exploratory --author <slug> [--changepoint …]` → `uv run forensics report` (Quarto on `PATH`). Inspect under `data/analysis/`: `<slug>_result.json` (`config_hash`), `corpus_custody.json` (`schema_version`, `corpus_hash`, `corpus_hash_v1`), `<slug>_hypothesis_tests.json` (Phase 16 fields: `n_pre`, `n_post`, `n_nan_dropped`, `skipped_reason`, `degenerate`), `<slug>_convergence.json` (`n_rankable_per_family` when convergence ran). For HTML-only fetch without discover/metadata/dedup/archive: `uv run forensics scrape --fetch` (same flag set as *FETCH_ONLY* in `dispatch_scrape`).

### Dedup performance cliff above `hamming_threshold = 3`

Near-duplicate detection (`forensics.scraper.dedup`) compares 128-bit simhashes with Hamming distance. The default `scraping.simhash_threshold` is **3** (aligned with the four 32-bit LSH banding guarantee). Raising the threshold widens the “near duplicate” neighborhood: each increment increases pairwise comparisons and union-find work superlinearly on large corpora. If you need a looser dedup, prefer bounded batches or profiling first — do not raise the threshold on full-site runs without measuring wall time and duplicate-review cost.

### Migrating simhash fingerprints after D-01 (NFKC normalization)

Fingerprint values are versioned (`dedup_simhash_version`, current = `v2` in code as `SIMHASH_FINGERPRINT_VERSION`). Rows with a missing version or a version other than `v2` are excluded from the cached fingerprint set until recomputed; running dedup **without** migrating first can admit historical near-duplicates that no longer match stored bands.

- Recompute all stale rows: `uv run forensics dedup recompute-fingerprints` (optional `--db PATH`, `--limit N` for tests).
- stdout is one JSON object: `recomputed`, `skipped`, `errors`.

## Pipeline Operations

- Run full pipeline: `uv run forensics all` — implementation: `src/forensics/pipeline.py` (`run_all_pipeline`). It runs **full scrape** (same as bare `forensics scrape` when no scrape flags are set), then extract, then `run_analyze(timeseries=True, convergence=True)` (**not** changepoint/drift unless you change the pipeline), then Quarto report. See [`docs/ARCHITECTURE.md`](ARCHITECTURE.md#forensics-all-end-to-end).
- Stage-by-stage (recommended when debugging):
  - `uv run forensics scrape` (use `--discover` / `--metadata` / `--fetch` etc. as needed; see `--help`)
  - `uv run forensics extract`
  - `uv run forensics analyze` (add `--changepoint`, `--drift`, … as needed). Each analyze run calls `verify_preregistration(settings)` before stages (see `src/forensics/cli/analyze.py`); threshold drift vs `data/preregistration/preregistration_lock.json` logs at WARNING, and `data/analysis/run_metadata.json` records `preregistration_status` (`ok` / `missing` / `mismatch`). **SQLite in analyze (ADR-009 Option A):** analyze still opens `data/articles.db` via `Repository` for **slug ↔ `author_id`** and roster wiring only; Parquet / `batch.npz` / manifests supply the measured signals. Keep the same `articles.db` that extract used (do not swap or truncate authors between extract and analyze without re-extracting), or joins and manifest filters can silently drop or mis-attribute rows.
  - `uv run forensics report` (requires **Quarto** on `PATH`; output under `data/reports/` per `quarto.yml`)
- Extract probability features (Phase 9): `uv run forensics extract --probability`
- Generate AI baseline (Phase 10): `uv run python scripts/generate_baseline.py --author {slug}`
- Validate environment before a run: `uv run forensics preflight` (pass `--strict` to promote warnings to failures). Hard-fails on Python < 3.13, missing `en_core_web_sm`, disk < 5 GB, config parse errors, or placeholder authors; warns for Quarto/Ollama/sentence-transformers cache misses. Machine-readable preflight: `uv run forensics --output json preflight` prints one JSON envelope on stdout (`sort_keys=True`; keys `ok`, `type`, `schemaVersion`, `data`). The `data` object holds `status` (`ok`/`warn`/`fail`), `strict`, `checks` (each `name`/`status`/`message`), `has_warnings`, and `has_failures`; exit codes match text mode (`1` only when any check is `fail`). Global `--output` must appear **before** the subcommand name. If `uv` ever mis-parses flags, use `uv run -- forensics --output json preflight`.
- Lock pre-registration thresholds: `uv run forensics lock-preregistration` writes `data/preregistration/preregistration_lock.json` (SHA256-hashed canonical JSON). Run **before** first `analyze` to convert the run from exploratory to confirmatory. If a filled lock already exists, the CLI exits **5 (CONFLICT)** unless you pass the global confirm flag **before** the subcommand: `uv run forensics --yes lock-preregistration` (not `lock-preregistration --yes`). Analyze always invokes `verify_preregistration` (same return statuses). See `src/forensics/preregistration.py`.
- Convergence permutation null (Phase 12 §5b): under `[analysis]` in `config.toml`, set `convergence_use_permutation = true` to draw an empirical null for each convergence window (p-values are **logged only**; detected windows are unchanged). Defaults: `convergence_use_permutation = false` (CPU), `convergence_permutation_iterations = 1000`, `convergence_permutation_seed = 42`. Wired from `src/forensics/config/settings.py` into `compute_convergence_scores` in `src/forensics/analysis/orchestrator/` (runner + `comparison.py`) and `src/forensics/analysis/comparison.py`.
- Blind newsroom survey (Phase 12 §1): `uv run forensics survey` runs the full pipeline across every qualified author on the manifest and ranks them by composite AI-adoption signal. Options: `--dry-run` (list qualified authors, no analysis), `--resume <run_id>` (skip authors already in `data/survey/run_<id>/checkpoint.json`), `--skip-scrape` (reuse existing corpus), `--author <slug>` (single-author debug run), `--min-articles` / `--min-span-days` (override `[survey]` thresholds). Output lands under `data/survey/run_<id>/` with `checkpoint.json` (written after each author) and `survey_results.json` (ranked, with the natural control cohort). Thresholds default to `SurveyConfig` in `config.toml` (`min_articles=50`, `min_span_days=730`, `min_words_per_article=200`, `min_articles_per_year=12.0`, `require_recent_activity=true`, `recent_activity_days=180`). Natural controls are authors whose composite score ≤ 0.2 AND `SignalStrength.NONE`; see `src/forensics/survey/scoring.py::identify_natural_controls`.
- **Survey parallelism:** with more than one pending author, `run_survey` may dispatch `ProcessPoolExecutor` workers sized by env `SURVEY_AUTHOR_WORKERS` or default `min(8, os.cpu_count())`. Child processes do **not** inherit parent `pytest` monkeypatches — the survey test stubs set `SURVEY_AUTHOR_WORKERS=1` to force sequential in-process fakes.
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
- **`forensics scrape`** may exit **`4` (TRANSIENT)** when the run recorded at least one `scrape_errors.jsonl` line, **every** logged line is classified `transient: true` (timeouts, exhausted 429/5xx retries, etc.), and there was **no** successful ingest/fetch outcome for the run (see `docs/EXIT_CODES.md`). Each JSONL row now includes a boolean `transient` field for downstream tooling.

## Expected Artifacts

After a successful full run, verify (paths depend on configured authors):

- `data/articles.db` — corpus + `analysis_runs`
- `data/authors_manifest.jsonl` — post–discover manifest
- `data/features/{slug}.parquet` — per-author features
- `data/embeddings/{slug}/batch.npz` — embeddings when not skipped
- `data/analysis/` — per-author `*_result.json`, `run_metadata.json`, and other stage JSON as enabled
  - When present, `run_metadata.json` → `section_residualized_sensitivity.analysis_dir` is a **project-relative** path (e.g. `data/analysis/sensitivity/section_residualized`), not an absolute path — resolve with repo root when opening artifacts.
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
- For a narrow validation run that should not enforce the repository-wide
  coverage threshold, add `--no-cov` (for example,
  `uv run pytest --no-cov tests/unit/test_analyze_compare.py::test_name -q`).
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

## Section diagnostics (Phase 15 J3 / J6 / J7)

URL-derived `section` tags (Phase 15 J1) unlock three diagnostic surfaces on
the `analyze` sub-app. All commands write deterministic JSON / CSV / Markdown
under `data/analysis/`; legacy `forensics analyze --changepoint` etc. still
work unchanged.

```bash
# J3 — newsroom-wide section descriptive report + J5 gate verdict.
# Persists section_centroids.json, section_distance_matrix.{json,csv},
# section_feature_ranking.json, and section_profile_report.md.
uv run forensics analyze section-profile
uv run forensics analyze section-profile --output /tmp/profile.md
uv run forensics analyze section-profile --features-dir path/to/features

# J6 — per-author section-contrast tests (Welch + Mann-Whitney + per-family
# BH; Phase 15 C2 helper). Output: data/analysis/<slug>_section_contrast.json.
uv run forensics analyze section-contrast                    # every author
uv run forensics analyze section-contrast --author jane-doe  # one author

# J7 — residualize-sections per-run override. Flips
# analysis.section_residualize_features for the current process only;
# config.toml is NOT modified. Use this for A/B comparisons against the
# unadjusted CP run without touching the persisted config.
uv run forensics analyze --residualize-sections --changepoint
uv run forensics analyze all --residualize-sections          # via run_analyze()
```

Operational notes:

- `section-contrast` requires authors to have ≥ 2 sections each with ≥ 30
  articles (`MIN_SECTION_ARTICLES`). Authors below the bar emit
  `{"pairs": [], "disposition": "insufficient_section_volume"}` rather than
  raising — downstream consumers must render "N/A".
- A WARNING is emitted when **every** PELT feature passes BH for a single
  pair — wholly different registers across the entire feature set is
  suspicious and warrants a spot-check.
- `--residualize-sections` is a hot-fix knob. Persistent toggling lives in
  `config.toml` under `[analysis] section_residualize_features = true` so
  the change is captured by the config hash + preregistration lock.

## Pre-registration lock workflow (confirmatory vs exploratory)

Every `analyze` run records `preregistration_status` in
`data/analysis/run_metadata.json`. The status comes from
`verify_preregistration(settings)` against
`data/preregistration/preregistration_lock.json` and is one of:

- `ok` — a filled lock file matches the current analysis thresholds. The
  run is **confirmatory**.
- `missing` — no lock file (or the committed template, see below). The
  run is **exploratory** and any p-values are descriptive only.
- `mismatch` — a filled lock file exists but one or more analysis
  thresholds drifted since the lock. Logged at WARNING with a
  per-key diff; the run continues so an operator can inspect.

### Files in this directory

- `data/preregistration/preregistration_lock.json` — the operator-fillable
  lock template lives in the repo so a fresh checkout has a non-mismatching
  exploratory state out of the box. The template carries:
  - `preregistration_id` — opaque identifier for the run plan
  - `locked_at` / `locked_by` — null until the operator fills them
  - `config_hash` — null until the operator fills it
  - `amended_from` / `amendments` — pointers to the narrative docs
    (`amendment_phase15.md` etc.) that justify the locked hypotheses
  - `hypotheses` — H1..Hn list operator must populate before claiming
    a confirmatory result
  - `expected_directions` — per-feature pre-declared direction of effect
- `data/preregistration/amendment_phase15.md` — phase-amendment narrative
  (committed). Reference any new hypothesis here before locking.

### How the analyze CLI reads the file

`verify_preregistration` short-circuits the unfilled template (where
`locked_at is null` AND `analysis` block is absent) to `missing` so the
committed template never trips a false `mismatch`. The first fully-filled
lock — written by `uv run forensics lock-preregistration` — populates the
canonical `analysis` snapshot + SHA256 `content_hash` and converts the
next run from exploratory to confirmatory.

### Locking workflow

```bash
# 1. Edit the template and commit it (preregistration_id + hypotheses +
#    expected_directions are the operator-authored fields). Do NOT fill
#    locked_at / locked_by / config_hash by hand — those are written by
#    the lock-preregistration command in step 2.
$EDITOR data/preregistration/preregistration_lock.json
git add data/preregistration/preregistration_lock.json
git commit -m "Pre-register analysis plan for <author> / <window>"

# 2. Snapshot the current thresholds + content hash. This OVERWRITES the
#    file with the canonical confirmatory lock — keep your template-edit
#    commit so the hypothesis history stays in git.
uv run forensics lock-preregistration

# 3. Run the analysis. ``run_metadata.json::preregistration_status`` lands
#    as ``ok`` and the narrative report renders as confirmatory.
uv run forensics analyze
cat data/analysis/run_metadata.json | jq .preregistration_status   # → "ok"
```

Re-running step 2 after every config change keeps the lock current. If you
change a threshold without re-locking, the next analyze run logs WARNING
+ records `preregistration_status: "mismatch"` — fix it before publishing.

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

### Phase 15 CLI surface (analyze + survey)

New flags and subcommands shipped during Phase 15. All are additive;
prior invocations remain valid. See `docs/ARCHITECTURE.md` for the
behavioural rationale.

```bash
# G1 — author-level parallelism (PR #60). Default 1 = serial.
uv run forensics analyze --max-workers 8

# D — survey shared-byline filter (PR #71). Default excludes group bylines
# (mediaite, mediaite-staff, ...). Pass to include them for transparency.
uv run forensics survey --include-shared-bylines

# J2 — advertorial / syndicated section exclusion (PR #76). Default
# excludes sponsored, partner-content, crosspost, etc. Both stages take
# the same flag so a single override flips the corresponding stage.
uv run forensics survey --include-advertorial
uv run forensics analyze --include-advertorial

# J3 — newsroom-wide section descriptive diagnostic (PR #75). Writes
# data/analysis/section_centroids.json, section_distance_matrix.json
# (+ .csv mirror), section_feature_ranking.json, and
# section_profile_report.md (J5 gate verdict embedded).
uv run forensics analyze section-profile
uv run forensics analyze section-profile --output /tmp/section_profile_test.md

# J6 — per-author section-contrast tests (Wave 3.3). Document forward-
# compatibly; flag may merge in parallel with this runbook entry.
uv run forensics analyze section-contrast
uv run forensics analyze section-contrast --author <slug>

# J5 — optional section residualization before BOCPD (Wave 3.3, gated
# on J3 verdict against real corpus data). Off by default.
uv run forensics analyze all --residualize-sections
```

### Phase 15 debug + parity recipes

```bash
# E1 — Pipeline B per-window component DEBUG logs. Useful when
# investigating drift / centroid-velocity regressions.
FORENSICS_LOG_LEVEL=DEBUG uv run forensics analyze --drift --author <slug>

# H2 — serial vs parallel JSON artifact parity check. Confirms
# author-level parallelism is byte-identical to a serial run. The
# integration test lives at tests/integration/test_parallel_parity.py
# (added by Wave 3.4).
uv run forensics analyze                    # serial baseline
mv data/analysis data/analysis_serial
uv run forensics analyze --max-workers 4    # parallel run
diff -r data/analysis_serial data/analysis  # expected: no output

# Evidence refresh — isolate each author under
# data/analysis/parallel/<run_id>/<slug>/, validate per-author artifacts,
# promote them to data/analysis/, then rebuild comparison metadata once.
# Use this when canonical per-author result hashes are stale and the serial
# refresh loop is too slow.
uv run forensics analyze --parallel-authors --max-workers 3
```

### Phase 15 schema migration + benchmarks

```bash
# Storage migrations (covered above):
uv run forensics migrate                    # SQLite (Phase D1, etc.)
uv run forensics features migrate           # parquet section column
uv run forensics features migrate --dry-run # preview only

# L1 — pre-Phase-15 wall-clock baseline + phase-by-phase benchmark.
uv run python scripts/bench_phase15.py --author mediaite-staff
```

### Phase 1 — synthetic PELT null calibration (M-23)

```bash
# Writes data/provenance/synthetic_null_pelt_calibration.json (Gaussian noise,
# fixed penalty). Re-run after changing AnalysisConfig.pelt_penalty materially.
uv run python scripts/synthetic_null_pelt_calibration.py
```

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

## Analysis orchestrator package layout

`forensics.analysis.orchestrator` is now a package split by concern:

- `orchestrator/timings.py` — `AnalysisTimings`, `_StageTimer`
- `orchestrator/per_author.py` — per-author feature/drift/convergence/test assembly
- `orchestrator/parallel.py` — process workers + isolated refresh flow
- `orchestrator/comparison.py` — target/control resolution + compare-only path
- `orchestrator/sensitivity.py` — section-residualized rerun path
- `orchestrator/staleness.py` — stale detection + run-metadata merge
- `orchestrator/runner.py` — `run_full_analysis` entrypoint

Import surface remains `from forensics.analysis.orchestrator import ...`.

## Phase 0 — preregistration lock, comparison report, AI baseline continuity

**Order of operations (punch-list Phase 0):**

1. **Amendment (M-05):** Append post-hoc threshold documentation to `data/preregistration/amendment_phase15.md` when Fix-F / Fix-G (or similar) apply.
2. **Lock (M-01):** `uv run forensics lock-preregistration` — writes `data/preregistration/preregistration_lock.json` with `locked_at`, `analysis`, and `content_hash`. Confirmatory `forensics analyze` (without `--exploratory`) requires `verify_preregistration` → `ok`.
3. **Comparison (M-03):** With exactly one `role = "target"` in `config.toml` (M-04), run `uv run forensics analyze --compare` to populate `data/analysis/comparison_report.json`. If `validate_analysis_result_config_hashes` fails, refresh per-author `*_result.json` under the current analysis config hash first.
4. **AI baseline metric (M-02):** Intended path: `ollama serve` locally, `uv sync --extra baseline`, then `uv run forensics analyze --ai-baseline --author <slug>` (see `[baseline]` in `config.toml`). Cell prompts append a **JSON delivery contract** so local Llama checkpoints return `{"headline","text","actual_word_count"}`; `forensics.baseline.agent.parse_generated_article_text` unwraps tool-shaped blobs and tolerates plain-text fallbacks. **Stub continuity (local only — `data/ai_baseline/` is gitignored):** `uv run python scripts/seed_phase0_ai_baseline_stubs.py` is only for environments without Ollama. After real generation, re-run `forensics analyze --drift --author <slug>` (add `--exploratory --allow-pre-phase16-embeddings` if article embedding manifests still lag the pinned HF revision).
5. **Embedding revision drift:** If `EmbeddingRevisionGateError` appears during `--drift`, re-extract embeddings for the pinned revision or run drift **exploratory** with `forensics analyze --drift --exploratory --allow-pre-phase16-embeddings` (warnings only; not confirmatory).

## Punch-list C/D/I — operational notes

- **C-06 (analyze vs SQLite):** Options and approval gate are documented in `docs/adr/ADR-009-analyze-stage-sqlite-reads.md`. No default behavior change until a path is chosen.
- **Scrape coverage summary (D-03):** `forensics.scraper.coverage.write_scrape_coverage_summary` can write a JSON summary next to `data/scrape_errors.jsonl` (call from a scrape completion path or a one-off script when you need coverage metrics for reports).
- **Crawl summary (L-04):** After `collect_article_metadata`, the crawler writes `crawl_summary.json` alongside `scrape_errors.jsonl` (per-author error buckets and top messages) via `forensics.scraper.coverage.write_crawl_summary_json`.
- **Run metadata staleness (D-09):** `run_metadata.json` may include `last_scraped_at` (ISO) when scrape artifacts are present; see `forensics.utils.provenance.read_latest_scraped_at_iso`.
- **Parallel analyze promotion (I-06):** After a successful `--parallel-authors` promotion, `data/analysis/parallel/<run>/parallel_promotion_complete.json` records completion metadata for debugging “partial promote” issues.
- **Disk preflight (I-05):** Helpers live in `forensics.utils.disk` (`free_disk_bytes`, `ensure_min_free_disk_bytes`); wire into preflight/CLI where you need a hard stop before large writes.
- **Config fingerprint (I-01):** Scraper-affecting fields and analysis seeds (LDA/UMAP/bootstrap, etc.) participate in `compute_model_config_hash` / `scraper_signal_digest`; re-lock preregistration if you change those and run confirmatory analysis.
