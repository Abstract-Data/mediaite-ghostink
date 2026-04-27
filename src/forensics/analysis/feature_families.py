"""Feature-family registry for convergence-ratio over PELT axes (not raw columns).

Six families avoid double-counting correlated readability/lexical blocks.
Issue #5: former single-member ``voice`` and ``paragraph_shape`` capped windows
at 6/8 (~89.8% of windows); ``first_person_ratio`` merges into ``ai_markers``,
``paragraph_length_variance`` into ``sentence_structure``, for a 6/6 ceiling.
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
