"""Strict vs lenient JSON decode for flat dict feature columns."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from forensics.models.features import (
    STRICT_DECODE_CTX,
    FeatureVector,
    strict_feature_decode_confirmatory,
)


def test_lenient_corrupt_json_warns_and_empty_dict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = {
        "article_id": "a1",
        "author_id": "b1",
        "timestamp": datetime(2024, 1, 1, tzinfo=UTC).isoformat(),
        "function_word_distribution": "{not-json",
    }
    with caplog.at_level(logging.WARNING):
        fv = FeatureVector.model_validate(payload)
    assert fv.lexical.function_word_distribution == {}
    assert any("feature dict field JSON decode failed" in r.message for r in caplog.records), (
        caplog.text
    )


def test_lenient_non_dict_json_warns_and_empty_dict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = {
        "article_id": "a2",
        "author_id": "b2",
        "timestamp": datetime(2024, 1, 2, tzinfo=UTC).isoformat(),
        "punctuation_profile": "[1, 2, 3]",
    }
    with caplog.at_level(logging.WARNING):
        fv = FeatureVector.model_validate(payload)
    assert fv.structural.punctuation_profile == {}
    assert any("decoded to non-dict" in r.message for r in caplog.records), caplog.text


def test_corrupt_dict_json_strict_context_raises() -> None:
    payload = {
        "article_id": "a3",
        "author_id": "b3",
        "timestamp": datetime(2024, 1, 3, tzinfo=UTC).isoformat(),
        "function_word_distribution": "{bad",
    }
    with (
        strict_feature_decode_confirmatory(exploratory=False),
        pytest.raises(ValueError, match="invalid JSON"),
    ):
        FeatureVector.model_validate(payload)


def test_non_dict_json_strict_context_raises() -> None:
    payload = {
        "article_id": "a4",
        "author_id": "b4",
        "timestamp": datetime(2024, 1, 4, tzinfo=UTC).isoformat(),
        "clause_initial_top10": "42",
    }
    with (
        strict_feature_decode_confirmatory(exploratory=False),
        pytest.raises(ValueError, match="must be an object"),
    ):
        FeatureVector.model_validate(payload)


def test_exploratory_disables_strict_even_with_manager() -> None:
    """``exploratory=True`` keeps lenient decode inside the orchestrator scope."""
    payload = {
        "article_id": "a5",
        "author_id": "b5",
        "timestamp": datetime(2024, 1, 5, tzinfo=UTC).isoformat(),
        "function_word_distribution": "{bad",
    }
    with strict_feature_decode_confirmatory(exploratory=True):
        fv = FeatureVector.model_validate(payload)
    assert fv.lexical.function_word_distribution == {}


def test_strict_decode_ctx_explicit_set_raises() -> None:
    payload = {
        "article_id": "a6",
        "author_id": "b6",
        "timestamp": datetime(2024, 1, 6, tzinfo=UTC).isoformat(),
        "pos_bigram_top30": "null",
    }
    token = STRICT_DECODE_CTX.set(True)
    try:
        with pytest.raises(ValueError, match="must be an object"):
            FeatureVector.model_validate(payload)
    finally:
        STRICT_DECODE_CTX.reset(token)
