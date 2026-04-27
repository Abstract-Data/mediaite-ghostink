"""Empirical AI-direction priors for stylometric features.

Each entry records the direction in which a feature shift is
*consistent with* known LLM stylistic biases. Sources:
- Phase 9 perplexity literature (lower PPL = more LLM-typical).
- Phase 7 convergence design notes.
- The GPTZero / OriginalityAI / Binoculars feature-priority dossiers.
- Internal Apr 27 2026 review of LLM output corpora.

A ``None`` value means "we have no documented prior" — concordance
checks skip these features. This is intentional: we never want to
fabricate a direction for a feature without evidence.

This file should be reviewed before pre-registration lock; any
threshold or directional claim derived from it is exploratory until
the lock exists.
"""

from __future__ import annotations

from typing import Literal

Direction = Literal["increase", "decrease"]

AI_TYPICAL_DIRECTION: dict[str, Direction | None] = {
    # AI marker phrases ("delve", "in conclusion", "it's important to note")
    "ai_marker_frequency": "increase",
    "formula_opening_score": "increase",
    # Readability / formality (LLMs trend toward formal, complex prose)
    "coleman_liau": "increase",
    "gunning_fog": "increase",
    "flesch_kincaid": "increase",
    # Lexical diversity (LLMs use more common phrasing)
    "bigram_entropy": "decrease",
    "trigram_entropy": "decrease",
    "ttr": "decrease",
    "lexical_diversity": "decrease",
    # Sentence-length variation (LLMs more uniform)
    "sent_length_std": "decrease",
    "sent_length_skewness": "decrease",
    "sent_length_mean": "increase",
    # Self-similarity (LLM-assisted corpora are more internally repetitive)
    "self_similarity_30d": "increase",
    "self_similarity_90d": "increase",
    # Function-word / connector frequency
    "conjunction_freq": "increase",
    "hedging_frequency": None,  # mixed evidence — leave undocumented
}


def direction_from_d(cohens_d: float | None) -> Direction | None:
    """Map a signed Cohen's d to 'increase' / 'decrease' / None."""
    if cohens_d is None:
        return None
    try:
        if not (cohens_d == cohens_d):  # NaN check
            return None
        if cohens_d > 0:
            return "increase"
        if cohens_d < 0:
            return "decrease"
    except TypeError:
        return None
    return None
