"""Topic-stratified sampling for Phase 10 baseline generation (LDA on author corpus)."""

from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path

from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import TfidfVectorizer

from forensics.config.settings import ForensicsSettings
from forensics.storage.repository import Repository


def extract_lda_topic_keywords(
    texts: list[str],
    *,
    num_topics: int = 20,
    n_keywords: int = 10,
    random_state: int = 42,
) -> list[tuple[int, list[str], str]]:
    """Fit LDA on TF-IDF corpus; return ``(topic_id, keywords, summary)`` per topic."""
    if not texts:
        return []
    n_samples = len(texts)
    max_features = min(5000, max(100, n_samples * 10))
    vectorizer = TfidfVectorizer(
        max_df=0.95,
        min_df=max(1, min(2, n_samples // 5)),
        max_features=max_features,
        stop_words="english",
    )
    X = vectorizer.fit_transform(texts)
    n_topics_eff = max(2, min(num_topics, max(2, X.shape[0] // 5)))
    lda = LatentDirichletAllocation(
        n_components=n_topics_eff,
        random_state=random_state,
        max_iter=30,
        learning_method="online",
    )
    lda.fit(X)
    names = vectorizer.get_feature_names_out()
    topics: list[tuple[int, list[str], str]] = []
    for topic_idx, topic in enumerate(lda.components_):
        top_ix = topic.argsort()[: -n_keywords - 1 : -1]
        kws = [str(names[i]) for i in top_ix]
        summary = ", ".join(kws[:5])
        topics.append((topic_idx, kws, summary))
    return topics


def sample_topic_keywords(
    db_path: Path,
    author_slug: str,
    *,
    settings: ForensicsSettings | None = None,
    num_topics: int | None = None,
    n_keywords: int | None = None,
    random_state: int = 42,
) -> list[list[str]]:
    """Return one keyword-list per LDA topic for this author's corpus.

    ``num_topics`` / ``n_keywords`` are resolved from ``settings.analysis`` when omitted.
    """
    if settings is None:
        from forensics.config import get_settings

        settings = get_settings()
    lda_cfg = settings.analysis.content_lda
    n_topics = num_topics if num_topics is not None else lda_cfg.lda_num_topics
    n_kw = n_keywords if n_keywords is not None else lda_cfg.lda_n_keywords
    with Repository(db_path) as repo:
        author = repo.get_author_by_slug(author_slug)
        if author is None:
            raise ValueError(f"Unknown author slug: {author_slug}")
        articles = repo.get_articles_by_author(author.id)
    texts = [a.clean_text for a in articles if a.clean_text and not a.is_duplicate]
    if len(texts) < 5:
        raise ValueError(f"Need ≥5 articles for LDA topics (got {len(texts)} for {author_slug})")
    topics = extract_lda_topic_keywords(
        texts,
        num_topics=n_topics,
        n_keywords=n_kw,
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
    with Repository(db_path) as repo:
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
