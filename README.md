# mediaite-ghostink

Hybrid **AI writing forensics** pipeline for Mediaite.com: deterministic stages **scrape → extract → analyze → report**, combining statistical stylometry (change-points, time series, hypothesis tests) with embedding drift and optional AI-baseline comparison.

[![CI](https://github.com/Abstract-Data/mediaite-ghostink/actions/workflows/ci.yml/badge.svg)](https://github.com/Abstract-Data/mediaite-ghostink/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3130/)
[![uv](https://img.shields.io/badge/uv-package%20manager-5A0FC8?logo=uv&logoColor=white)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pytest](https://img.shields.io/badge/testing-pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Hypothesis](https://img.shields.io/badge/property%20tests-hypothesis-6A4D8F)](https://hypothesis.readthedocs.io/)
[![Coverage](https://img.shields.io/badge/coverage-pytest--cov%20%E2%80%94%20%E2%89%A560%25%20lines-informational)](https://github.com/Abstract-Data/mediaite-ghostink/blob/main/pyproject.toml)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![packaging](https://img.shields.io/badge/build-hatchling-3775A9)](https://github.com/pypa/hatch)

Pull requests receive a **CI report** comment (pytest summary and line coverage vs `main`) from [`.github/workflows/ci-report.yml`](.github/workflows/ci-report.yml).

---

## Table of contents

- [What this project does](#what-this-project-does)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [CLI](#cli)
- [Typical workflows](#typical-workflows)
- [Data layout](#data-layout)
- [Optional dependency extras](#optional-dependency-extras)
- [Reports (Quarto)](#reports-quarto)
- [Notebooks & prompts](#notebooks--prompts)
- [Development](#development)
- [Documentation](#documentation)
- [Agent & contributor notes](#agent--contributor-notes)

---

## What this project does

The codebase implements two complementary lenses (see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/adr/ADR-001-hybrid-forensics-methodology.md`](docs/adr/ADR-001-hybrid-forensics-methodology.md)):

| Track | Role |
|--------|------|
| **Pipeline A — Statistical stylometry** | Lexical, structural, content, and productivity features over time; change-point methods (e.g. PELT, BOCPD), rolling statistics, convergence windows, classical tests and effect sizes. |
| **Pipeline B — Embedding drift** | Sentence-transformer embeddings (default **384-dim** `sentence-transformers/all-MiniLM-L6-v2`); centroid velocity, similarity decay, variance, optional UMAP views, optional synthetic AI baseline articles. |

Outputs include SQLite + Parquet + DuckDB-friendly artifacts, JSONL exports, analysis JSON under `data/analysis/`, and Quarto-driven reports under `data/reports/`.

---

## Architecture

- **Entrypoint:** `forensics` console script → [`src/forensics/cli/__init__.py`](src/forensics/cli/__init__.py) (**Typer**). Use `uv run forensics --help` and `uv run forensics <command> --help`.
- **Stages:** scraper (WordPress discovery + HTTP + dedup), feature extraction (`src/forensics/features/`), analysis (`src/forensics/analysis/`), reporting (`src/forensics/reporting.py`). Full orchestration for `forensics all` lives in [`src/forensics/pipeline.py`](src/forensics/pipeline.py).
- **Configuration:** [`src/forensics/config/settings.py`](src/forensics/config/settings.py) loads **`config.toml`** at the project root with **`FORENSICS_`** environment overrides (pydantic-settings). Override the TOML path with **`FORENSICS_CONFIG_FILE`**.

Storage and model contracts are summarized in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and ADRs under [`docs/adr/`](docs/adr/).

---

## Requirements

- **Python 3.13** (see `requires-python` in [`pyproject.toml`](pyproject.toml)).
- **[uv](https://github.com/astral-sh/uv)** for environments and script execution (`uv run …`).
- **Quarto** on your `PATH` if you run `forensics report` or the report step of `forensics all` ([download](https://quarto.org/docs/get-started/)).
- **spaCy English model** for feature work aligned with CI:

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

Copy [`.env.example`](.env.example) to `.env` and fill values for your environment (API keys, optional observability). See [Configuration](#configuration).

---

## Configuration

1. **Authors & scraping:** Edit **[`config.toml`](config.toml)**. Replace template rows whose slugs are `placeholder-target` / `placeholder-control` with real authors before any live scrape; the CLI rejects those placeholders for discover/metadata/fetch paths.
2. **Nested settings:** Tables such as `[scraping]`, `[analysis]`, `[probability]`, `[baseline]`, `[report]`, and `[chain_of_custody]` tune rate limits, analysis thresholds, optional Phase 9/10 behavior, and report output.
3. **Environment:** Variables like `FORENSICS_DATA_DIR`, `FORENSICS_REPORT_PATH`, and nested keys via `FORENSICS_*` are described in [`src/forensics/config/settings.py`](src/forensics/config/settings.py) and `.env.example`.

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
| **`analyze`** | Modes via flags: `--changepoint`, `--timeseries`, `--drift`, `--convergence`, `--compare`, `--ai-baseline`, corpus **`--verify`**, optional **`--author`**. With **no** analysis flags, the default runs **time-series** plus the **full convergence-oriented** analysis path; add flags to narrow or extend. See `uv run forensics analyze --help`. |
| **`report`** | Quarto render (`--notebook`, `--format` html|pdf|both, `--verify`). Requires per-author analysis artifacts under `data/analysis/`. |
| **`all`** | End-to-end: scrape (default full scrape path) → extract → analyze (time-series + convergence as in `run_analyze`) → `report`. |

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
| `data/features/` | Feature tables (Parquet / pipeline outputs). |
| `data/embeddings/` | Embedding artifacts used by drift and reports. |
| `data/analysis/` | Per-author JSON results, run metadata, custody hashes. |
| `data/articles.jsonl` | JSONL export for auditing. |
| `data/reports/` | Quarto book output (see `quarto.yml` `output-dir`). |

Exact filenames evolve with the pipeline; treat [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) as the conceptual map.

---

## Optional dependency extras

Defined in [`pyproject.toml`](pyproject.toml):

| Extra | Install | Use |
|-------|---------|-----|
| **`dev`** | `uv sync --extra dev` | pytest, pytest-cov, Hypothesis, Ruff, pre-commit. |
| **`probability`** | `uv sync --extra probability` | Phase 9 token-level features (torch, transformers); `forensics extract --probability`. |
| **`baseline`** | `uv sync --extra baseline` | pydantic-ai + evals for baseline workflows; local **[baseline]** config in `config.toml` (e.g. Ollama) for orchestration smoke tests. |

---

## Reports (Quarto)

- Project config: [`quarto.yml`](quarto.yml) (book title, chapters under `notebooks/`, output to **`data/reports/`**).
- **`forensics report`** shells out to **`quarto`**; install separately if missing.
- Optional **`--verify`** checks corpus hash material under `data/analysis/` (see [`src/forensics/utils/provenance.py`](src/forensics/utils/provenance.py)).

---

## Notebooks & prompts

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
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Operational runbook. |
| [`docs/DEPLOYMENTS.md`](docs/DEPLOYMENTS.md) | Deployment notes. |
| [`docs/GUARDRAILS.md`](docs/GUARDRAILS.md) | Recurring failure patterns and mitigations. |
| [`docs/adr/`](docs/adr/) | Architecture decision records. |

---

## Agent & contributor notes

- **[`AGENTS.md`](AGENTS.md)** — Boundaries, commands, embedding pin, data directories, and conventions for automation and humans.
- **Governance / hooks:** [`.github/workflows/agents-governance.yml`](.github/workflows/agents-governance.yml) and [`docs/adr/ADR-003-agent-governance-and-hooks.md`](docs/adr/ADR-003-agent-governance-and-hooks.md).
