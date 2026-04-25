# Architecture

## Purpose

`mediaite-ghostink` is a hybrid forensic analysis pipeline that investigates AI writing tool adoption at Mediaite.com by cross-validating two independent analysis approaches:

- **Pipeline A — Statistical Stylometry:** Change-point detection on lexical, structural, content, and productivity feature timelines
- **Pipeline B — Embedding Drift Analysis:** Semantic vector drift tracking using sentence-transformer embeddings

The implementation follows a deterministic four-stage pipeline: `scrape → extract → analyze → report`.

## Runtime Flow

The `forensics` console script (`forensics = "forensics.cli:main"` in `pyproject.toml`) loads the Typer application in `src/forensics/cli/__init__.py`. Commands:

- `forensics scrape` — Typer sub-app: WordPress discovery, metadata, HTML fetch, dedup, archive/export (see `forensics.cli.scrape`).
- `forensics extract` — feature + embedding extraction from SQLite (`forensics.cli.extract`).
- `forensics analyze` — analysis modes behind flags; default when **no** flags are passed is **time-series + full convergence / hypothesis path** (`forensics.cli.analyze.run_analyze`).
- `forensics report` — Quarto render (`forensics.reporting.run_report`).
- `forensics all` — synchronous orchestration in `forensics.pipeline.run_all_pipeline` (see below).

Configuration is **`ForensicsSettings`** from `forensics.config.settings` (TOML + `FORENSICS_*` env). There is no separate `PipelineConfig` type; the “pipeline config” is that settings object plus implicit paths under `get_project_root()/data/`.

### `forensics all` (end-to-end)

`run_all_pipeline` in `src/forensics/pipeline.py` wires the default automation path:

| Step | Code | Notes |
|------|------|--------|
| 1 | `insert_analysis_run` | Writes an `analysis_runs` row with description `forensics all` (non-fatal on `OSError`). |
| 2 | `dispatch_scrape(discover=False, …, archive=False)` | All stage flags false selects the **full scrape** branch (same as bare `forensics scrape`), which again records `forensics scrape` in `analysis_runs` inside `dispatch_scrape`. |
| 3 | `extract_all_features` | All authors; embeddings unless skipped elsewhere. |
| 4 | `run_analyze(timeseries=True, convergence=True)` | **Does not** enable `--changepoint`, `--drift`, `--compare`, or `--ai-baseline`; change `pipeline.py` if `all` should match a richer CLI default. |
| 5 | `run_report` | Uses `settings.report.output_format`; requires Quarto on `PATH` and per-author artifacts under `data/analysis/`. |

## Stage map (implemented entrypoints)

Illustrative mapping from “stage” to production modules (names are for navigation, not a single façade class):

- **Scrape** — `forensics.cli.scrape.dispatch_scrape` → `crawler.discover_authors` / `collect_article_metadata` / `fetcher.fetch_articles`, `dedup.deduplicate_articles`, `export.export_articles_jsonl`, persistence via `storage.repository.Repository`.
- **Extract** — `forensics.cli.extract` / `features.pipeline.extract_all_features` → Parquet under `data/features/`, embeddings under `data/embeddings/` as implemented by the feature pipeline.
- **Analyze** — `forensics.cli.analyze.run_analyze` → `analysis.timeseries`, `analysis.changepoint`, `analysis.drift`, `analysis.orchestrator`, etc., depending on CLI flags; writes JSON artifacts under `data/analysis/`.
- **Report** — `forensics.reporting.run_report` → subprocess to `quarto render`, output under `data/reports/` per `quarto.yml`.

## Data Models

Core models in `src/forensics/models/`:

- `AuthorManifest` — discovered author registry
- `Author` — author metadata (id, name, slug, article count)
- `Article` — article content and metadata (url, author_id, publish_date, text, word_count)
- `FeatureVector` — per-article feature measurements (lexical, structural, content, productivity)
- `EmbeddingRecord` — sentence-transformer embedding (384-dim float vector per article)
- `ChangePoint` — detected change-point with method, confidence, affected features
- `ConvergenceWindow` — time window where 60%+ features show simultaneous shifts
- `DriftScores` — embedding drift metrics (centroid velocity, cosine decay, intra-period variance)
- `HypothesisTest` — statistical test result (test name, statistic, p-value, effect size)
- `AnalysisResult` — final per-author result combining Pipeline A + B scores

## Storage Architecture

