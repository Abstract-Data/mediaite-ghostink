"""Sentence-transformer embeddings (Phase 4)."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from forensics.utils.model_cache import KeyedModelCache

logger = logging.getLogger(__name__)

_ST_MODEL_CACHE = KeyedModelCache()


def _get_model(model_name: str, revision: str) -> Any:
    cache_key = f"{model_name}@{revision}"

    def load() -> Any:
        from sentence_transformers import SentenceTransformer

        logger.info(
            "Loading sentence-transformer model: %s (revision=%s)",
            model_name,
            revision,
        )
        return SentenceTransformer(model_name, revision=revision or None)

    return _ST_MODEL_CACHE.get_or_load(cache_key, load)


def clear_model_cache() -> None:
    """Drop cached models (tests)."""
    _ST_MODEL_CACHE.clear()


def compute_embedding(text: str, model_name: str, revision: str) -> np.ndarray:
    """Return a dense embedding vector for ``text``.

    ``revision`` is the Hugging Face revision (commit SHA or branch) passed to
    :class:`sentence_transformers.SentenceTransformer` and must match
    ``settings.analysis.embedding_model_revision`` for reproducible analysis.
    """
    model = _get_model(model_name, revision)
    vec = model.encode(text or "", show_progress_bar=False)
    return np.asarray(vec, dtype=np.float32)
