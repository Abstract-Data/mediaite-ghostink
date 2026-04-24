"""Lexical feature extractors (Phase 4)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from spacy.tokens import Doc

# Top-50 function words (order stable for reproducible dict keys).
FUNCTION_WORDS: tuple[str, ...] = (
    "the",
    "a",
    "is",
    "of",
    "and",
    "to",
    "in",
    "that",
    "it",
    "for",
    "was",
    "on",
    "are",
    "with",
    "as",
    "at",
    "be",
    "this",
    "have",
    "from",
    "by",
    "not",
    "but",
    "what",
    "all",
    "were",
    "when",
    "we",
    "there",
    "can",
    "an",
    "your",
    "which",
    "their",
    "if",
    "do",
    "will",
    "each",
    "about",
    "how",
    "up",
    "out",
    "them",
    "then",
    "she",
    "many",
    "some",
    "so",
    "these",
    "would",
)

# Phrases or patterns (case-insensitive). ``*`` matches non-empty run within phrase.
_AI_MARKER_SPECS: tuple[str, ...] = (
    "it's important to note",
    "it's worth noting",
    "delve",
    "in today's * landscape",
    "navigate",
    "underscores",
    "arguably",
    "at its core",
    "a testament to",
    "in an era of",
    "serves as a",
    "plays a crucial role",
    "it should be noted",
    "represents a significant",
    "offers a unique",
    "is a game-changer",
)


def _compile_ai_marker_patterns() -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for spec in _AI_MARKER_SPECS:
        if "*" in spec:
            parts = [re.escape(p) for p in spec.split("*")]
            body = r".+?".join(parts)
        else:
            body = re.escape(spec)
        patterns.append(re.compile(rf"\b{body}\b", re.IGNORECASE))
    return patterns


_AI_MARKER_PATTERNS = _compile_ai_marker_patterns()


def _alphabetic_words(doc: Doc) -> list[str]:
    return [t.text.lower() for t in doc if t.is_alpha]


def _ttr(words: list[str]) -> float:
    if not words:
        return float("nan")
    return len(set(words)) / len(words)


def _mattr(words: list[str], window: int = 50) -> float:
    if not words:
        return float("nan")
    if len(words) <= window:
        return _ttr(words)
    ratios = [_ttr(words[i : i + window]) for i in range(len(words) - window + 1)]
    return sum(ratios) / len(ratios)


def _hapax_ratio(words: list[str]) -> float:
    """Hapax ratio = (# tokens that appear exactly once) / (# total tokens).

    Uses token-denominator (not type-denominator) so the value scales with
    sparsity of the distribution: purely repetitive text → 0, purely unique
    vocabulary → 1. Downstream changepoint code relies on this ordering.
    """
    if not words:
        return float("nan")
    counts = Counter(words)
    hapax = sum(1 for c in counts.values() if c == 1)
    return hapax / len(words)


def _yules_k(words: list[str]) -> float:
    """Yule's K from frequency spectrum (types by token frequency)."""
    if not words:
        return float("nan")
    counts = Counter(words)
    n_tokens = len(words)
    if n_tokens < 2:
        return float("nan")
    spectrum = Counter(counts.values())
    m2 = sum((r**2) * nr for r, nr in spectrum.items())
    return 1e4 * (m2 - n_tokens) / (n_tokens**2)


def _simpsons_d(words: list[str]) -> float:
    if not words:
        return float("nan")
    counts = Counter(words)
    n = len(words)
    if n < 2:
        return float("nan")
    numer = sum(c * (c - 1) for c in counts.values())
    return numer / (n * (n - 1))


def _ai_marker_frequency(text: str, doc: Doc) -> float:
    n_sents = len(list(doc.sents)) or 1
    total = 0
    lower = text.lower()
    for pat in _AI_MARKER_PATTERNS:
        total += len(pat.findall(lower))
    return total / n_sents


def _function_word_distribution(doc: Doc) -> dict[str, float]:
    counts = Counter(t.text.lower() for t in doc if t.is_alpha)
    total = sum(counts[w] for w in FUNCTION_WORDS)
    if total == 0:
        return {w: 0.0 for w in FUNCTION_WORDS}
    return {w: counts[w] / total for w in FUNCTION_WORDS}


def extract_lexical_features(text: str, doc: Doc) -> dict[str, Any]:
    """Compute lexical fingerprint features for one article."""
    words = _alphabetic_words(doc)
    return {
        "ttr": _ttr(words),
        "mattr": _mattr(words, window=50),
        "hapax_ratio": _hapax_ratio(words),
        "yules_k": _yules_k(words),
        "simpsons_d": _simpsons_d(words),
        "ai_marker_frequency": _ai_marker_frequency(text, doc),
        "function_word_distribution": _function_word_distribution(doc),
    }
