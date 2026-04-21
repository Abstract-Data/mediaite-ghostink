"""LDA topic stratification for baseline prompts."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import TfidfVectorizer

from forensics.storage.repository import Repository, init_db

logger = logging.getLogger(__name__)


def get_topic_distribution(
    author_slug: str,
    db_path: Path,
    *,
    num_topics: int = 20,
    n_keywords: int = 10,
    random_state: int = 42,
) -> list[dict]:
    """LDA topic mixtures over the author's corpus → weights and keyword lists.

    Returns:
        [{"topic_id": int, "keywords": list[str], "weight": float}, ...]
    """
    init_db(db_path)
    repo = Repository(db_path)
    author = repo.get_author_by_slug(author_slug)
    if author is None:
        msg = f"Unknown author slug: {author_slug}"
        raise ValueError(msg)
    corpus = repo.list_articles_for_extraction(author_id=author.id)
    texts = [a.clean_text for a in corpus if a.clean_text.strip()]
    if len(texts) < 5:
        msg = f"Need at least 5 articles with text for topic stratification (got {len(texts)})"
        raise ValueError(msg)

    n_samples = len(texts)
    max_features = min(5000, max(100, n_samples * 10))
    # Small homogeneous corpora: max_df=0.95 can drop every token; relax for short runs.
    max_df = 1.0 if n_samples < 25 else 0.95
    vectorizer = TfidfVectorizer(
        max_df=max_df,
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
    doc_topics = lda.fit_transform(X)
    mean_mix = doc_topics.mean(axis=0)
    s = float(mean_mix.sum()) or 1.0
    weights = mean_mix / s

    names = vectorizer.get_feature_names_out()
    out: list[dict] = []
    for topic_idx, topic in enumerate(lda.components_):
        top_ix = topic.argsort()[: -n_keywords - 1 : -1]
        kws = [str(names[i]) for i in top_ix]
        w = float(weights[topic_idx]) if topic_idx < len(weights) else 0.0
        out.append({"topic_id": topic_idx, "keywords": kws, "weight": w})

    out.sort(key=lambda d: d["weight"], reverse=True)
    logger.info(
        "topic distribution: author=%s topics=%d top_weight=%.3f",
        author_slug,
        len(out),
        out[0]["weight"] if out else 0.0,
    )
    return out


def sample_topic_keywords(
    topic_distribution: list[dict],
    rng: np.random.Generator,
) -> tuple[list[str], str]:
    """Sample one topic by weight; return (keywords, suggested angle summary)."""
    if not topic_distribution:
        return (
            ["politics", "washington", "congress"],
            "developments in national politics",
        )
    weights = np.asarray([max(t["weight"], 1e-9) for t in topic_distribution], dtype=np.float64)
    weights /= weights.sum()
    idx = int(rng.choice(len(topic_distribution), p=weights))
    t = topic_distribution[idx]
    kws = list(t["keywords"])[:8]
    angle = ", ".join(kws[:5])
    return kws, angle
