"""Unit tests for ``_score_author_articles`` (C2 extraction)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import MagicMock

from forensics.config.settings import ProbabilityConfig
from forensics.features.probability_pipeline import _score_author_articles
from forensics.models.article import Article
from forensics.models.author import Author


def _author() -> Author:
    return Author(
        id="author-abc",
        name="Test Author",
        slug="test-author",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2024, 1, 1),
        baseline_end=date(2024, 6, 30),
        archive_url="https://www.mediaite.com/author/test-author/",
    )


def _article(i: int) -> Article:
    return Article(
        id=f"article-{i}",
        author_id="author-abc",
        url=f"https://www.mediaite.com/post-{i}/",  # type: ignore[arg-type]
        title=f"Post {i}",
        published_date=datetime(2024, 3, 1, tzinfo=UTC),
        clean_text=f"Article body {i} contains some sample text for scoring.",
        word_count=50,
        metadata={},
        content_hash=f"hash-{i}",
    )


def _ppl_stub() -> dict[str, float]:
    return {
        "mean_perplexity": 25.0,
        "median_perplexity": 20.0,
        "perplexity_variance": 1.5,
        "min_sentence_ppl": 10.0,
        "max_sentence_ppl": 40.0,
        "ppl_skewness": 0.2,
        "low_ppl_sentence_ratio": 0.1,
    }


def test_score_author_articles_without_binoculars(monkeypatch) -> None:
    """binoc=None → rows are written; binoculars_score is None."""
    called = {"ppl": 0, "bino": 0}

    def fake_perplexity(text: str, *_a: Any, **_kw: Any) -> dict[str, float]:
        called["ppl"] += 1
        return _ppl_stub()

    monkeypatch.setattr(
        "forensics.features.probability_pipeline.compute_perplexity", fake_perplexity
    )

    cfg = ProbabilityConfig()
    rows = _score_author_articles(
        _author(),
        [_article(1), _article(2)],
        model=MagicMock(),
        tokenizer=MagicMock(),
        binoc=None,
        cfg=cfg,
    )
    assert len(rows) == 2
    assert called["ppl"] == 2
    assert called["bino"] == 0
    for row in rows:
        assert row["binoculars_score"] is None
        assert row["mean_perplexity"] == 25.0
        assert row["author_id"] == "author-abc"


def test_score_author_articles_with_binoculars(monkeypatch) -> None:
    """binoc tuple present → binoculars_score populated."""
    monkeypatch.setattr(
        "forensics.features.probability_pipeline.compute_perplexity",
        lambda *_a, **_kw: _ppl_stub(),
    )
    monkeypatch.setattr(
        "forensics.features.probability_pipeline.compute_binoculars_score",
        lambda *_a, **_kw: 0.85,
    )

    cfg = ProbabilityConfig()
    rows = _score_author_articles(
        _author(),
        [_article(1)],
        model=MagicMock(),
        tokenizer=MagicMock(),
        binoc=(MagicMock(), MagicMock(), MagicMock()),
        cfg=cfg,
    )
    assert rows[0]["binoculars_score"] == 0.85


def test_score_author_articles_empty_list() -> None:
    cfg = ProbabilityConfig()
    rows = _score_author_articles(
        _author(),
        [],
        model=MagicMock(),
        tokenizer=MagicMock(),
        binoc=None,
        cfg=cfg,
    )
    assert rows == []
