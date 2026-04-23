# mediaite-ghostink

Hybrid **AI writing forensics** pipeline for Mediaite.com: deterministic stages **scrape → extract → analyze → report**, combining statistical stylometry (change-points, time series, hypothesis tests) with embedding drift and optional token-probability and AI-baseline comparison.

[![CI](https://github.com/Abstract-Data/mediaite-ghostink/actions/workflows/ci.yml/badge.svg)](https://github.com/Abstract-Data/mediaite-ghostink/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3130/)
[![uv](https://img.shields.io/badge/uv-package%20manager-5A0FC8?logo=uv&logoColor=white)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pytest](https://img.shields.io/badge/testing-pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Hypothesis](https://img.shields.io/badge/property%20tests-hypothesis-6A4D8F)](https://hypothesis.readthedocs.io/)
[![Coverage](https://img.shields.io/badge/coverage-pytest--cov%20%E2%80%94%20%E2%89%A566%25%20lines-informational)](https://github.com/Abstract-Data/mediaite-ghostink/blob/main/pyproject.toml)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![packaging](https://img.shields.io/badge/build-hatchling-3775A9)](https://github.com/pypa/hatchling)

Pull requests receive a **CI report** comment (pytest summary and line coverage vs `main`) from [`.github/workflows/ci-report.yml`](.github/workflows/ci-report.yml).

---

## Table of contents

- [What this project does](#what-this-project-does)
- [Models, measurements, and algorithms](#models-measurements-and-algorithms)
- [Local machine setup](#local-machine-setup)
- [Forensic assurance and chain of custody](#forensic-assurance-and-chain-of-custody)
- [Responsible use](#responsible-use)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [CLI](#cli)
- [Typical workflows](#typical-workflows)
- [Repository layout](#repository-layout)
- [Data layout](#data-layout)
- [Optional dependency extras](#optional-dependency-extras)
- [Reports (Quarto)](#reports-quarto)
- [Notebooks and prompts](#notebooks-and-prompts)
- [Development](#development)
- [Documentation](#documentation)
- [Agent and contributor notes](#agent-and-contributor-notes)

---

## What this project does

The codebase implements two complementary lenses (see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/adr/ADR-001-hybrid-forensics-methodology.md`](docs/adr/ADR-001-hybrid-forensics-methodology.md)):

| Track | Role |
|--------|------|
| **Pipeline A — Statistical stylometry** | Lexical, structural, content, and productivity features over time; change-point methods (PELT, BOCPD, and related tests), rolling statistics, convergence windows, classical tests, effect sizes, and multiple-comparison correction. |
| **Pipeline B — Embedding drift** | Sentence-transformer embeddings (default **384-dimensional** `sentence-transformers/all-MiniLM-L6-v2`); centroid velocity, similarity decay, intra-period variance, optional UMAP views, optional comparison to synthetic “AI baseline” text. |

Optional tracks (extras and config):

| Track | Role |
|--------|------|
| **Phase 9 — Token-level probability** | Reference language model (default Hugging Face **GPT-2**) for perplexity-style signals; optional **Binoculars**-style contrast using Falcon-7B base vs instruct checkpoints (`uv sync --extra probability`). |
| **Phase 10 — AI baseline generation** | Local **Ollama** models (configurable) generate synthetic articles for controlled comparison (`uv sync --extra baseline`). |

Outputs include SQLite + Parquet + DuckDB-friendly artifacts, JSONL exports, analysis JSON under `data/analysis/`, optional probability and baseline trees under `data/probability/` and `data/ai_baseline/`, and Quarto-driven reports under `data/reports/`.

---

## Models, measurements, and algorithms

Settings below default from [`config.toml`](config.toml) and [`src/forensics/config/settings.py`](src/forensics/config/settings.py); override with **`FORENSICS_`** environment variables (nested keys use `__`, for example `FORENSICS_ANALYSIS__SIGNIFICANCE_THRESHOLD`).

### NLP and embeddings

| Component | Default | Purpose |
|-----------|---------|---------|
| **spaCy** | `en_core_web_md` (TOML: `spacy_model`) | Tokenization, linguistic features, and preflight validation. Install with `uv run python -m spacy download en_core_web_md`. |
| **Sentence Transformers** | `sentence-transformers/all-MiniLM-L6-v2` (`[analysis] embedding_model`) | Dense **384-d** article embeddings for drift, similarity decay, and monthly centroids. `embedding_model_version` is recorded for provenance. |
| **scikit-learn** | LDA, TF–IDF, etc. | Topic diversity, self-similarity, and related content features (see `src/forensics/features/`). |

### Stylometry and readability (per article)

Implemented feature families (see **Feature families** in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)):

1. **Lexical** — type–token ratio (TTR), MATTR, hapax rates, Yule’s K, Simpson’s D, stylometric “AI marker” and function-word style signals.
2. **Structural** — sentence length statistics, passive voice ratio, punctuation profile, parse-depth style measures via spaCy.
3. **Content** — n-gram entropy, rolling LDA topic diversity, formulaic / hedging-style scores.
4. **Productivity** — inter-article gaps, rolling counts, burst-style signals over the timeline.

**textstat** contributes readability-style scalar signals where used in the feature pipeline.

### Change-point and time-series analysis

| Method | Library / notes |
|--------|------------------|
| **PELT** | `ruptures`, RBF cost; penalty from `AnalysisConfig.pelt_penalty` (default **3.0**). |
| **BOCPD** | Bayesian online change-point detection (custom `scipy`-based implementation); hazard and threshold from settings. |
| **Chow, CUSUM, Kleinberg bursts** | Implemented under `src/forensics/analysis/` (see architecture doc). |
| **Convergence windows** | Windows where a minimum **fraction** of features move together (`convergence_window_days`, `convergence_min_feature_ratio`); optional **permutation null** (`convergence_use_permutation`) logs empirical p-values without changing detected windows. |

### Statistical inference

- **Tests:** Welch’s *t*, Mann–Whitney U, Kolmogorov–Smirnov (as implemented in analysis modules).
- **Effect sizes:** Cohen’s *d* where applicable.
- **Intervals:** Bootstrap resamples (`bootstrap_iterations`, default **1000**).
- **Multiple comparisons:** Benjamini–Hochberg or Bonferroni (`multiple_comparison_method`).

### Optional: token probability (extra `probability`)

| Setting | Default | Role |
|---------|---------|------|
| `reference_model` | `gpt2` | Causal LM for perplexity-style features. |
| `reference_model_revision` | pinned revision id | Reproducible HF snapshot. |
| `binoculars_model_base` / `binoculars_model_instruct` | Falcon-7B pair | Optional contrastive signal (`binoculars_enabled` default **false**). |
| `max_sequence_length`, `sliding_window_stride`, `batch_size`, `device` | see `config.toml` | Windowing and compute. |

### Optional: AI baseline text (extra `baseline`)

Local **Ollama** HTTP API (`baseline.ollama_base_url`); model tags from `baseline.models` and temperatures from `baseline.temperatures`. Generated artifacts and manifests live under `data/ai_baseline/` (see [`docs/RUNBOOK.md`](docs/RUNBOOK.md)).

### Survey mode (newsroom-wide)

**`[survey]`** thresholds (`min_articles`, `min_span_days`, `min_words_per_article`, yearly density, recent activity) gate which authors qualify for blind survey runs (`forensics survey`). See [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

---

## Local machine setup

1. **Install [uv](https://github.com/astral-sh/uv)** and **Python 3.13** (see `requires-python` in [`pyproject.toml`](pyproject.toml)).

2. **Clone and install dependencies**

   ```bash
   git clone git@github.com:Abstract-Data/mediaite-ghostink.git
   cd mediaite-ghostink
   uv sync --extra dev
   ```

3. **Install the spaCy pipeline** (must match `spacy_model` in `config.toml`, default `en_core_web_md`):

   ```bash
   uv run python -m spacy download en_core_web_md
   ```

4. **Edit [`config.toml`](config.toml)** — Replace template authors (`placeholder-target` / `placeholder-control`) with real author rows before any live scrape; the CLI rejects placeholders on discover/metadata/fetch paths.

5. **Optional: Quarto** — Required for `forensics report` and the report step of `forensics all`. [Install Quarto](https://quarto.org/docs/get-started/) so `quarto` is on your `PATH`.

6. **Optional extras**

   - `uv sync --extra probability` — Phase 9 token features (`forensics extract --probability`); pulls **torch / transformers** (large download).
   - `uv sync --extra baseline` — Phase 10 Ollama-driven baseline generation (`scripts/generate_baseline.py`, `forensics analyze --ai-baseline`, …).
   - `uv sync --extra tui` — Interactive `forensics setup` wizard (`uv run forensics setup`).

7. **Optional: Ollama** — For baseline generation, install Ollama and pull the model tags listed in `[baseline] models` (see [`docs/RUNBOOK.md`](docs/RUNBOOK.md)).

8. **Validate before a long run**

   ```bash
   uv run forensics validate
   uv run forensics preflight          # add --strict to fail on warnings
   ```

9. **Secrets / environment** — Copy [`.env.example`](.env.example) if your deployment uses external secrets or observability; the core pipeline is driven by **`config.toml`** and **`FORENSICS_*`**. Override the config file path with **`FORENSICS_CONFIG_FILE`**.

Default SQLite corpus path is **`data/articles.db`** under the project root (see `DEFAULT_DB_RELATIVE` in settings).

---

## Forensic assurance and chain of custody

This project is structured for **auditable, staged** research: each stage reads and writes defined artifacts so an independent reviewer can trace **what** was collected, **how** it was transformed, and **which** parameters were active.

### Stages and artifacts

1. **Scrape** — WordPress REST discovery, metadata, optional bulk or per-article body fetch, **simhash** near-duplicate control (`simhash_threshold`), persistence to SQLite (`content_hash` per article, scrape timestamps).
2. **Extract** — Deterministic feature vectors to Parquet; embeddings to `data/embeddings/`; optional probability parquet.
3. **Analyze** — JSON results under `data/analysis/`; analysis run rows in SQLite; **corpus custody** file written after analysis (see below).
4. **Report** — Quarto render from `notebooks/` into `data/reports/`.

Canonical paths are summarized in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#data-and-file-outputs).

### Integrity and hashing

- **Per-article `content_hash`** — SHA-256 of normalized article text at ingest (see `forensics.utils.hashing.content_hash`); stored in SQLite for tamper-evident comparison of body text.
- **`corpus_custody.json`** — Written under `data/analysis/` after analysis (`write_corpus_custody`): records a **corpus-level hash** derived from ordered per-article `content_hash` values so later runs can detect corpus drift.
- **`compute_config_hash`** — Deterministic hash of the full resolved **`ForensicsSettings`** payload (excluding derived paths) for tying reports to a configuration snapshot (`get_run_metadata` / run metadata patterns).

### Verification commands

- **`uv run forensics report --verify`** — Before render, recomputes the live corpus hash and compares it to `data/analysis/corpus_custody.json`; fails if missing or mismatched.
- **`uv run forensics analyze --verify-corpus`** — Same hash check without rendering a report.

### Preregistration (confirmatory runs)

`forensics lock-preregistration` writes a hashed lock of analysis thresholds to `data/preregistration/preregistration_lock.json`. **`analyze`** always runs `verify_preregistration` and records status in `data/analysis/run_metadata.json` (`ok` / `missing` / `mismatch`). This supports **pre-registered** vs exploratory analysis discipline (see [`docs/RUNBOOK.md`](docs/RUNBOOK.md)).

### Configuration: `[chain_of_custody]`

[`config.toml`](config.toml) includes:

```toml
[chain_of_custody]
verify_corpus_hash = true
verify_raw_archives = true
log_all_generations = true
```

These flags document the **intended** custody posture. **`verify_corpus_hash`** is enforced when you pass **`--verify`** / **`--verify-corpus`** as above (the TOML flags are not yet auto-wired to skip those CLI switches). Raw-archive and generation-log toggles are reserved for stricter operational policies; baseline manifests still record generation metadata under `data/ai_baseline/` when you run Phase 10.

### Exports and databases

- **`data/articles.jsonl`** — Human-readable corpus export for review.
- **`uv run forensics export`** — Single-file DuckDB bundle over SQLite + optional Parquet + analysis JSON (see runbook).

### What reviewers should ask for

- Frozen **`config.toml`** (or `FORENSICS_CONFIG_FILE` copy) and **`FORENSICS_*`** env used for the run.
- **`data/analysis/run_metadata.json`**, **`corpus_custody.json`**, per-author `*_result.json` and related analysis JSON.
- **`analysis_runs`** rows in **`data/articles.db`** (stage descriptions and timing where recorded).
- Quarto **HTML/PDF** outputs and the **notebook** sources under `notebooks/`.
- For probability / baseline: **`data/probability/model_card.json`**, **`data/ai_baseline/generation_manifest.json`**, and referenced model revisions.

---

## Responsible use

- **Scraping:** Defaults respect **`robots.txt`**, use a declared **`user_agent`**, and apply **rate limits** (`[scraping]`). Adjust only in line with site policy and applicable law.
- **Outcomes:** Stylometry and drift metrics are **statistical signals**, not legal findings. Targets vs controls must be defined **before** confirmatory interpretation; use preregistration and documented baselines.
- **Synthetic text:** AI baseline generation is for **controlled comparison**, not for passing off as human journalism.

---

## Architecture

- **Entrypoint:** `forensics` console script → [`src/forensics/cli/__init__.py`](src/forensics/cli/__init__.py) (**Typer**). Use `uv run forensics --help` and `uv run forensics <command> --help`.
- **Stages:** scraper (WordPress discovery + HTTP + dedup), feature extraction (`src/forensics/features/`), analysis (`src/forensics/analysis/`), reporting (`src/forensics/reporting/`). Full orchestration for `forensics all` lives in [`src/forensics/pipeline.py`](src/forensics/pipeline.py).
- **Configuration:** [`src/forensics/config/settings.py`](src/forensics/config/settings.py) loads **`config.toml`** at the project root with **`FORENSICS_`** environment overrides (pydantic-settings). Override the TOML path with **`FORENSICS_CONFIG_FILE`**.

Storage and model contracts are summarized in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and ADRs under [`docs/adr/`](docs/adr/).

---

## Requirements

- **Python 3.13** (see `requires-python` in [`pyproject.toml`](pyproject.toml)).
- **[uv](https://github.com/astral-sh/uv)** for environments and script execution (`uv run …`).
- **Quarto** on your `PATH` if you run `forensics report` or the report step of `forensics all` ([download](https://quarto.org/docs/get-started/)).
- **spaCy English model** for feature work aligned with CI (default **`en_core_web_md`**):

  ```bash
  uv run python -m spacy download en_core_web_md
  ```

---

## Installation

```bash
git clone git@github.com:Abstract-Data/mediaite-ghostink.git
cd mediaite-ghostink
uv sync --extra dev
```

Copy [`.env.example`](.env.example) to `.env` when you need optional secrets or observability hooks. Core pipeline configuration remains **`config.toml`** + **`FORENSICS_*`**.

---

## Configuration

1. **Authors and scraping:** Edit **[`config.toml`](config.toml)**. Replace template rows whose slugs are `placeholder-target` / `placeholder-control` with real authors before any live scrape; the CLI rejects those placeholders for discover/metadata/fetch paths.
2. **Nested settings:** Tables such as `[scraping]`, `[analysis]`, `[survey]`, `[probability]`, `[baseline]`, `[report]`, and `[chain_of_custody]` tune rate limits, analysis thresholds, survey eligibility, optional Phase 9/10 behavior, and report output.
3. **Environment:** Nested keys via `FORENSICS_*` are described in [`src/forensics/config/settings.py`](src/forensics/config/settings.py) and `.env.example`.

---

## CLI

Global options (Typer app root):

```bash
uv run forensics --version
uv run forensics -v scrape --help   # example: DEBUG logs for scrape
```

| Command | Purpose |
|---------|---------|
| **`scrape`** | WordPress author discovery, article metadata, HTML fetch, simhash dedup, optional raw archive. Combine flags as documented in `uv run forensics scrape --help` (e.g. `--discover`, `--metadata`, `--fetch`, `--dedup`, `--archive`, `--dry-run` with `--fetch`, `--force-refresh` with discover). |
| **`extract`** | Feature extraction + embeddings from `data/articles.db`. Options include `--author`, `--skip-embeddings`, and **`--probability`** (requires `--extra probability`). |
| **`analyze`** | Modes via flags: `--changepoint`, `--timeseries`, `--drift`, `--convergence`, `--compare`, `--ai-baseline`, corpus **`--verify-corpus`**, optional **`--author`**. With **no** analysis flags, the default runs **time-series** plus the **full convergence-oriented** analysis path; add flags to narrow or extend. See `uv run forensics analyze --help`. |
| **`report`** | Quarto render (`--notebook`, `--format` html|pdf|both, **`--verify`**). Requires per-author analysis artifacts under `data/analysis/`. |
| **`all`** | End-to-end: full scrape (`dispatch_scrape` with all stage flags false → same path as bare `forensics scrape`) → `extract_all_features` → `run_analyze(timeseries=True, convergence=True)` (**no** `--changepoint` / `--drift` unless you change `pipeline.py`) → `run_report`. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#forensics-all-end-to-end). |
| **`validate`**, **`preflight`**, **`survey`**, **`calibrate`**, **`export`**, **`lock-preregistration`**, **`setup`** | Operational and quality workflows — see [`docs/RUNBOOK.md`](docs/RUNBOOK.md). |

---

## Typical workflows

**Full pipeline (after configuring real authors and installing Quarto):**

```bash
uv run forensics all
```

**Incremental scrape (example):**

```bash
uv run forensics scrape --discover
uv run forensics scrape --metadata
uv run forensics scrape --fetch --dry-run   # count only
uv run forensics scrape --fetch
```

**Features then analysis:**

```bash
uv run forensics extract
uv run forensics analyze --changepoint --timeseries
uv run forensics analyze --drift
uv run forensics report --format html
```

---

## Repository layout

| Path | Role |
|------|------|
| `src/forensics/` | Application package (CLI, scraper, features, analysis, storage, config, models). |
| `tests/` | Pytest suite (`unit/`, `integration/`, `evals/`, fixtures, Hypothesis tests). |
| `docs/` | Architecture, testing policy, runbook, ADRs, deployment notes. |
| `notebooks/` | Jupyter chapters consumed by Quarto. |
| `prompts/` | Versioned prompts for agents and pipeline phases. |
| `scripts/` | Maintenance and one-off utilities. |
| `evals/` | Eval scenarios referenced from tooling or docs. |

---

## Data layout

| Path | Role |
|------|------|
| `data/articles.db` | Primary SQLite store (articles, authors, run metadata). |
| `data/authors_manifest.jsonl` | Discovered author manifest from scrape. |
| `data/raw/` | Raw HTML / year archives (see scrape `--archive`). |
| `data/features/` | Per-author feature tables (Parquet). |
| `data/embeddings/` | Embedding batches used by drift and reports. |
| `data/analysis/` | Per-author JSON results, run metadata, `corpus_custody.json`. |
| `data/articles.jsonl` | JSONL export for auditing. |
| `data/reports/` | Quarto book output (see `quarto.yml` `output-dir`). |
| `data/probability/` | Phase 9 outputs when enabled. |
| `data/ai_baseline/` | Phase 10 synthetic baseline artifacts. |
| `data/survey/`, `data/calibration/` | Survey and calibration run outputs (see runbook). |

Exact filenames evolve with the pipeline; treat [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) as the conceptual map.

---

## Optional dependency extras

Defined in [`pyproject.toml`](pyproject.toml):

| Extra | Install | Use |
|-------|---------|-----|
| **`dev`** | `uv sync --extra dev` | pytest, pytest-cov, Hypothesis, Ruff, pre-commit. |
| **`probability`** | `uv sync --extra probability` | Phase 9 token-level features (torch, transformers); `forensics extract --probability`. |
| **`baseline`** | `uv sync --extra baseline` | pydantic-ai + evals for baseline workflows; local **[baseline]** config in `config.toml` (Ollama) for generation smoke tests. |
| **`tui`** | `uv sync --extra tui` | Textual wizard: `uv run forensics setup`. |

---

## Reports (Quarto)

- Project config: [`quarto.yml`](quarto.yml) (book title, chapters under `notebooks/`, output to **`data/reports/`**).
- **`forensics report`** shells out to **`quarto`**; install separately if missing.
- **`--verify`** checks corpus hash material under `data/analysis/` (see [`src/forensics/utils/provenance.py`](src/forensics/utils/provenance.py)).

---

## Notebooks and prompts

- **`notebooks/`** — Exploratory and chapter notebooks wired into the Quarto book.
- **`prompts/`** — Versioned agent / phase prompts with **`current.md`** pointers; see [`prompts/README.md`](prompts/README.md) for the release contract.

---

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v
uv run pytest tests/ -v --cov=src --cov-report=term-missing
```

- **Default pytest** options (markers, coverage on `forensics`) live in [`pyproject.toml`](pyproject.toml). Slow tests are marked `@pytest.mark.slow`; default runs exclude them (`-m 'not slow'`). Run them with `uv run pytest tests/ -m slow` when needed.
- **CI:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs Ruff lint/format and pytest with coverage JSON for PR comments.
- **Pre-commit:** [`uv run pre-commit install`](https://pre-commit.com/) using [`.pre-commit-config.yaml`](.pre-commit-config.yaml).

Testing policy and coverage gates are documented in [`docs/TESTING.md`](docs/TESTING.md).

---

## Documentation

| Document | Contents |
|----------|----------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Runtime flow, modules, storage, feature and analysis methods. |
| [`docs/TESTING.md`](docs/TESTING.md) | Test layout, commands, coverage rules. |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Operational runbook (survey, calibration, export, baseline, preflight). |
| [`docs/DEPLOYMENTS.md`](docs/DEPLOYMENTS.md) | Deployment notes. |
| [`docs/GUARDRAILS.md`](docs/GUARDRAILS.md) | Recurring failure patterns and mitigations. |
| [`docs/adr/`](docs/adr/) | Architecture decision records. |

---

## Agent and contributor notes

- **[`AGENTS.md`](AGENTS.md)** — Boundaries, commands, embedding pin, data directories, and conventions for automation and humans.
- **Governance / hooks:** [`.github/workflows/agents-governance.yml`](.github/workflows/agents-governance.yml) and [`docs/adr/ADR-003-agent-governance-and-hooks.md`](docs/adr/ADR-003-agent-governance-and-hooks.md).
