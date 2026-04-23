"""Unit tests for ``_topic_entropy_lda``.

The function under test takes a corpus of raw document strings (row 0 is the
article under analysis) and returns the Shannon entropy of the fitted
per-document topic mixture for the requested row. It does NOT touch spaCy
directly — tokenization is handled internally by sklearn's
``CountVectorizer`` — so these tests seed synthetic string corpora and assert
on the returned entropy. ``spacy.load`` is still patched as a defensive
no-op so CI environments lacking ``en_core_web_md`` cannot regress into
loading the model through any transitive import.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from forensics.config.settings import AnalysisConfig
from forensics.features.content import _topic_entropy_lda


@pytest.fixture(autouse=True)
def _no_spacy_model_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent any transitive ``spacy.load`` from reaching the filesystem."""
    import spacy

    def _raise_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("spacy.load must not be called by _topic_entropy_lda")

    monkeypatch.setattr(spacy, "load", _raise_if_called)


@pytest.fixture
def analysis_cfg() -> AnalysisConfig:
    """Small component count keeps LDA fast and entropy bounds tight."""
    return AnalysisConfig(
        content_lda_n_components=3,
        content_lda_max_iter=5,
        content_lda_max_features=256,
        content_lda_max_df=1.0,
    )


_CATS = "cat kitten feline paw whiskers purr meow tail fur claw"
_SPORTS = "football goalkeeper stadium striker referee offside pitch league trophy"
_FINANCE = "stock bond dividend interest inflation yield treasury equity bear bull"


def _focused_corpus() -> list[str]:
    """Row 0 sticks to one narrow subject; peers cover distinct topics.

    With a focused row-0 document, LDA will assign most of its topic mass to
    a single component, yielding a low per-document entropy.
    """
    return [
        _CATS,
        _SPORTS,
        _SPORTS + " manager",
        _SPORTS + " coach",
        _FINANCE,
        _FINANCE + " market",
        _FINANCE + " investor",
    ]


def _scattered_corpus() -> list[str]:
    """Row 0 mixes three distinct topics; peers anchor each topic.

    A row-0 document that draws vocabulary from multiple coherent clusters
    forces LDA to spread topic mass across components, yielding higher entropy
    than a row-0 document that sits in a single cluster.
    """
    return [
        # Row 0 spans three topics in one document.
        _CATS + " " + _SPORTS + " " + _FINANCE,
        _CATS,
        _CATS + " nap",
        _SPORTS,
        _SPORTS + " manager",
        _FINANCE,
        _FINANCE + " market",
    ]


def test_focused_row_has_low_entropy(analysis_cfg: AnalysisConfig) -> None:
    entropy = _topic_entropy_lda(
        _focused_corpus(),
        topic_row=0,
        analysis=analysis_cfg,
    )
    assert math.isfinite(entropy)
    assert entropy >= 0.0
    # Max possible entropy for k=3 topics is log2(3) ≈ 1.585. A document
    # anchored to one topic should land well below that ceiling.
    assert entropy < math.log2(analysis_cfg.content_lda_n_components)


def test_scattered_row_has_higher_entropy_than_focused_row(
    analysis_cfg: AnalysisConfig,
) -> None:
    focused = _topic_entropy_lda(
        _focused_corpus(),
        topic_row=0,
        analysis=analysis_cfg,
    )
    scattered = _topic_entropy_lda(
        _scattered_corpus(),
        topic_row=0,
        analysis=analysis_cfg,
    )
    assert math.isfinite(focused)
    assert math.isfinite(scattered)
    assert scattered > focused


def test_empty_corpus_returns_nan(analysis_cfg: AnalysisConfig) -> None:
    result = _topic_entropy_lda([], topic_row=0, analysis=analysis_cfg)
    assert math.isnan(result)


def test_single_document_corpus_returns_nan(analysis_cfg: AnalysisConfig) -> None:
    result = _topic_entropy_lda(
        ["just one document about cats"],
        topic_row=0,
        analysis=analysis_cfg,
    )
    assert math.isnan(result)


def test_two_document_corpus_returns_nan(analysis_cfg: AnalysisConfig) -> None:
    # Guard clause requires at least 3 docs.
    result = _topic_entropy_lda(
        ["doc one about cats", "doc two about dogs"],
        topic_row=0,
        analysis=analysis_cfg,
    )
    assert math.isnan(result)


def test_identical_documents_yield_low_entropy(analysis_cfg: AnalysisConfig) -> None:
    docs = ["cat kitten feline paw whiskers purr"] * 6
    entropy = _topic_entropy_lda(docs, topic_row=0, analysis=analysis_cfg)
    assert math.isfinite(entropy)
    assert entropy >= 0.0
    # Identical docs can't disambiguate topics, so the mixture should stay
    # well under the uniform ceiling of log2(k).
    assert entropy < math.log2(analysis_cfg.content_lda_n_components)


def test_topic_row_out_of_range_returns_nan(analysis_cfg: AnalysisConfig) -> None:
    result = _topic_entropy_lda(
        _focused_corpus(),
        topic_row=999,
        analysis=analysis_cfg,
    )
    assert math.isnan(result)


def test_corpus_with_no_vocabulary_returns_nan(analysis_cfg: AnalysisConfig) -> None:
    # ``CountVectorizer`` strips 1-char tokens by default, leaving no features.
    result = _topic_entropy_lda(
        ["a", "b", "c", "d"],
        topic_row=0,
        analysis=analysis_cfg,
    )
    assert math.isnan(result)


def test_deterministic_across_runs(analysis_cfg: AnalysisConfig) -> None:
    docs = _focused_corpus()
    first = _topic_entropy_lda(docs, topic_row=0, analysis=analysis_cfg)
    second = _topic_entropy_lda(docs, topic_row=0, analysis=analysis_cfg)
    assert first == pytest.approx(second)
