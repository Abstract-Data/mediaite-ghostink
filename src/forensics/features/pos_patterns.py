"""POS bigram and dependency-shape features."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from spacy.tokens import Doc, Span


def _token_depth_to_root(token: Any) -> int:
    depth = 0
    t = token
    seen = 0
    while t.head is not t and seen < 1000:
        depth += 1
        t = t.head
        seen += 1
    return depth


def max_dep_depth_sentence(sent: Span) -> int:
    """Maximum dependency depth in a sentence (longest path from any token toward root)."""
    if not len(sent):
        return 0
    return max(_token_depth_to_root(t) for t in sent)


def dep_depth_per_sentence(doc: Doc) -> list[float]:
    return [float(max_dep_depth_sentence(sent)) for sent in doc.sents]


def _entropy_from_counts(counter: Counter[str], total: int) -> float:
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counter.values():
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log2(p)
    return h


def extract_pos_pattern_features(doc: Doc) -> dict[str, Any]:
    """POS bigrams, clause-initial patterns, and dependency depth stats."""
    bigrams: list[str] = []
    for i in range(len(doc) - 1):
        a, b = doc[i], doc[i + 1]
        if a.is_punct or b.is_punct:
            continue
        bigrams.append(f"{a.pos_}_{b.pos_}")
    bc = Counter(bigrams)
    big_total = sum(bc.values())
    pos_bigram_top30: dict[str, float] = {}
    if big_total:
        top = bc.most_common(30)
        pos_bigram_top30 = {k: v / big_total for k, v in top}

    opening_counter: Counter[str] = Counter()
    for sent in doc.sents:
        toks = [t for t in sent if not t.is_space]
        if len(toks) < 3:
            continue
        pat = "_".join(toks[i].pos_ for i in range(3))
        opening_counter[pat] += 1

    open_total = sum(opening_counter.values())
    clause_initial_entropy = _entropy_from_counts(opening_counter, open_total)
    clause_initial_top10: dict[str, float] = {}
    if open_total:
        clause_initial_top10 = {k: v / open_total for k, v in opening_counter.most_common(10)}

    depths = dep_depth_per_sentence(doc)
    if depths:
        mean_d = sum(depths) / len(depths)
        var = sum((d - mean_d) ** 2 for d in depths) / len(depths)
        std_d = math.sqrt(var)
        max_d = max(depths)
    else:
        mean_d = std_d = max_d = 0.0

    return {
        "pos_bigram_top30": pos_bigram_top30,
        "clause_initial_entropy": clause_initial_entropy,
        "clause_initial_top10": clause_initial_top10,
        "dep_depth_mean": mean_d,
        "dep_depth_std": std_d,
        "dep_depth_max": max_d,
    }
