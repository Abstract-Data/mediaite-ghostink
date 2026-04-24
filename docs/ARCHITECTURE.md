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

## Phase 15 Analysis-Stage Updates

Phase 15 (April 2026) restructured several analysis-stage internals while
preserving stage boundaries and the on-disk artifact layout. The summary
below tracks the post-Phase-15 contract; see
`prompts/phase15-optimizations/v0.4.0.md` for the full rationale and PR
list.

### MAP-reset BOCPD (Phase A, PR #70)

The Adams & MacKay BOCPD detector previously thresholded the run-length
posterior `P(r_t = 0 | x_{1:t})`. Run-8 sensitivity review (April 2026)
proved this quantity is algebraically pinned to the constant hazard rate
`h`: under the canonical update, `log_pi_new[0] = log h + log evidence`,
the continuation mass equals `(1 − h) × evidence`, and normalization
divides by `evidence` — so `P(r=0) ≡ h` for every feature at every
timestep regardless of σ², prior, or threshold.

Phase A replaced the threshold rule with a **MAP run-length reset**:
the detector emits a change-point when the posterior MAP run-length
drops below a configurable fraction of its previous value. Two settings
control the rule:

- `bocpd_map_drop_ratio` (default `0.5`) — fraction of previous MAP
  run-length that triggers a reset.
- `bocpd_min_run_length` — minimum run-length floor before a reset is
  considered.

`bocpd_threshold` was removed from settings. `bocpd_detection_mode`
(`"map_reset"` default) participates in the config hash; see also the
GUARDRAILS Sign **"BOCPD `P(r=0)` Posterior Is Pinned to the Hazard
Rate"**.

### Feature-Family Registry & Per-Family FDR (Phases B + C, PRs #64, #66)

The convergence detector previously required ≥ 60 % of all features to
shift simultaneously inside a 90-day window. With ~ 50 features
dominated by lexical-fingerprint variants, that threshold rarely fired
because related features collapse into a single statistical signal.

Phase B introduced a **`FEATURE_FAMILIES` registry** in
`src/forensics/analysis/families.py` that groups features into four
analytic families: lexical, structural, content, productivity (mirroring
the documented Feature Families). The convergence rule now operates on
**families**, not raw feature counts: a window converges when a
configurable fraction of *families* show simultaneous shifts. The
default per-family threshold dropped from 0.60 → 0.50 (Phase B3).

`ConvergenceWindow` (and the persisted `*_convergence.json`) gained a
`families_converging: list[str]` field listing the families that
contributed to the window — this is what the narrative report cites.

Phase C swapped the global Benjamini-Hochberg correction for
**per-family BH** by default (`fdr_grouping = "family"`). Each family's
test bundle is corrected independently so a single noisy family can no
longer suppress signal in others. Legacy global behavior is recoverable
via `fdr_grouping = "author"`. KS was also dropped from the default
hypothesis-test battery (Step C1) to reduce redundancy with Welch's t
and Mann-Whitney U.

### Shared-Byline Filter (Phase D, PR #71)

Authors whose byline is a newsroom group account (`mediaite`,
`mediaite-staff`, etc.) pollute the stylometric baseline because their
articles are written by many human authors. Phase D added an
`is_shared_byline` boolean to the `Author` model and to the
`authors` SQLite table (migration `Repository.apply_migrations()`),
populated at ingest from a curated list of group-byline patterns.

The survey qualification path now excludes shared bylines by default.
Operators can include them for transparency / debugging via
`forensics survey --include-shared-bylines`.

### Section-Tag Enrichment & Section-Conditioned Analysis (Phase J, PRs #73, #75 …)

WordPress `articles.metadata` carries section/tag fields for only ~ 0.01 %
of rows because `scraping.bulk_fetch_mode = true` skips the per-article
metadata pass. Phase J1 added a **`section` column at feature-extraction
time** derived from the URL first-path-segment via
`forensics.utils.url.section_from_url` (100 % coverage). The Phase-15
parquet schema migration is `forensics features migrate`; legacy
parquets without the column also fall back through `section_from_url`
on-read.

Phase J2 added an **advertorial / syndicated exclusion list**
(`excluded_sections`) shared by `SurveyConfig` and `FeaturesConfig`
(default: `sponsored`, `partner-content`, `crosspost`, …). Articles in
those sections drop out of stylometric baselines unless an operator
passes `--include-advertorial` on `forensics survey` or
`forensics analyze`. Excluded rows are dumped to
`data/survey/excluded_articles.csv` for editorial review.

Phase J3 added **`forensics analyze section-profile`** — a newsroom-wide
descriptive diagnostic: per-section centroids, an inter-section cosine
distance matrix, and a per-feature Kruskal–Wallis omnibus ranking. Output
artifacts under `data/analysis/`: `section_centroids.json`,
`section_distance_matrix.json` (+ `.csv` mirror),
`section_feature_ranking.json`, `section_profile_report.md` (with
the J5 gate verdict embedded: `PASS` / `BORDERLINE` / `FAIL` /
`DEGENERATE`).

Phase J4 added per-author **section-mix time series** at
`data/analysis/<slug>_section_mix.json` (consumed by the K2 reporting
chart). Phase J6 added **`forensics analyze section-contrast
[--author <slug>]`** — per-author, per-feature MWU contrasts across
sections.

Phase J5 (optional **section residualization** before BOCPD) is **gated
on the J3 verdict against real corpus data** and ships behind
`--residualize-sections` on `forensics analyze all`. The Wave 4 toggle
decision waits on the J3 PASS/BORDERLINE/FAIL verdict from a populated
features tree (smoke runs return `DEGENERATE` because the worktree has
no `data/features/*.parquet`).

### PELT Cost-Model Knob (Phase F0, PR #69)

Profiling on April 24 2026 (preserved at
`data/analysis/provenance/apr24_rbf_profile.txt`) showed
`ruptures.costs.costrbf.error` accounted for 99.2 % of analysis
wall-clock across 3.2 M calls. Phase F0 swapped the PELT cost model from
RBF to L2 by default. The model is now a settings knob:

- `pelt_cost_model: Literal["l2", "l1", "rbf"] = "l2"`

L2 is mathematically equivalent for mean-shift detection on the
features in scope and delivers ≥ 50 × speedup on the PELT phase. RBF
remains selectable for sensitivity sweeps.

### Parallelism Topology (Phase G)

Phase 15 ships two layers of parallelism for `forensics analyze`:

- **G1 — author-level (default, landed via PR #60).** `run_full_analysis`
  fans out across authors via `ProcessPoolExecutor`. Surface knob:
  `analysis.max_workers` (CLI: `--max-workers`). Parity is verified by
  `tests/integration/test_parallel_parity.py`.
- **G2 — feature-level (opt-in, PR #67 / `feature_workers`).** Within
  `analyze_author_feature_changepoints`, per-feature change-point
  computation can fan out across an inner pool. Each feature is an
  independent 1D signal. Surface knob:
  `analysis.feature_workers` (default `1`, opt-in). G2 is opportunistic
  — recommended only when a single author has unusually many features
  AND the per-author wall-clock is the bottleneck.
- **G3 — embedding I/O audit.** Pipeline B reads embedding batches in
  bulk; verified non-regressive in Phase 15.

Both layers honor the same `config_hash` so parallel and serial runs
produce byte-identical artifacts (see Phase H2 parity test).

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
