# Phase 1: Project Scaffolding, Pydantic Models & Configuration

Version: 0.1.0
Status: pending
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: nothing (first phase)

## Objective

Create the full project directory structure, all Pydantic models, the configuration system, the storage layer, utility modules, the CLI skeleton, and update `pyproject.toml` with missing dependencies. After this phase, `uv run forensics --help` must work and all models must be importable.

## Pre-flight

```bash
uv sync
uv run ruff check .
uv run pytest tests/ -v
```

Confirm the project builds cleanly before making changes. If `src/forensics/` doesn't exist yet, create it.

## 1. Update pyproject.toml Dependencies

The current `pyproject.toml` is missing several dependencies required by the spec. Add these to `[project.dependencies]`:

```
spacy>=3.7.0
scikit-learn>=1.5.0
sentence-transformers>=3.0.0
ruptures>=1.1.9
scipy>=1.14.0
numpy>=1.26.0
plotly>=5.22.0
umap-learn>=0.5.6
textstat>=0.7.4
```

Do NOT remove any existing dependencies. Run `uv sync` after editing.

## 2. Create Directory Structure

Create every directory and `__init__.py` file for the following layout under `src/forensics/`:

```
src/forensics/
    __init__.py
    cli.py
    pipeline.py
    config/
        __init__.py
        settings.py
    models/
        __init__.py
        author.py
        article.py
        features.py
        analysis.py
        report.py
    scraper/
        __init__.py
        crawler.py
        fetcher.py
        parser.py
        dedup.py
    features/
        __init__.py
        lexical.py
        structural.py
        content.py
        productivity.py
        readability.py
        embeddings.py
        pipeline.py
    analysis/
        __init__.py
        changepoint.py
        timeseries.py
        drift.py
        convergence.py
        comparison.py
        statistics.py
    storage/
        __init__.py
        repository.py
        parquet.py
        duckdb_queries.py
        export.py
    utils/
        __init__.py
        text.py
        hashing.py
```

Also create `data/` subdirectories if they don't exist:

```
data/
    raw/
    features/
    embeddings/
    ai_baseline/
    reports/
```

And the `tests/` directory:

```
tests/
    __init__.py
    test_scraper.py
    test_features.py
    test_analysis.py
    test_storage.py
    conftest.py
```

Stub every `.py` file (module docstring + pass) EXCEPT the ones detailed below, which get full implementations.

## 3. Configuration System (src/forensics/config/settings.py)

Implement using `pydantic-settings`. Load from `config.toml` at project root with `FORENSICS_` env var prefix overrides.

### Models to implement:

**AuthorConfig**
- `name`: str
- `slug`: str
- `outlet`: str (default "mediaite.com")
- `role`: Literal["target", "control"]
- `archive_url`: str
- `baseline_start`: date
- `baseline_end`: date

**ScrapingConfig**
- `rate_limit_seconds`: float = 2.0
- `rate_limit_jitter`: float = 0.5
- `respect_robots_txt`: bool = True
- `user_agent`: str = "AI-Writing-Forensics/1.0 (research)"
- `max_concurrent`: int = 3
- `max_retries`: int = 3
- `retry_backoff_seconds`: float = 5.0

**AnalysisConfig**
- `rolling_windows`: list[int] = [30, 90]
- `significance_threshold`: float = 0.05
- `multiple_comparison_method`: Literal["bonferroni", "benjamini_hochberg"] = "benjamini_hochberg"
- `bootstrap_iterations`: int = 1000
- `min_articles_for_period`: int = 5
- `embedding_model`: str = "sentence-transformers/all-MiniLM-L6-v2"
- `embedding_model_version`: str = "v2.0"
- `changepoint_methods`: list[str] = ["pelt", "bocpd"]

**ReportConfig**
- `title`: str = "Writing Forensics Analysis"
- `output_format`: Literal["html", "pdf", "both"] = "both"
- `include_sections`: list[str] = [] (empty = all)
- `chart_theme`: str = "plotly_white"
- `cloudflare_deploy`: bool = False

