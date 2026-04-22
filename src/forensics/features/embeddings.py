"""Sentence-transformer embeddings (Phase 4)."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from forensics.utils.model_cache import KeyedModelCache

logger = logging.getLogger(__name__)

_ST_MODEL_CACHE = KeyedModelCache()


def _get_model(model_name: str) -> Any:
    def load() -> Any:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformer model: %s", model_name)
        return SentenceTransformer(model_name)

    return _ST_MODEL_CACHE.get_or_load(model_name, load)


def clear_model_cache() -> None:
    """Drop cached models (tests)."""
    _ST_MODEL_CACHE.clear()


def compute_embedding(text: str, model_name: str) -> np.ndarray:
    """Return a dense embedding vector for ``text``."""
    model = _get_model(model_name)
    vec = model.encode(text or "", show_progress_bar=False)
    return np.asarray(vec, dtype=np.float32)
