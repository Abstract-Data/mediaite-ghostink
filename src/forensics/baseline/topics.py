"""Topic-stratified sampling for Phase 10 baseline generation.

Reuses ``extract_lda_topic_keywords`` from the drift analysis module to keep
the LDA fit identical to what's used in Phase 6.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path

from forensics.analysis.drift import extract_lda_topic_keywords
from forensics.storage.repository import Repository


def sample_topic_keywords(
    db_path: Path,
    author_slug: str,
    *,
    num_topics: int = 20,
    n_keywords: int = 10,
    random_state: int = 42,
) -> list[list[str]]:
    """Return one keyword-list per LDA topic for this author's corpus."""
    repo = Repository(db_path)
    author = repo.get_author_by_slug(author_slug)
    if author is None:
        raise ValueError(f"Unknown author slug: {author_slug}")
    articles = repo.get_articles_by_author(author.id)
    texts = [a.clean_text for a in articles if a.clean_text and not a.is_duplicate]
    if len(texts) < 5:
        raise ValueError(f"Need ≥5 articles for LDA topics (got {len(texts)} for {author_slug})")
    topics = extract_lda_topic_keywords(
        texts,
        num_topics=num_topics,
        n_keywords=n_keywords,
        random_state=random_state,
    )
    return [keywords for _idx, keywords, _summary in topics]


def sample_word_counts(
    db_path: Path,
    author_slug: str,
    n: int,
    *,
    seed: int = 42,
) -> list[int]:
    """Sample target word counts from the author's historical distribution."""
    repo = Repository(db_path)
    author = repo.get_author_by_slug(author_slug)
    if author is None:
        raise ValueError(f"Unknown author slug: {author_slug}")
    counts = [
        a.word_count
        for a in repo.get_articles_by_author(author.id)
        if a.clean_text and a.word_count > 0
    ]
    if not counts:
        return [600] * n
    rng = random.Random(seed)
    return [rng.choice(counts) for _ in range(n)]


def cycle_keywords(keywords: Sequence[list[str]], n: int) -> list[list[str]]:
    """Deterministic round-robin of keyword lists — used when topic counts don't match n."""
    if not keywords:
        return [["politics", "news"] for _ in range(n)]
    return [list(keywords[i % len(keywords)]) for i in range(n)]
