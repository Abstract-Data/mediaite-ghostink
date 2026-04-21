# Phase 9: Probability Features — Perplexity, Burstiness & Binoculars Score

Version: 0.1.0
Status: pending
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 4 (feature extraction complete, articles in Parquet/SQLite)

## Objective

Implement token-level probability features that directly measure how "AI-like" text is, complementing the stylometric features (Phase 4) and embedding drift (Phase 6). This produces **Pipeline C** for the convergence framework — an independent signal based on language model perplexity rather than writing style or semantic drift.

After this phase, each article has perplexity, burstiness, and Binoculars scores stored alongside the existing feature vectors. The longitudinal trajectory of these scores (did perplexity drop abruptly at a specific date?) is the key forensic signal.

## Background

Current AI detection research identifies per-token probability metrics as the most direct signal of AI authorship:

- **Perplexity:** How predictable text is to a language model. AI-generated text scores systematically lower because LLMs select statistically predictable tokens.
- **Burstiness:** Variance of per-sentence perplexity across an article. Human writers produce irregular spikes; AI output is uniformly flat.
- **Binoculars score:** The ratio of perplexity to cross-perplexity between two related models. Achieves >90% detection of ChatGPT text at 0.01% FPR without any LLM-specific training data.

## 1. Reference Model Selection & Pinning

### Primary reference model: `gpt2` (124M parameters)

- Available via HuggingFace `transformers`
- Well-studied baseline in detection literature
- Fast inference on CPU
- Pin by model revision hash (not just name): store the specific HuggingFace commit hash in `config.toml`

### Binoculars model pair: `tiiuae/falcon-7b` + `tiiuae/falcon-7b-instruct`

- The Binoculars method requires two related models (base + instruct)
- Falcon-7B is the recommended pair from the original paper (Hans et al., 2024)
- Requires GPU for reasonable throughput; fall back to batch-size-1 on CPU with warning

### config.toml additions

```toml
[probability]
reference_model = "gpt2"
reference_model_revision = "e7da7f2"  # pin to specific HuggingFace commit
binoculars_model_base = "tiiuae/falcon-7b"
binoculars_model_instruct = "tiiuae/falcon-7b-instruct"
binoculars_enabled = true  # set false if no GPU available
max_sequence_length = 1024
batch_size = 16  # reduce for CPU
device = "auto"  # auto-detect GPU, fallback to CPU
```

### Model version pinning

Store model metadata in `data/probability/model_card.json`:

```json
{
  "reference_model": "gpt2",
  "reference_model_revision": "e7da7f2",
  "reference_model_sha256": "...",
  "binoculars_base": "tiiuae/falcon-7b",
  "binoculars_instruct": "tiiuae/falcon-7b-instruct",
  "scored_at": "2026-04-20T12:00:00Z",
  "device_used": "cuda:0",
  "transformers_version": "4.x.x"
}
```

Before scoring, check if `model_card.json` exists and matches config. If mismatch, warn and offer to re-score entire corpus (since scores are not comparable across model versions).

## 2. Perplexity Computation (src/forensics/features/probability.py)

### compute_perplexity(text: str, model, tokenizer) -> dict

```python
import torch
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

def compute_perplexity(
    text: str,
    model: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    max_length: int = 1024,
    stride: int = 512,
) -> dict:
    """Compute per-article and per-sentence perplexity metrics.

    Uses sliding window with stride for articles longer than max_length.

    Returns:
        {
            "mean_perplexity": float,       # article-level PPL
            "median_perplexity": float,      # median of sentence PPLs
            "perplexity_variance": float,    # burstiness — variance of sentence PPLs
            "min_sentence_ppl": float,       # lowest sentence PPL (most AI-like)
            "max_sentence_ppl": float,       # highest sentence PPL (most human-like)
            "ppl_skewness": float,           # skew of sentence PPL distribution
            "low_ppl_sentence_ratio": float, # fraction of sentences with PPL < threshold
        }
    """
```

### Article-level perplexity

Formula: PPL(s) = exp(-1/L * Σ log P(x_i | x_{0:i-1}))

where L = number of tokens, P(x_i | x_{0:i-1}) is the model's predicted probability for each token given its prefix.

Implementation:
1. Tokenize the full article text
2. For articles longer than `max_length`, use sliding window with `stride` overlap
3. Run forward pass, extract log-probabilities from model output
4. Average negative log-likelihoods across all tokens
5. Exponentiate to get perplexity

### Sentence-level perplexity (for burstiness)

1. Split article into sentences (reuse spaCy segmentation from Phase 4, or simple regex split)
2. Compute perplexity for each sentence independently
3. Burstiness = variance of these per-sentence perplexity values
4. Human text: high variance (some sentences predictable, some surprising)
5. AI text: low variance (uniformly predictable)

### Low-PPL sentence ratio

Count sentences where perplexity falls below a configurable threshold (default: 20.0 for GPT-2). This captures the fraction of "suspiciously predictable" sentences. A sudden increase in this ratio over time is a strong signal.

## 3. Binoculars Score (src/forensics/features/binoculars.py)

### compute_binoculars_score(text: str, model_base, model_instruct, tokenizer) -> float

The Binoculars method (Hans et al., 2024):

```python
def compute_binoculars_score(
    text: str,
    model_base: AutoModelForCausalLM,
    model_instruct: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    max_length: int = 512,
) -> float:
    """Compute Binoculars score: ratio of cross-perplexity to perplexity.

    Score = PPL(text; model_base) / cross_PPL(text; model_base, model_instruct)

    Where cross-perplexity uses model_base's logits but model_instruct's
    token probabilities (or vice versa).

    Low scores (< threshold) indicate AI-generated text.
    The original paper reports >90% TPR at 0.01% FPR with threshold ~0.9.

    Returns:
        Binoculars score (float). Lower = more likely AI-generated.
    """
```

