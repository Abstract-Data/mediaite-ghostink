# mediaite-ghostink

Forensics pipeline scaffold for `scrape -> extract -> analyze -> report`.

## Quickstart

```bash
uv sync
uv run forensics all
uv run pytest tests/ -v
```

## Probability features (Pipeline C)

Perplexity, burstiness, and optional Binoculars-style scores use **PyTorch** and **HuggingFace
Transformers** (~500MB+ for GPT-2; tens of GB for Falcon-7B). They are optional so the
core scrape → extract path can stay lightweight:

- **Develop / CI (recommended):** `uv sync --extra dev` (includes `torch`, `transformers`,
  `accelerate`).
- **Probability only:** `uv sync --extra probability`.

After sync, `uv run forensics extract` runs stylometric features and then GPT-2 probability
scoring when the stack is installed (use `--skip-probability` to skip). Use
`uv run forensics extract --probability` for probability-only scoring into `data/probability/`.
Run slow integration tests with HuggingFace downloads via `uv run pytest tests/test_probability.py`
(without `--skip-slow`).
