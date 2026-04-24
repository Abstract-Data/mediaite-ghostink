"""Feature-family registry for convergence-ratio computation (Phase 15 B1).

Groups the 23 features in PELT_FEATURE_COLUMNS (analysis/changepoint.py) into
6 independent axes. Computing convergence ratio over families rather than
raw features prevents double-counting the 3 correlated readability features
and the 5 correlated lexical-richness features.

Phase 15 B-followup (issue #5): the original v0.4.0 design carried two
single-member families — ``voice`` (``first_person_ratio``) and
``paragraph_shape`` (``paragraph_length_variance``) — that almost never
co-fired with the other six. Empirically those two families capped 89.8 %
of windows at a 6/8 = 0.75 convergence ratio, so no real-world window
could ever clear 7/8. We fold each single-member feature into its closest
multi-member relative:

* ``first_person_ratio`` → ``ai_markers`` — first-person suppression is
  one of the register markers AI tools systematically affect (alongside
  hedging and formula openings).
* ``paragraph_length_variance`` → ``sentence_structure`` — paragraph
  shape is structural variance at the same syntactic level the rest of
  the family already measures (sentence length, clause depth).

The new family count is 6, so the theoretical ceiling for
``convergence_ratio`` becomes 1.00 (6/6) instead of 0.75 (6/8).
"""

from __future__ import annotations

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS

FEATURE_FAMILIES: dict[str, str] = {
    # Lexical richness
    "ttr": "lexical_richness",
    "mattr": "lexical_richness",
    "hapax_ratio": "lexical_richness",
    "yules_k": "lexical_richness",
    "simpsons_d": "lexical_richness",
    # Readability
    "flesch_kincaid": "readability",
    "coleman_liau": "readability",
    "gunning_fog": "readability",
    # Sentence structure (incl. paragraph_length_variance — structural variance)
    "sent_length_mean": "sentence_structure",
    "sent_length_std": "sentence_structure",
    "sent_length_skewness": "sentence_structure",
    "subordinate_clause_depth": "sentence_structure",
    "conjunction_freq": "sentence_structure",
    "passive_voice_ratio": "sentence_structure",
    "paragraph_length_variance": "sentence_structure",
    # Entropy
    "bigram_entropy": "entropy",
    "trigram_entropy": "entropy",
    # Self-similarity
    "self_similarity_30d": "self_similarity",
    "self_similarity_90d": "self_similarity",
    # AI / formula / voice register markers
    "ai_marker_frequency": "ai_markers",
    "formula_opening_score": "ai_markers",
    "hedging_frequency": "ai_markers",
    "first_person_ratio": "ai_markers",
}

FAMILY_COUNT: int = len(set(FEATURE_FAMILIES.values()))


def _assert_coverage() -> None:
    missing = set(PELT_FEATURE_COLUMNS) - set(FEATURE_FAMILIES)
    extra = set(FEATURE_FAMILIES) - set(PELT_FEATURE_COLUMNS)
    if missing:
        raise RuntimeError(
            f"FEATURE_FAMILIES is missing these PELT_FEATURE_COLUMNS entries: "
            f"{sorted(missing)}. Add them with a family label."
        )
    if extra:
        raise RuntimeError(
            f"FEATURE_FAMILIES has entries not in PELT_FEATURE_COLUMNS: {sorted(extra)}."
        )


_assert_coverage()


def family_for(feature: str) -> str:
    """Return the family label for a feature, or 'unknown' if unregistered."""
    return FEATURE_FAMILIES.get(feature, "unknown")