Implementation:
1. Tokenize text with shared tokenizer
2. Forward pass through both models
3. Compute perplexity using model_base logits
4. Compute cross-perplexity: use model_base to get next-token distributions, but score using model_instruct's predictions
5. Return the ratio

### GPU/CPU handling

```python
def load_binoculars_models(config: ProbabilityConfig) -> tuple | None:
    """Load Binoculars model pair. Returns None if GPU unavailable and binoculars_enabled=True."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu" and config.binoculars_enabled:
        logger.warning(
            "Binoculars requires GPU for reasonable performance. "
            "Falling back to CPU with batch_size=1. Set binoculars_enabled=false to skip."
        )
    # Load models with torch_dtype=float16 on GPU, float32 on CPU
```

## 4. Pipeline Orchestrator Integration

### extract_probability_features(db_path: Path, config: ForensicsSettings) -> int

```python
def extract_probability_features(
    db_path: Path,
    config: ForensicsSettings,
) -> int:
    """Extract probability features for all articles.

    1. Load reference model (GPT-2) — always
    2. Load Binoculars model pair — if enabled and GPU available
    3. For each article (exclude duplicates, redirects, <50 words):
       a. Compute perplexity metrics
       b. Compute Binoculars score (if available)
       c. Store results
    4. Write to data/probability/{author_slug}.parquet
    5. Return count of processed articles
    """
```

### Batch processing

Process articles in batches for GPU efficiency:
- Default batch_size: 16 (GPU) / 1 (CPU)
- Log progress: "Scoring probability features: {n}/{total} articles ({author_name})"
- Estimated throughput: ~50 articles/min (GPU), ~5 articles/min (CPU, GPT-2 only)

### Storage

- `data/probability/{author_slug}.parquet` — per-article probability features
- `data/probability/model_card.json` — frozen model metadata

Parquet schema:
```
article_id: int
author_id: int
publish_date: date
mean_perplexity: float
median_perplexity: float
perplexity_variance: float  # burstiness
min_sentence_ppl: float
max_sentence_ppl: float
ppl_skewness: float
low_ppl_sentence_ratio: float
binoculars_score: float  # nullable if not computed
```

## 5. CLI Integration

```
uv run forensics extract --probability          # probability features only
uv run forensics extract --probability --no-binoculars  # perplexity only, skip Binoculars
uv run forensics extract --probability --author {slug}  # single author
uv run forensics extract --probability --device cpu     # force CPU
```

The `extract` command's default behavior (`uv run forensics extract`) should include probability features if the reference model is available. If the model hasn't been downloaded, log a helpful message:
```
INFO: Probability features require downloading gpt2 (~500MB). Run with --probability to enable.
```

## 6. Time-Series Analysis Integration

The probability features are designed for longitudinal analysis. In Phase 5/7, treat them like any other feature time series:

- **Perplexity timeline:** Plot mean_perplexity over time per author. A sudden drop indicates text became more predictable to the LM.
- **Burstiness timeline:** Plot perplexity_variance over time. A sudden decrease indicates text became more uniform (AI-like).
- **Binoculars timeline:** Plot binoculars_score over time. A drop below ~0.9 is the detection threshold.
- **Low-PPL ratio timeline:** Plot low_ppl_sentence_ratio over time. An increase indicates more "suspiciously predictable" sentences.

All of these are time-series features that feed into the existing change-point detection (PELT, BOCPD) and convergence framework. They constitute **Pipeline C** — an independent analytical track alongside stylometric change-points (Pipeline A) and embedding drift (Pipeline B).

## 7. Dependencies

Add to `pyproject.toml`:
```toml
"torch>=2.0",
"transformers>=4.40",
"accelerate>=0.30",
```

Note: `torch` is a large dependency (~2GB). Document this in the README and make probability features optional — the core pipeline (phases 1-8) should work without torch installed.

## 8. Tests (tests/test_probability.py)

- **test_perplexity_computation**: Known text -> perplexity is a positive float
- **test_perplexity_ai_vs_human**: GPT-2-generated text has lower perplexity than random human text (use a simple fixture)
- **test_burstiness_uniform_text**: Text with identical sentences -> low variance
- **test_burstiness_diverse_text**: Text mixing short/long/complex sentences -> higher variance
- **test_sliding_window**: Article longer than max_length produces valid perplexity
- **test_binoculars_score_range**: Score is a positive float
- **test_model_card_creation**: After scoring, model_card.json exists with correct fields
- **test_model_version_mismatch**: Changed config triggers warning
- **test_cpu_fallback**: Without GPU, falls back gracefully
- **test_parquet_schema**: Output Parquet has expected columns and types

Use `@pytest.mark.slow` for tests that load actual models. Provide a `--skip-slow` pytest option.

## Validation

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_probability.py -v -k "not slow"

# Full run with model download (requires ~500MB for GPT-2, ~14GB for Falcon-7B):
uv run forensics extract --probability --author {some-slug}
ls -la data/probability/
cat data/probability/model_card.json
```

## Handoff

After this phase, every article has perplexity, burstiness, and (optionally) Binoculars scores. These feed into the existing analysis pipeline as Pipeline C. Phase 7's convergence framework can now cross-validate three independent analytical tracks: stylometric change-points (A), embedding drift (B), and probability trajectories (C). This is the most direct evidence of AI-generated text in the pipeline.
