"""Phase 9 — perplexity and burstiness features.

Pure compute functions operate on preloaded ``model`` / ``tokenizer`` handles so
callers can decide when to bear the ~500MB GPT-2 load cost. Sentence
segmentation uses a simple regex rather than spaCy so the probability pipeline
does not require ``en_core_web_md``.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[tuple[str, str | None, str], tuple[Any, Any]] = {}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def split_sentences(text: str) -> list[str]:
    """Cheap sentence segmentation (no spaCy dependency)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(cleaned) if s.strip()]
    return parts or [cleaned]


def clear_model_cache() -> None:
    """Drop cached torch models (tests)."""
    _MODEL_CACHE.clear()


def resolve_torch_device(device: str | None) -> str:
    """Pick ``cpu`` or ``cuda`` for optional extras; ``cpu`` when torch is missing."""
    if device in ("cpu", "cuda"):
        return device
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_reference_model(
    model_name: str = "gpt2",
    revision: str | None = None,
    device: str | None = None,
) -> tuple[Any, Any]:
    """Lazy-load the reference LM (default: GPT-2) and tokenizer."""
    resolved_device = resolve_torch_device(device)
    cache_key = (model_name, revision, resolved_device)
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    try:
        import torch  # type: ignore[import-not-found]
        from transformers import (  # type: ignore[import-not-found]
            AutoModelForCausalLM,
            AutoTokenizer,
        )
    except ImportError as exc:  # pragma: no cover - exercised via CLI error path
        raise ImportError(
            "Probability features require torch + transformers. "
            "Install with: uv sync --extra probability"
        ) from exc

    logger.info(
        "Loading reference LM %s (revision=%s, device=%s)",
        model_name,
        revision,
        resolved_device,
    )
    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=revision)
    dtype = torch.float16 if resolved_device == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(model_name, revision=revision, torch_dtype=dtype)
    model.to(resolved_device)
    model.eval()

    _MODEL_CACHE[cache_key] = (model, tokenizer)
    return model, tokenizer


def _perplexity_of_ids(input_ids, model, *, max_length: int, stride: int) -> float:
    """Sliding-window negative log-likelihood -> perplexity."""
    import torch  # type: ignore[import-not-found]

    device = next(model.parameters()).device
    ids = input_ids.to(device)
    seq_len = ids.size(1)
    if seq_len < 2:
        return math.nan

    nlls: list[torch.Tensor] = []
    prev_end = 0
    for begin in range(0, seq_len, stride):
        end = min(begin + max_length, seq_len)
        trg_len = end - prev_end
        chunk = ids[:, begin:end]
        target = chunk.clone()
        target[:, :-trg_len] = -100
        with torch.no_grad():
            outputs = model(chunk, labels=target)
        nlls.append(outputs.loss * trg_len)
        prev_end = end
        if end == seq_len:
            break

    total_nll = torch.stack(nlls).sum() / seq_len
    return float(torch.exp(total_nll).item())


def compute_perplexity(
    text: str,
    model: Any,
    tokenizer: Any,
    *,
    max_length: int = 1024,
    stride: int = 512,
    low_ppl_threshold: float = 20.0,
) -> dict[str, float]:
    """Compute article + sentence-level perplexity statistics.

    Returns a dict with:
      - mean_perplexity:       article-level PPL over all tokens
      - median_perplexity:     median of per-sentence PPLs
      - perplexity_variance:   burstiness (variance of sentence PPLs)
      - min_sentence_ppl:      lowest sentence PPL (most AI-like sentence)
      - max_sentence_ppl:      highest sentence PPL
      - ppl_skewness:          skew of sentence PPL distribution
      - low_ppl_sentence_ratio: fraction of sentences with PPL < threshold
    """
    import torch  # type: ignore[import-not-found]

    ids = tokenizer(text or "", return_tensors="pt")["input_ids"]
    mean_ppl = _perplexity_of_ids(ids, model, max_length=max_length, stride=stride)

    sentence_ppls: list[float] = []
    for sent in split_sentences(text or ""):
        if len(sent.split()) < 3:
            continue
        sent_ids = tokenizer(sent, return_tensors="pt")["input_ids"]
        if sent_ids.size(1) < 2:
            continue
        p = _perplexity_of_ids(sent_ids, model, max_length=max_length, stride=stride)
        if not (math.isnan(p) or math.isinf(p)):
            sentence_ppls.append(p)

    if not sentence_ppls:
        return {
            "mean_perplexity": mean_ppl if not math.isnan(mean_ppl) else 0.0,
            "median_perplexity": 0.0,
            "perplexity_variance": 0.0,
            "min_sentence_ppl": 0.0,
            "max_sentence_ppl": 0.0,
            "ppl_skewness": 0.0,
            "low_ppl_sentence_ratio": 0.0,
        }

    tensor = torch.tensor(sentence_ppls, dtype=torch.float64)
    mean = tensor.mean()
    var = tensor.var(unbiased=False) if tensor.numel() > 1 else torch.tensor(0.0)
    std = var.sqrt().clamp(min=1e-12)
    skew_val = ((tensor - mean) ** 3).mean() / (std**3)
    return {
        "mean_perplexity": float(mean_ppl) if not math.isnan(mean_ppl) else 0.0,
        "median_perplexity": float(tensor.median().item()),
        "perplexity_variance": float(var.item()),
        "min_sentence_ppl": float(tensor.min().item()),
        "max_sentence_ppl": float(tensor.max().item()),
        "ppl_skewness": float(skew_val.item()) if tensor.numel() > 1 else 0.0,
        "low_ppl_sentence_ratio": float((tensor < low_ppl_threshold).sum().item() / tensor.numel()),
    }
