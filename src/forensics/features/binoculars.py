"""Phase 9 — Binoculars score (Hans et al. 2024).

The Binoculars method compares perplexity of a text under a base model to the
cross-perplexity between the base and an instruct-tuned companion. Low ratios
(< ~0.9) indicate AI-generated text.
"""

from __future__ import annotations

import logging
from typing import Any

from forensics.features.probability import resolve_torch_device
from forensics.utils.model_cache import KeyedModelCache

logger = logging.getLogger(__name__)

_BINOC_PAIR_CACHE = KeyedModelCache()


def clear_pair_cache() -> None:
    _BINOC_PAIR_CACHE.clear()


def load_binoculars_models(
    base_name: str,
    instruct_name: str,
    *,
    enabled: bool = True,
    device: str | None = None,
) -> tuple[Any, Any, Any] | None:
    """Load the Binoculars base+instruct pair.

    Returns ``None`` when scoring is disabled or torch+transformers aren't
    installed. Emits a warning when falling back to CPU.
    """
    if not enabled:
        return None

    try:
        import torch  # type: ignore[import-not-found]
        from transformers import (  # type: ignore[import-not-found]
            AutoModelForCausalLM,
            AutoTokenizer,
        )
    except ImportError:
        logger.warning(
            "Binoculars unavailable: torch + transformers not installed "
            "(uv sync --extra probability)"
        )
        return None

    resolved = resolve_torch_device(device)

    if resolved == "cpu":
        logger.warning(
            "Binoculars falling back to CPU — expect ~1 article/min on 7B models. "
            "Set binoculars_enabled=false in config.toml to skip entirely."
        )

    cache_key = (base_name, instruct_name, resolved)

    def load() -> tuple[Any, Any, Any]:
        logger.info(
            "Loading Binoculars pair base=%s instruct=%s on %s",
            base_name,
            instruct_name,
            resolved,
        )
        tokenizer = AutoTokenizer.from_pretrained(base_name)
        dtype = torch.float16 if resolved == "cuda" else torch.float32
        model_base = AutoModelForCausalLM.from_pretrained(base_name, torch_dtype=dtype)
        model_inst = AutoModelForCausalLM.from_pretrained(instruct_name, torch_dtype=dtype)
        model_base.to(resolved).eval()
        model_inst.to(resolved).eval()
        return model_base, model_inst, tokenizer

    return _BINOC_PAIR_CACHE.get_or_load(cache_key, load)


def compute_binoculars_score(
    text: str,
    model_base: Any,
    model_instruct: Any,
    tokenizer: Any,
    *,
    max_length: int = 512,
) -> float:
    """Return PPL(base) / cross-PPL(base, instruct). Lower = more AI-like."""
    import torch  # type: ignore[import-not-found]

    encoded = tokenizer(
        text or "",
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
    )
    ids = encoded["input_ids"]
    device = next(model_base.parameters()).device
    ids = ids.to(device)
    if ids.size(1) < 2:
        return float("nan")

    with torch.no_grad():
        out_base = model_base(ids, labels=ids)
        out_inst = model_instruct(ids, labels=ids)

    ppl_base = float(torch.exp(out_base.loss).item())
    cross_loss = 0.5 * (out_base.loss + out_inst.loss)
    cross_ppl = float(torch.exp(cross_loss).item())
    if cross_ppl == 0.0:
        return float("nan")
    return ppl_base / cross_ppl
