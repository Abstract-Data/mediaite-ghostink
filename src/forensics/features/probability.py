"""Perplexity and burstiness from a causal language model (Phase 9)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy import stats

if TYPE_CHECKING:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    """Lightweight sentence boundaries (regex); avoids spaCy in hot path."""
    parts = [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]
    return parts if parts else [text.strip()] if text.strip() else []


def _resolve_max_positions(model: Any, requested: int) -> int:
    cfg = getattr(model, "config", None)
    npos = getattr(cfg, "n_positions", None) if cfg is not None else None
    if npos is None:
        return requested
    return int(min(requested, int(npos)))


def _sliding_window_mean_nll(
    model: Any,
    input_ids: torch.Tensor,
    *,
    max_length: int,
    stride: int,
    device: torch.device,
) -> tuple[float, int]:
    """Return (sum_negative_log_likelihood, token_count) for full sequence."""
    import torch

    max_length = _resolve_max_positions(model, max_length)
    seq_len = int(input_ids.size(1))
    if seq_len < 2:
        return 0.0, 0
    total_nll = 0.0
    total_tokens = 0
    prev_end_loc = 0
    for begin_loc in range(0, seq_len, stride):
        end_loc = min(begin_loc + max_length, seq_len)
        trg_len = end_loc - prev_end_loc
        chunk = input_ids[:, begin_loc:end_loc].to(device)
        target_ids = chunk.clone()
        if begin_loc > 0:
            target_ids[:, :-trg_len] = -100
        with torch.no_grad():
            outputs = model(chunk, labels=target_ids)
        # HF loss = mean CE over non-ignored next-token positions
        n_contrib = int((target_ids[:, 1:] != -100).sum().item())
        if n_contrib > 0:
            total_nll += float(outputs.loss) * n_contrib
            total_tokens += n_contrib
        prev_end_loc = end_loc
        if end_loc == seq_len:
            break
    return total_nll, total_tokens


def _single_forward_mean_nll(
    model: Any,
    input_ids: torch.Tensor,
    device: torch.device,
) -> tuple[float, int]:
    import torch

    chunk = input_ids.to(device)
    if chunk.size(1) < 2:
        return 0.0, 0
    with torch.no_grad():
        outputs = model(chunk, labels=chunk)
    n_contrib = chunk.size(1) - 1
    return float(outputs.loss) * n_contrib, n_contrib


def _token_sequence_nll(
    model: Any,
    tokenizer: Any,
    text: str,
    *,
    max_length: int,
    stride: int,
    device: torch.device,
) -> float:
    """Average NLL per predicted token (natural log) for ``text``."""
    enc = tokenizer(text, return_tensors="pt", add_special_tokens=False)
    input_ids = enc["input_ids"]
    if input_ids.numel() == 0:
        return float("nan")
    max_length = _resolve_max_positions(model, max_length)
    if input_ids.size(1) <= max_length:
        total_nll, ntok = _single_forward_mean_nll(model, input_ids, device)
    else:
        total_nll, ntok = _sliding_window_mean_nll(
            model,
            input_ids,
            max_length=max_length,
            stride=stride,
            device=device,
        )
    if ntok <= 0:
        return float("nan")
    return total_nll / ntok


def sentence_perplexities(
    text: str,
    model: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    *,
    max_length: int,
    stride: int,
    device: torch.device,
) -> list[float]:
    """Per-sentence perplexity (truncated windows per sentence)."""
    import math

    sents = split_sentences(text)
    out: list[float] = []
    for sent in sents:
        nll = _token_sequence_nll(
            model,
            tokenizer,
            sent,
            max_length=max_length,
            stride=stride,
            device=device,
        )
        if math.isnan(nll):
            continue
        out.append(float(math.exp(nll)))
    return out


def compute_perplexity(
    text: str,
    model: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    *,
    max_length: int = 1024,
    stride: int = 512,
    low_ppl_threshold: float = 20.0,
    device: torch.device | str | None = None,
) -> dict[str, float]:
    """Compute per-article and per-sentence perplexity metrics.

    Uses a strided sliding window for articles longer than ``max_length``.
    """
    import math

    import torch

    dev = torch.device(device) if device is not None else torch.device("cpu")
    article_nll = _token_sequence_nll(
        model,
        tokenizer,
        text,
        max_length=max_length,
        stride=stride,
        device=dev,
    )
    mean_ppl = float(math.exp(article_nll)) if not math.isnan(article_nll) else float("nan")

    sent_ppls = sentence_perplexities(
        text,
        model,
        tokenizer,
        max_length=max_length,
        stride=stride,
        device=dev,
    )
    if not sent_ppls:
        nan = float("nan")
        return {
            "mean_perplexity": mean_ppl,
            "median_perplexity": nan,
            "perplexity_variance": nan,
            "min_sentence_ppl": nan,
            "max_sentence_ppl": nan,
            "ppl_skewness": nan,
            "low_ppl_sentence_ratio": nan,
        }

    arr = np.asarray(sent_ppls, dtype=np.float64)
    median = float(np.median(arr))
    var = float(np.var(arr))
    low_ratio = float(np.mean(arr < low_ppl_threshold))
    if var < 1e-12 or arr.size < 3:
        sk = 0.0
    else:
        sk = float(stats.skew(arr, bias=False))
    if math.isnan(sk):
        sk = 0.0

    return {
        "mean_perplexity": mean_ppl,
        "median_perplexity": median,
        "perplexity_variance": var,
        "min_sentence_ppl": float(np.min(arr)),
        "max_sentence_ppl": float(np.max(arr)),
        "ppl_skewness": sk,
        "low_ppl_sentence_ratio": low_ratio,
    }
