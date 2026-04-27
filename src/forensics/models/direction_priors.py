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

Lives under ``forensics.models`` (not ``forensics.analysis``) so
:mod:`forensics.models.report` can import priors without executing
``forensics.analysis``'s orchestrator barrel (circular import).
"""

from __future__ import annotations

import math
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

# Human-readable audit trail for reviewers; keys must match ``AI_TYPICAL_DIRECTION``.
AI_TYPICAL_DIRECTION_RATIONALE: dict[str, str] = {
    "ai_marker_frequency": (
        "LLM prose often overuses discourse markers and templated openers vs human news copy."
    ),
    "formula_opening_score": (
        "Scaffolded openings (thesis-style framing) are more common in model-assisted drafts."
    ),
    "coleman_liau": ("LLM outputs skew toward higher grade-level / formal register on average."),
    "gunning_fog": (
        "Same readability axis as Coleman-Liau: elevated complexity vs typical "
        "wire-style human copy."
    ),
    "flesch_kincaid": (
        "Flesch-Kincaid grade rises with syntactic complexity; LLM baselines trend higher here."
    ),
    "bigram_entropy": (
        "LLM text often concentrates on high-probability bigrams, lowering sequence entropy."
    ),
    "trigram_entropy": "Same mechanism as bigram entropy at the trigram level.",
    "ttr": (
        "Type-token ratio tends to fall when vocabulary is drawn from a narrower generative mode."
    ),
    "lexical_diversity": (
        "Composite lexical-diversity label tracks the same contraction as raw TTR-style signals."
    ),
    "sent_length_std": (
        "More uniform sentence lengths (lower std) are typical of templated LLM pacing."
    ),
    "sent_length_skewness": (
        "Reduced skew reflects less idiosyncratic tail behavior vs human-authored variance."
    ),
    "sent_length_mean": "Mean sentence length often drifts upward under model drafting habits.",
    "self_similarity_30d": (
        "Short-window self-similarity rises when phrasing repeats across adjacent chunks."
    ),
    "self_similarity_90d": (
        "Longer-window repetition also elevates under internally homogeneous LLM corpora."
    ),
    "conjunction_freq": (
        "Higher function-word / connector density aligns with explanatory LLM register."
    ),
    "hedging_frequency": (
        "mixed evidence — corpus-dependent; no committed AI-typical sign for this feature."
    ),
}


def direction_from_d(cohens_d: float | None) -> Direction | None:
    """Map a signed Cohen's d to 'increase' / 'decrease' / None."""
    if cohens_d is None:
        return None
    try:
        if math.isnan(cohens_d):
            return None
        if cohens_d > 0:
            return "increase"
        if cohens_d < 0:
            return "decrease"
    except TypeError:
        return None
    return None