**ForensicsSettings** (top-level, composes the above)
- `authors`: list[AuthorConfig]
- `scraping`: ScrapingConfig
- `analysis`: AnalysisConfig
- `report`: ReportConfig

Provide a `get_settings()` factory that reads `config.toml` from the project root (use `tomllib` from stdlib). Cache with `@lru_cache`.

## 4. Pydantic Models (src/forensics/models/)

### author.py

**AuthorManifest** (from REST API discovery, stored in `data/authors_manifest.jsonl`)
- `wp_id`: int
- `name`: str
- `slug`: str
- `total_posts`: int
- `discovered_at`: datetime

**Author** (configured for analysis)
- `id`: str (UUID, use `default_factory=lambda: str(uuid4())`)
- `name`: str
- `slug`: str
- `outlet`: str
- `role`: Literal["target", "control"]
- `baseline_start`: date
- `baseline_end`: date
- `archive_url`: str

### article.py

**Article**
- `id`: str (UUID)
- `author_id`: str (FK)
- `url`: HttpUrl
- `title`: str
- `published_date`: datetime
- `raw_html_path`: str = "" (relative path to compressed archive)
- `clean_text`: str = ""
- `word_count`: int = 0
- `metadata`: dict = {}
- `content_hash`: str = ""

### features.py

**FeatureVector**
- `id`: str (UUID)
- `article_id`: str (FK)
- `author_id`: str (FK)
- `timestamp`: datetime
- Lexical: `ttr`, `mattr`, `hapax_ratio`, `yules_k`, `simpsons_d`: float; `ai_marker_frequency`: float; `function_word_distribution`: dict[str, float]
- Structural: `sent_length_mean`, `sent_length_median`, `sent_length_std`, `sent_length_skewness`, `subordinate_clause_depth`, `conjunction_freq`, `passive_voice_ratio`, `sentences_per_paragraph`, `paragraph_length_variance`: float; `punctuation_profile`: dict[str, float]
- Readability: `flesch_kincaid`, `coleman_liau`, `gunning_fog`, `smog`: float
- Content: `bigram_entropy`, `trigram_entropy`, `self_similarity_30d`, `self_similarity_90d`, `topic_diversity_score`, `formula_opening_score`, `formula_closing_score`, `first_person_ratio`, `hedging_frequency`: float
- Productivity: `days_since_last_article`: float; `rolling_7d_count`, `rolling_30d_count`: int

All float fields should default to `0.0` and all dict fields to `{}`.

**EmbeddingRecord**
- `article_id`: str (FK)
- `author_id`: str (FK)
- `timestamp`: datetime
- `model_name`: str
- `embedding_path`: str
- `embedding_dim`: int

### analysis.py

**ChangePoint**
- `feature_name`: str
- `author_id`: str
- `timestamp`: datetime
- `confidence`: float (ge=0, le=1)
- `method`: Literal["pelt", "bocpd", "chow", "cusum"]
- `effect_size_cohens_d`: float
- `direction`: Literal["increase", "decrease"]

**ConvergenceWindow**
- `start_date`: date
- `end_date`: date
- `features_converging`: list[str]
- `convergence_ratio`: float
- `pipeline_a_score`: float
- `pipeline_b_score`: float

**DriftScores**
- `author_id`: str
- `baseline_centroid_similarity`: float
- `ai_baseline_similarity`: float
- `monthly_centroid_velocities`: list[float]
- `intra_period_variance_trend`: list[float]

**HypothesisTest**
- `test_name`: str
- `feature_name`: str
- `author_id`: str
- `raw_p_value`: float
- `corrected_p_value`: float
- `effect_size_cohens_d`: float
- `confidence_interval_95`: tuple[float, float]
- `significant`: bool

