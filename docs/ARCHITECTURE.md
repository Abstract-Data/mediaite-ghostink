# Architecture

## Purpose

`mediaite-ghostink` is a hybrid forensic analysis pipeline that investigates AI writing tool adoption at Mediaite.com by cross-validating two independent analysis approaches:

- **Pipeline A — Statistical Stylometry:** Change-point detection on lexical, structural, content, and productivity feature timelines
- **Pipeline B — Embedding Drift Analysis:** Semantic vector drift tracking using sentence-transformer embeddings

The implementation follows a deterministic four-stage pipeline: `scrape → extract → analyze → report`.

## Runtime Flow

`forensics.cli:main` exposes five commands:

- `uv run forensics scrape` — discover authors and fetch articles
- `uv run forensics extract` — compute feature vectors and embeddings
- `uv run forensics analyze` — run change-point detection, drift analysis, convergence scoring
- `uv run forensics report` — generate markdown/notebook reports
- `uv run forensics all` — run full pipeline end-to-end

Each command builds a `PipelineConfig` (via pydantic-settings with config.toml + FORENSICS_ env prefix) and calls stage functions in `forensics.pipeline`.

## Stage Contracts

- `scraper.scrape(seed_urls)` → `list[Article]` — WordPress REST API discovery + HTML fetch
- `features.extract_features(articles)` → `list[FeatureVector]` — four feature families + embeddings
- `analysis.analyze(feature_vectors, embeddings)` → `list[AnalysisResult]` — change-points + drift + convergence
- `pipeline.run_report(config)` → `Path` — generated markdown report with Plotly visualizations

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

## Data and File Outputs

- `data/raw/documents.json` — scraped article content
- `data/features/features.parquet` — extracted feature vectors (Polars)
- `data/analysis/analysis.json` — analysis results
- `data/reports/report.md` — generated markdown report
- `data/pipeline/summary.json` — pipeline run metadata
- `data/scrape_errors.jsonl` — scraping error log

## Key Modules

- `src/forensics/config/` — runtime configuration (pydantic-settings, config.toml + FORENSICS_ env prefix)
- `src/forensics/models/` — all data models (Pydantic v2)
- `src/forensics/scraper/` — WordPress REST API author discovery + HTML fetch (httpx + BeautifulSoup)
- `src/forensics/features/` — feature extraction (lexical, structural, content, productivity, embeddings)
- `src/forensics/analysis/` — change-point detection (PELT, BOCPD, Chow, CUSUM), embedding drift, convergence
- `src/forensics/storage/` — SQLite repository + Parquet persistence + DuckDB analytical queries
- `src/forensics/pipeline.py` — orchestration layer
- `src/forensics/cli.py` — command-line interface (argparse)

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

## Architectural Constraints

- Use `uv run` for Python execution.
- Preserve stage boundaries and data model contracts.
- Keep writes contained under `data/` unless requirements explicitly expand storage targets.
- Prefer additive, low-risk changes over broad rewrites.
- Use deterministic, testable modules over notebook-only logic.