```
WordPress REST API
    ↓
SQLite (write store) ← articles, authors, scrape metadata
    ↓
Parquet (feature store) ← feature vectors via Polars
    ↓
DuckDB (analytical queries) ← spans SQLite + Parquet for cross-store analysis
    ↓
JSONL (transparency export) ← human-readable audit trail
    ↓
Markdown/Notebooks (reports) ← Plotly charts + Quarto rendering
```

## Data and file outputs

Canonical layout (see also [`README.md`](../README.md) **Data layout**):

- `data/articles.db` — SQLite corpus, authors, `analysis_runs`, article bodies and scrape metadata.
- `data/authors_manifest.jsonl` — discovery output from scrape.
- `data/articles.jsonl` — optional export mirror after fetch/dedup paths.
- `data/raw/` — optional raw HTML / year archives when scrape `--archive` is used.
- `data/features/{author_slug}.parquet` — per-author feature tables (not a single monolithic `features.parquet`).
- `data/embeddings/{author_slug}/batch.npz` — embedding batches (see `features.pipeline` docstring).
- `data/analysis/` — per-author JSON (`*_result.json`, `*_changepoints.json`, `*_hypothesis_tests.json`, …), `run_metadata.json`, `corpus_custody.json` when written.
- `data/reports/` — Quarto book output directory (`quarto.yml` `project.output-dir`).

Older docs sometimes referenced `data/raw/documents.json`, `data/analysis/analysis.json`, or `data/pipeline/summary.json`; those paths are **not** the current contract—prefer the list above and the storage modules under `src/forensics/storage/`.

### Analysis Hash Contracts

The pipeline intentionally records two different hashes:

- `data/analysis/run_metadata.json` `config_hash` is the broad raw pipeline settings hash used for audit metadata.
- Each `data/analysis/{author_slug}_result.json` `config_hash` is the analysis-settings compatibility hash from `compute_model_config_hash(settings.analysis, length=16, round_trip=True)`.

Report rendering and compare-only analysis require every configured author result they consume to match the current analysis-settings hash. Mixed or stale per-author result hashes must be recomputed with `uv run forensics analyze` instead of merged into a single evidence chain.

## Key Modules

- `src/forensics/config/` — runtime configuration (pydantic-settings, config.toml + FORENSICS_ env prefix)
- `src/forensics/models/` — all data models (Pydantic v2)
- `src/forensics/scraper/` — WordPress REST API author discovery + HTML fetch (httpx + BeautifulSoup)
- `src/forensics/features/` — feature extraction (lexical, structural, content, productivity, embeddings)
- `src/forensics/analysis/` — change-point detection (PELT, BOCPD, Chow, CUSUM), embedding drift, convergence
- `src/forensics/storage/` — SQLite repository + Parquet persistence + DuckDB analytical queries
- `src/forensics/pipeline.py` — orchestration layer
- `src/forensics/cli/` — command-line interface (Typer)

## Feature Families

1. **Lexical Fingerprint:** TTR, MATTR, hapax legomena, Yule's K, Simpson's D, AI markers, function word distribution
2. **Sentence & Structure:** sentence length stats, clause depth, passive voice ratio, punctuation profile
3. **Content & Repetitiveness:** n-gram entropy, self-similarity (TF-IDF), topic diversity (LDA), formulaic scoring, hedging markers
4. **Productivity Signals:** publication gaps, rolling article counts, burst detection

## Analysis Methods

### Pipeline A — Change-Point Detection
- PELT (ruptures, rbf model, penalty=3.0)
- BOCPD (Adams & MacKay 2007, custom scipy implementation)
- Chow test (F-statistic + p-value)
- CUSUM test
- Kleinberg burst detection
- Cross-feature convergence (60%+ features in 90-day window)

### Pipeline B — Embedding Drift
- Monthly centroid tracking (mean embedding per month)
- Centroid velocity (cosine distance between consecutive months)
- Cosine similarity decay curve (vs first 20 articles baseline)
- Intra-period variance
- AI baseline comparison (GPT-4o generated articles)
- UMAP 2D projection

### Convergence & Statistics
- Welch's t-test, Mann-Whitney U, Kolmogorov-Smirnov
- Cohen's d effect sizes
- Bootstrapped 95% confidence intervals (1000 resamples)
- Benjamini-Hochberg multiple comparison correction

