"""Match synthetic article lengths to the author's empirical distribution."""

from __future__ import annotations

import polars as pl


def sample_word_counts(author_articles: pl.DataFrame, n: int, *, seed: int = 42) -> list[int]:
    """Sample word counts with replacement from ``author_articles.word_count``."""
    if "word_count" not in author_articles.columns:
        msg = "author_articles must include a word_count column"
        raise ValueError(msg)
    if author_articles.height == 0:
        return [600] * n
    return (
        author_articles.select("word_count")
        .sample(n=n, with_replacement=True, seed=seed)
        .to_series()
        .to_list()
    )
