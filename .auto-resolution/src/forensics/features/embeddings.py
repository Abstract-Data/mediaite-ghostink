"""Sentence-transformer embeddings (Phase 4)."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, Any] = {}


def _get_model(model_name: str) -> Any:
    if model_name not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformer model: %s", model_name)
        _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _MODEL_CACHE[model_name]


def clear_model_cache() -> None:
    """Drop cached models (tests)."""
    _MODEL_CACHE.clear()


def compute_embedding(text: str, model_name: str) -> np.ndarray:
    """Return a dense embedding vector for ``text``."""
    model = _get_model(model_name)
    vec = model.encode(text or "", show_progress_bar=False)
    return np.asarray(vec, dtype=np.float32)
