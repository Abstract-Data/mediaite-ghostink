"""Binoculars-style score from a base + instruct LM pair (Phase 9)."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from forensics.config.settings import ProbabilityConfig

if TYPE_CHECKING:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

logger = logging.getLogger(__name__)


def load_binoculars_models(
    cfg: ProbabilityConfig,
    *,
    device: torch.device,
) -> tuple[AutoModelForCausalLM, AutoModelForCausalLM, AutoTokenizer] | None:
    """Load Falcon (or configured) base + instruct pair for Binoculars scoring.

    Returns ``None`` when Binoculars is disabled or when CUDA is unavailable — Falcon-7B
    is impractical on CPU for this pipeline (set ``binoculars_enabled = false`` to silence).
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not cfg.binoculars_enabled:
        return None
    if device.type != "cuda":
        logger.warning(
            "Binoculars requires GPU for reasonable performance. "
            "Skipping Falcon pair on device=%s. Set binoculars_enabled=false to silence.",
            device,
        )
        return None

    dtype = torch.float16
    tok = AutoTokenizer.from_pretrained(cfg.binoculars_model_base, revision=None)
    if tok.pad_token is None and tok.eos_token is not None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        cfg.binoculars_model_base,
        torch_dtype=dtype,
        device_map={"": device},
    )
    instruct = AutoModelForCausalLM.from_pretrained(
        cfg.binoculars_model_instruct,
        torch_dtype=dtype,
        device_map={"": device},
    )
    base.eval()
    instruct.eval()
    return base, instruct, tok


def compute_binoculars_score(
    text: str,
    model_base: AutoModelForCausalLM,
    model_instruct: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    *,
    max_length: int = 512,
    device: torch.device | None = None,
) -> float:
    """Ratio of base perplexity to instruct perplexity on the same tokenization.

    This is a **practical Binoculars-style** signal: two related LMs disagree most on
    machine-generated text when the instruct model assigns sharper probability to the
    observed continuation. The literature's full cross-perplexity mixes observer and
    performer logits; here we use the standard perplexity ratio as a stable pipeline
    approximation (always a positive float when defined).

    Lower scores suggest more ``instruct-like`` / machine-generated surface statistics
    under this pair; higher scores suggest less agreement with the instruct LM's
    preferences relative to the base LM.

    Returns:
        Positive float, or ``nan`` if undefined.
    """
    from forensics.features.probability import _resolve_max_positions, _sliding_window_mean_nll

    dev = device or next(model_base.parameters()).device
    max_length = min(max_length, _resolve_max_positions(model_base, max_length))
    enc = tokenizer(
        text,
        return_tensors="pt",
        add_special_tokens=False,
        truncation=True,
        max_length=max_length,
    )
    input_ids = enc["input_ids"].to(dev)
    if input_ids.size(1) < 2:
        return float("nan")

    stride = max(1, max_length // 2)
    sum_b, n_b = _sliding_window_mean_nll(
        model_base,
        input_ids,
        max_length=max_length,
        stride=stride,
        device=dev,
    )
    sum_i, n_i = _sliding_window_mean_nll(
        model_instruct,
        input_ids,
        max_length=max_length,
        stride=stride,
        device=dev,
    )
    if n_b <= 0 or n_i <= 0:
        return float("nan")
    ppl_b = math.exp(sum_b / n_b)
    ppl_i = math.exp(sum_i / n_i)
    if ppl_i <= 0 or math.isnan(ppl_i):
        return float("nan")
    return float(ppl_b / ppl_i)
