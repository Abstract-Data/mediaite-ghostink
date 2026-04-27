"""Deterministic evidence-chain prose from :class:`AnalysisResult` (Phase 12 §6d).

Same inputs yield identical bytes for paste-in reports. Tone matches
preregistered hedges; no intent speculation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from forensics.analysis.feature_families import FAMILY_COUNT, FEATURE_FAMILIES
from forensics.analysis.utils import describe_velocity_acceleration_pct
from forensics.models.analysis import AnalysisResult, ConvergenceWindow
from forensics.survey.scoring import (
    SignalStrength,
    SurveyScore,
    compute_composite_score,
)

if TYPE_CHECKING:
    from forensics.paths import AnalysisArtifactPaths
    from forensics.preregistration import VerificationResult


# K6: stable diagnostic string (tests pin exact wording).
PIPELINE_B_DIAGNOSTIC_NOTE: str = (
    "Embedding drift outputs were incomplete for this author; the embedding-drift "
    "score reflects the data that were available."
)


def _preregistration_clause(verification: VerificationResult | None) -> str:
    """Return a short sentence describing the preregistration lock state.

    ``None`` means the caller did not supply verification (we do not touch
    disk from a pure-function narrative). In that case the clause is empty.
    """
    if verification is None:
        return ""
    if verification.status == "ok":
        return "The analysis thresholds in use match the pre-registered lock on file."
    if verification.status == "missing":
        return "No pre-registered threshold lock was on file when this narrative was generated."
    # mismatch
    return "The analysis thresholds in use no longer match the pre-registered lock."


def _family_representative_pairs(window: ConvergenceWindow) -> list[tuple[str, str]]:
    """Return ``[(family, representative_feature), ...]`` for family-aware narratives.

    The pipeline-A scorer in ``analysis/convergence.py`` writes one
    representative feature per family into ``features_converging`` (see
    ``_pipeline_a_from_stylometry``). Re-deriving the family-to-feature
    mapping here, rather than trusting positional alignment with
    ``families_converging``, keeps the pairing robust if either list is
    reordered or filtered downstream. Only features that map to a family
    listed in ``families_converging`` are returned.
    """
    families_in_window = set(window.families_converging)
    pairs = [
        (FEATURE_FAMILIES[feat], feat)
        for feat in window.features_converging
        if feat in FEATURE_FAMILIES and FEATURE_FAMILIES[feat] in families_in_window
    ]
    pairs.sort(key=lambda p: (p[0], p[1]))
    return pairs


def _families_convergence_sentence(window: ConvergenceWindow, author_slug: str) -> str | None:
    """Phase 15 K1 — narrative sentence keyed on ``families_converging``.

    Returns ``None`` when family-level data is absent so callers can fall back
    to the legacy feature-level sentence (older artifacts).
    """
    if not window.families_converging:
        return None
    pairs = _family_representative_pairs(window)
    if not pairs:
        return None
    family_phrase = ", ".join(f"{fam} ({feat})" for fam, feat in pairs)
    month_year = window.start_date.strftime("%b %Y")
    return (
        f"{author_slug}'s {month_year} window shows convergence across "
        f"{len(window.families_converging)} of {FAMILY_COUNT} feature families: "
        f"{family_phrase}."
    )


def _legacy_convergence_sentence(window: ConvergenceWindow) -> str:
    """Pre-Phase-15 narrative sentence for artifacts without families data."""
    features = window.features_converging
    feature_preview = ", ".join(features[:5])
    if len(features) > 5:
        feature_preview += f", and {len(features) - 5} more"
    return (
        f"A convergence window beginning {window.start_date.isoformat()} "
        f"spans {len(features)} feature(s) shifting simultaneously "
        f"({feature_preview}), with an agreement ratio of "
        f"{window.convergence_ratio:.0%}."
    )


def _convergence_sentences(analysis: AnalysisResult, author_slug: str) -> list[str]:
    if not analysis.convergence_windows:
        return []
    strongest = max(analysis.convergence_windows, key=lambda w: w.convergence_ratio)
    families_sentence = _families_convergence_sentence(strongest, author_slug)
    if families_sentence is not None:
        return [families_sentence]
    return [_legacy_convergence_sentence(strongest)]


def _effect_size_sentences(analysis: AnalysisResult) -> list[str]:
    significant = sorted(
        (t for t in analysis.hypothesis_tests if t.significant),
        key=lambda t: abs(t.effect_size_cohens_d),
        reverse=True,
    )
    if not significant:
        return []
    top = significant[:3]
    parts = ", ".join(f"{t.feature_name} (d={t.effect_size_cohens_d:.2f})" for t in top)
    return [
        (
            f"The strongest significant effects were observed in {parts}, "
            f"drawn from {len(significant)} test(s) that cleared the "
            "pre-registered significance threshold."
        )
    ]


def _drift_sentences(analysis: AnalysisResult) -> list[str]:
    if analysis.drift_scores is None:
        return []
    phrase = describe_velocity_acceleration_pct(analysis.drift_scores.monthly_centroid_velocities)
    if phrase is None:
        return []
    return [
        f"Embedding drift velocity {phrase} in the "
        "second half of the timeline relative to the first half."
    ]


def _change_point_sentences(analysis: AnalysisResult) -> list[str]:
    if not analysis.change_points:
        return []
    unique_features = {cp.feature_name for cp in analysis.change_points}
    earliest = min(cp.timestamp for cp in analysis.change_points)
    return [
        (
            f"Stylometric change-points were detected across "
            f"{len(unique_features)} feature(s); the earliest timestamp was "
            f"{earliest.date().isoformat()}."
        )
    ]


def _era_sentences(analysis: AnalysisResult) -> list[str]:
    era = analysis.era_classification
    if era.total_ai_marker_change_points == 0 or era.dominant_era is None:
        return []
    label = era.dominant_era.replace("_", " ")
    return [
        (
            f"AI-marker change-points were concentrated in the {label} era "
            f"({era.total_ai_marker_change_points} gated marker event(s))."
        )
    ]


def _control_sentences(control_count: int) -> list[str]:
    if control_count <= 0:
        return []
    return [
        (
            f"The same combined pattern was not observed among {control_count} "
            "natural-control author(s) drawn from the same corpus."
        )
    ]


def _score_sentences(score: SurveyScore) -> list[str]:
    """Open the paragraph with the score tier and composite magnitude."""
    strength_label = score.strength.value.replace("_", " ").title()
    parts = [
        f"stylometry and structural convergence {score.pipeline_a_score:.2f}",
        f"embedding drift {score.pipeline_b_score:.2f}",
    ]
    if score.pipeline_c_score is not None:
        parts.append(f"language-model probability trajectory {score.pipeline_c_score:.2f}")
    parts.append(f"joint convergence index {score.convergence_score:.2f}")
    return [
        (
            f"Composite signal classification: {strength_label} "
            f"(composite index {score.composite:.3f}; "
            f"{', '.join(parts)})."
        )
    ]


def _caveat_sentence() -> str:
    return (
        "Findings describe statistical patterns in writing features; "
        "they do not by themselves demonstrate AI authorship and should be "
        "read alongside editorial and corpus caveats."
    )


def generate_evidence_narrative(
    analysis_result: AnalysisResult,
    author_slug: str,
    *,
    score: SurveyScore | None = None,
    control_count: int = 0,
    preregistration: VerificationResult | None = None,
) -> str:
    """Deterministic evidence paragraph.

    Optional ``score`` / ``preregistration`` keep copy aligned with tables and lock checks.
    """
    resolved_score = score if score is not None else compute_composite_score(analysis_result)

    header = (
        f"Summary for author {author_slug} (analysis record "
        f"{analysis_result.run_id[:8]}, configuration hash "
        f"{analysis_result.config_hash}). "
    )

    sentences: list[str] = []
    sentences.extend(_score_sentences(resolved_score))

    if resolved_score.strength == SignalStrength.NONE:
        sentences.append(
            "No evidence of AI-assisted writing was detected above the pre-registered thresholds."
        )
    else:
        sentences.extend(_convergence_sentences(analysis_result, author_slug))
        sentences.extend(_effect_size_sentences(analysis_result))
        sentences.extend(_drift_sentences(analysis_result))
        sentences.extend(_change_point_sentences(analysis_result))
        sentences.extend(_era_sentences(analysis_result))
        sentences.extend(_control_sentences(control_count))

    prereg_clause = _preregistration_clause(preregistration)
    if prereg_clause:
        sentences.append(prereg_clause)

    sentences.append(_caveat_sentence())

    return header + " ".join(sentences)


def _author_has_embeddings(slug: str, paths: AnalysisArtifactPaths) -> bool:
    """Mirror ``drift._author_has_embeddings_on_disk`` without importing it.

    Re-importing the analysis-layer helper would create a reporting → analysis
    dependency just for one filesystem check. Repeating the four lines is the
    smaller price.
    """
    slug_dir = paths.embeddings_dir / slug
    if not slug_dir.is_dir():
        return False
    return any(slug_dir.iterdir())


def _has_missing_drift_artifact(slug: str, paths: AnalysisArtifactPaths) -> bool:
    artifacts = (
        paths.drift_json(slug),
        paths.baseline_curve_json(slug),
        paths.centroids_npz(slug),
    )
    return any(not p.is_file() for p in artifacts)


def pipeline_b_diagnostics_block(
    author_slug: str,
    paths: AnalysisArtifactPaths,
) -> str:
    """Plain-text note when embeddings exist but a drift artifact is missing; otherwise empty."""
    if not _author_has_embeddings(author_slug, paths):
        return ""
    if not _has_missing_drift_artifact(author_slug, paths):
        return ""
    return PIPELINE_B_DIAGNOSTIC_NOTE


__all__ = [
    "PIPELINE_B_DIAGNOSTIC_NOTE",
    "generate_evidence_narrative",
    "pipeline_b_diagnostics_block",
]
