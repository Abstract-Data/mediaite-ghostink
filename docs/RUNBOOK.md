# Runbook

Operational quick reference. Agents: append new sections here whenever you discover debug techniques, resolve recurring errors, add CLI commands, or learn environment facts that future operators need.

## Local Setup

1. Install dependencies: `uv sync`
2. For Phase 10 (baseline generation): `uv sync --extra baseline`
3. Validate environment: `uv run ruff check . && uv run ruff format --check .`
4. Run tests: `uv run pytest tests/ -v`
5. Run with coverage: `uv run pytest tests/ -v --cov=src --cov-report=term-missing`

## Pipeline Operations

- Run full pipeline: `uv run forensics all`
- Stage-by-stage:
  - `uv run forensics scrape`
  - `uv run forensics extract`
  - `uv run forensics analyze`
  - `uv run forensics report`
- Extract probability features (Phase 9): `uv run forensics extract --probability`
- Generate AI baseline (Phase 10): `uv run python scripts/generate_baseline.py --author {slug}`

## Expected Artifacts

After a successful full run, verify:

- `data/raw/documents.json`
- `data/features/features.parquet`
- `data/analysis/analysis.json`
- `data/reports/report.md`
- `data/pipeline/summary.json`

Phase 9 outputs: `data/probability/{author_slug}.parquet`, `data/probability/model_card.json`
Phase 10 outputs: `data/ai_baseline/{author_slug}/`, `data/ai_baseline/generation_manifest.json`

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

## Git Workflow

```bash
# Before every commit
uv run ruff format .
uv run ruff check . --fix
uv run pytest tests/ -v

# Conventional commit prefixes
# feat: fix: refactor: test: docs: chore:
```

## Incident Handoff

When handing off active work:

- Record the exact command(s) run.
- Capture failing tests or observed error text.
- Add status and next steps in `HANDOFF.md` (required — see CLAUDE.md Session Boundaries).
