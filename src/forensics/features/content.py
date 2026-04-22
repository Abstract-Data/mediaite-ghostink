"""Content and topic feature extractors (Phase 4)."""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from typing import Any, Final

import numpy as np
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from spacy.tokens import Doc

from forensics.config.settings import AnalysisConfig

# Self-similarity requires a minimum peer set; fewer peers yields noisy or
# degenerate cosine scores that harm downstream convergence detection.
MIN_PEERS_FOR_SIMILARITY: Final[int] = 5


def _shannon_bigrams_trigrams(words: list[str]) -> tuple[float, float]:
    def entropy_ngrams(n: int) -> float:
        if len(words) < n:
            return float("nan")
        grams: list[str] = []
        for i in range(len(words) - n + 1):
            grams.append("_".join(words[i : i + n]))
        c = Counter(grams)
        tot = sum(c.values())
        h = 0.0
        for v in c.values():
            p = v / tot
            h -= p * math.log2(p)
        return h

    return entropy_ngrams(2), entropy_ngrams(3)


@lru_cache(maxsize=256)
def _self_similarity_cached(current: str, peers: tuple[str, ...]) -> float:
    """TF-IDF mean cosine sim of ``current`` to each peer; peers key must be hashable."""
    if not peers:
        return 0.0
    # Fresh vectorizer per compute: ``fit_transform`` mutates state; safe under concurrency.
    vec = TfidfVectorizer(max_features=4096, min_df=1)
    mat = vec.fit_transform([current, *peers])
    sims = cosine_similarity(mat[0:1], mat[1:])[0]
    return float(sims.mean())


def _self_similarity(current: str, peers: list[str]) -> float | None:
    """TF-IDF cosine similarity of ``current`` vs ``peers``.

    Returns ``None`` when fewer than :data:`MIN_PEERS_FOR_SIMILARITY` usable
    peers are available — early-career authors lack the peer history needed
    for a meaningful self-similarity signal.
    """
    usable = [p for p in peers if p and p.strip()]
    if len(usable) < MIN_PEERS_FOR_SIMILARITY:
        return None
    return _self_similarity_cached(current, tuple(usable))


def _nonempty_stripped(texts: list[str]) -> list[str]:
    return [t.strip() for t in texts if t and t.strip()]


def _truncate_for_lda(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars]


def _lda_document_corpus(
    current: str,
    peers: list[str],
    *,
    max_peer_documents: int,
    max_chars_per_document: int,
) -> list[str]:
    """Current article plus recent peers, capped for cost and memory (row 0 = current)."""
    head = _truncate_for_lda(current.strip(), max_chars_per_document)
    if not head:
        return []
    tail_src = _nonempty_stripped(peers)
    if max_peer_documents > 0 and len(tail_src) > max_peer_documents:
        tail_src = tail_src[-max_peer_documents:]
    tail = [_truncate_for_lda(p, max_chars_per_document) for p in tail_src]
    tail = [p for p in tail if p]
    return [head, *tail]


def _discrete_distribution_entropy(dist: np.ndarray) -> float:
    s = float(dist.sum())
    if s <= 0:
        return float("nan")
    p = dist / s
    return float(-sum(float(x) * math.log2(float(x)) for x in p if x > 0))


_OPENING_PATTERNS = (
    re.compile(r"\bin a recent\b", re.I),
    re.compile(r"\bas .{1,40}? reported\b", re.I),
    re.compile(r"\btime will tell\b", re.I),
    re.compile(r"\baccording to reports\b", re.I),
    re.compile(r"\bit remains to be seen\b", re.I),
)

_CLOSING_PATTERNS = (
    re.compile(r"\bonly time will tell\b", re.I),
    re.compile(r"\bwe will keep you updated\b", re.I),
    re.compile(r"\bstay tuned\b", re.I),
)

_FIRST_PERSON = re.compile(
    r"\b(i|me|my|mine|we|us|our|ours)\b",
    re.I,
)

_HEDGES = (
    "perhaps",
    "might",
    "could be argued",
    "it seems",
    "appears to",
    "likely",
    "possibly",
    "it is possible",
    "one could argue",
    "to some extent",
)


def _formula_score(lower: str, patterns: tuple[re.Pattern[str], ...]) -> float:
    hits = sum(1 for p in patterns if p.search(lower))
    return min(1.0, hits / max(1, len(patterns)))


def _first_person_ratio(lower: str, n_words: int) -> float:
    return len(_FIRST_PERSON.findall(lower)) / max(1, n_words)


def _hedging_frequency(lower: str, n_sents: int) -> float:
    hedge_hits = sum(lower.count(h) for h in _HEDGES)
    return hedge_hits / max(1, n_sents)


def _topic_entropy_lda(
    docs: list[str],
    *,
    topic_row: int,
    analysis: AnalysisConfig,
) -> float:
    """Fit LDA on ``docs`` and return Shannon entropy of the topic mixture for row ``topic_row``."""
    if len(docs) < 3:
        return float("nan")
    k = analysis.content_lda_n_components
    k_eff = min(k, max(2, len(docs) - 1))
    try:
        vec = CountVectorizer(
            max_features=analysis.content_lda_max_features,
            min_df=1,
            max_df=analysis.content_lda_max_df,
        )
        X = vec.fit_transform(docs)
        if X.shape[0] < 2 or X.shape[1] < 2:
            return float("nan")
        lda = LatentDirichletAllocation(
            n_components=k_eff,
            max_iter=analysis.content_lda_max_iter,
            learning_method="online",
            random_state=42,
        )
        dist = lda.fit_transform(X)
        if topic_row >= dist.shape[0]:
            return float("nan")
        return _discrete_distribution_entropy(dist[topic_row])
    except ValueError:
        return float("nan")


def extract_content_features(
    text: str,
    doc: Doc,
    recent_texts_30d: list[str],
    recent_texts_90d: list[str],
    *,
    analysis: AnalysisConfig | None = None,
) -> dict[str, Any]:
    """Content, repetition, and light topic features."""
    cfg = analysis or AnalysisConfig()
    words = [t.text.lower() for t in doc if t.is_alpha]
    bi, tri = _shannon_bigrams_trigrams(words)

    sim30 = _self_similarity(text, recent_texts_30d)
    sim90 = _self_similarity(text, recent_texts_90d)

    # LDA: row 0 is the article under analysis; peers are capped for perf/scale.
    lda_docs = _lda_document_corpus(
        text,
        recent_texts_90d,
        max_peer_documents=cfg.content_lda_max_peer_documents,
        max_chars_per_document=cfg.content_lda_max_chars_per_document,
    )
    topic_div = _topic_entropy_lda(lda_docs, topic_row=0, analysis=cfg)

    sents = list(doc.sents)
    n_words = len(words) or 1
    n_sents = len(sents) or 1

    lower = text.lower()
    open_score = _formula_score(lower, _OPENING_PATTERNS)
    close_score = _formula_score(lower, _CLOSING_PATTERNS)
    first_person = _first_person_ratio(lower, n_words)
    hedging = _hedging_frequency(lower, n_sents)

    return {
        "bigram_entropy": bi,
        "trigram_entropy": tri,
        # ``self_similarity_*`` may be ``None`` when peer set is smaller than
        # ``MIN_PEERS_FOR_SIMILARITY`` — downstream code must treat as null.
        "self_similarity_30d": sim30,
        "self_similarity_90d": sim90,
        "topic_diversity_score": topic_div,
        "formula_opening_score": open_score,
        "formula_closing_score": close_score,
        "first_person_ratio": first_person,
        "hedging_frequency": hedging,
    }