**AnalysisResult**
- `author_id`: str
- `run_id`: str (UUID)
- `run_timestamp`: datetime
- `config_hash`: str
- `change_points`: list[ChangePoint]
- `convergence_windows`: list[ConvergenceWindow]
- `drift_scores`: DriftScores | None = None
- `hypothesis_tests`: list[HypothesisTest]

### report.py

Stub this with a `ReportManifest` model:
- `run_id`: str
- `title`: str
- `generated_at`: datetime
- `sections`: list[str]
- `output_paths`: dict[str, str]

## 5. Storage Layer (src/forensics/storage/)

### repository.py

Thin repository over `sqlite3` stdlib for `articles.db`. Implement:

- `init_db(db_path: Path) -> None` — creates tables using this schema:

```sql
CREATE TABLE IF NOT EXISTS authors (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    outlet TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('target', 'control')),
    baseline_start DATE,
    baseline_end DATE,
    archive_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    author_id TEXT NOT NULL REFERENCES authors(id),
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    published_date DATETIME NOT NULL,
    raw_html_path TEXT,
    clean_text TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    metadata JSON,
    content_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_author_date ON articles(author_id, published_date);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    config_hash TEXT NOT NULL,
    description TEXT
);
```

- `upsert_author(db_path, author: Author) -> None`
- `upsert_article(db_path, article: Article) -> None`
- `get_articles_by_author(db_path, author_id: str) -> list[Article]`
- `get_all_articles(db_path) -> list[Article]`
- `get_unfetched_urls(db_path) -> list[tuple[str, str]]` (returns article_id, url where clean_text is empty)

### export.py

- `export_articles_jsonl(db_path: Path, output_path: Path) -> int` — writes all articles to JSONL, returns count
- `append_jsonl(path: Path, record: dict) -> None` — append a single JSON line

### parquet.py and duckdb_queries.py

Stub these with module docstrings and `pass`. They'll be implemented in Phase 4 (features) and Phase 5 (analysis).

## 6. Utility Modules (src/forensics/utils/)

### text.py

- `clean_text(raw: str) -> str` — normalize whitespace, strip HTML entities, normalize unicode
- `normalize_whitespace(text: str) -> str`
- `word_count(text: str) -> int`

### hashing.py

- `content_hash(text: str) -> str` — SHA-256 hex digest of normalized text
- `simhash(text: str, hashbits: int = 128) -> int` — basic simhash for near-duplicate detection

## 7. CLI Skeleton (src/forensics/cli.py)

Use `argparse` (no external deps). Implement:

```python
def main():
    parser = argparse.ArgumentParser(prog="forensics", description="AI Writing Forensics Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("scrape", help="Crawl and fetch articles for configured authors")
    subparsers.add_parser("extract", help="Run feature extraction pipeline")
    subparsers.add_parser("analyze", help="Run analysis (change-point, drift, comparison)")
    subparsers.add_parser("report", help="Generate notebook outputs")
    subparsers.add_parser("all", help="Full pipeline end-to-end")

    args = parser.parse_args()
    # Each command prints "Phase not yet implemented" for now
```

## 8. Create config.toml Template

Create `config.toml` at project root with the default values from Section 12 of the spec, using placeholder author entries.

## 9. Tests (tests/conftest.py)

Create shared fixtures:
- `tmp_db` — creates a temp SQLite database via `init_db`
- `sample_author` — returns an `Author` instance
- `sample_article` — returns an `Article` instance
- `settings` — returns `ForensicsSettings` with test defaults

Write basic tests in `test_storage.py`:
- Test `init_db` creates tables
- Test `upsert_author` + read back
- Test `upsert_article` + `get_articles_by_author`
- Test `export_articles_jsonl` round-trip

## Validation

```bash
uv sync
uv run forensics --help          # must show subcommands
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v          # all tests pass
python -c "from forensics.models.author import Author; print('OK')"
python -c "from forensics.config.settings import ForensicsSettings; print('OK')"
```

## Handoff

After this phase, every module file exists (stubbed or implemented). The CLI works. Models are importable. Storage can read/write to SQLite. The foundation is set for Phase 2 (scraping).