Convergence windows pass by either ratio or A/B agreement. The ratio path
requires the configured fraction of feature families to shift within the
window. The AB-pass path is deliberately narrower: Pipeline A score must be
greater than 0.5 and Pipeline B score must be greater than 0.5, which lets a
strong stylometric signal plus independent embedding-drift signal pass even
when the feature-family ratio alone is below threshold. The constants are
named in `forensics.analysis.convergence` and keep the rule auditable.

Section-residualized sensitivity runs are written separately under
`data/analysis/sensitivity/section_residualized/`. They use URL-derived section
tags, not sparse article metadata, and never overwrite the primary
pre-registered artifacts. If section residualization materially reduces
change-point counts, downstream reporting should treat that author’s evidence
as more section-sensitive.

### Confirmatory Methodology Gates

Confirmatory `forensics analyze` runs require a matching lock at
`data/preregistration/preregistration_lock.json`. Missing or mismatched locks
hard-fail unless the operator passes `--exploratory`, which is recorded in
`data/analysis/run_metadata.json`.

The locked minimal test battery is fixed at a Nov. 1, 2022 split across six
features: `ai_marker_frequency`, `ttr`, `mattr`, `sent_length_mean`,
`paragraph_length_variance`, and `hedging_frequency`. Confirmatory tests use
Welch's t-test and Mann-Whitney U per feature, with multiple-comparison
correction applied globally across all authors in the run. Change-points that
feed evidence outputs must satisfy confidence >= 0.9 and
`abs(effect_size_cohens_d) >= analysis.effect_size_threshold` (default 0.2).

## Design Pattern Guidance for Phases 4–7

The implemented codebase (Phases 1–3) follows a deliberate pattern: Pydantic models for data contracts, classes for stateful services (`Repository`, `RateLimiter`), and pure functions for everything else. Phases 4–7 should preserve this balance but will likely need more classes due to the nature of the work.

**Feature extraction (Phase 4):** Individual feature functions (e.g., `compute_ttr(text) -> float`) should remain pure functions. However, consider a `FeatureExtractor` class if the extraction pipeline needs to hold configuration state (model references, tokenizer caches, feature toggles) across a batch of articles. The sentence-transformers embedding model in particular should be loaded once and held in an instance — not reloaded per article.

**Analysis (Phases 5–6):** Change-point detection and drift analysis are strong candidates for stateful classes. A `ChangePointDetector` could encapsulate the algorithm backend (PELT, BOCPD, Chow, CUSUM) via a strategy pattern, hold configuration (penalty, min_size), and expose a consistent `detect(timeseries) -> list[ChangePoint]` interface. Similarly, a `DriftAnalyzer` could hold the baseline embedding centroid and compute drift metrics incrementally. These classes make it easy to swap algorithms and test each one in isolation.

**Reporting (Phase 7):** A `ReportBuilder` class that accumulates sections and renders to markdown/notebook would be cleaner than passing a growing dict of results through a chain of functions.

**Rule of thumb:** If a module needs to load an expensive resource (ML model, baseline data), maintain state across calls (running statistics, centroids), or support multiple interchangeable backends (detection algorithms), use a class. If it's a pure transformation with no state, keep it as a function.

## Phase 15 Parallelism Topology

Per-author parallelism for `run_full_analysis` landed as PR #60
(merge commit `57fd6c0` on `2026-04-23`). The parity test promised by the
plan lives at `tests/integration/test_parallel_parity.py` and is covered in
Phase-15 unit H2 (pending). All downstream Phase-15 work assumes this
topology as the baseline and uses `analysis.max_workers` / `feature_workers`
for coarse and fine-grained knobs respectively.

```
G1 (per-author ProcessPoolExecutor) merged to `main` at 57fd6c0 on 2026-04-23.
Verified against tests/integration/test_parallel_parity.py (pending H2).
```

## Phase 15 Pre-Rollout Performance Baseline

The Apr 24 2026 profile that drove Phase 15 F0 (PELT RBF → L2 swap) is
preserved at `data/analysis/provenance/apr24_rbf_profile.txt`. Headline:
`ruptures.costs.costrbf.error` accounted for 99.2 % of analysis wall-clock
across 3.2M calls. See `docs/settings_phase15.md` for the full settings
audit and `prompts/phase15-optimizations/current.md` §F0 for the rationale.

## Architectural Constraints

- Use `uv run` for Python execution.
- Preserve stage boundaries and data model contracts.
- Keep writes contained under `data/` unless requirements explicitly expand storage targets.
- Prefer additive, low-risk changes over broad rewrites.
- Use deterministic, testable modules over notebook-only logic.
