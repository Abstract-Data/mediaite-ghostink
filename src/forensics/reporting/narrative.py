"""Evidence-chain narrative generation for flagged authors (Phase 12 §6d).

Given an :class:`AnalysisResult`, produce a short, factual prose paragraph
(~200-400 words) summarising what the detector found for a single author.
The output is designed to be pasted verbatim into a published report, so
the function is deterministic: the same inputs always yield the same bytes.

The narrative covers:

- Which detectors fired (stylometric change-points, embedding drift,
  probability convergence).
- The strongest signals with quantitative effect sizes.
- Convergence windows and their feature overlap.
- Embedding-drift acceleration relative to baseline, when computable.
- Optional natural-control comparison.
- Pre-registration lock status, when verifiable against disk.

The tone is deliberately conservative — no hype language, no speculation
about intent. Calibrated hedges (``"no evidence"``, ``"consistent with"``)
mirror the language used in the preregistration document.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from forensics.analysis.utils import describe_velocity_acceleration_pct
from forensics.models.analysis import AnalysisResult
from forensics.survey.scoring import (
    SignalStrength,
    SurveyScore,
    compute_composite_score,
)

if TYPE_CHECKING:
    from forensics.preregistration import VerificationResult


# ---------------------------------------------------------------------------
# Preregistration helper — deterministic, never raises
# ---------------------------------------------------------------------------


def _preregistration_clause(verification: VerificationResult | None) -> str:
    """Return a short sentence describing the preregistration lock state.

    ``None`` means the caller did not supply verification (we do not touch
    disk from a pure-function narrative). In that case the clause is empty.
    """
    if verification is None:
        return ""
    if verification.status == "ok":
        return "Analysis thresholds were pre-registered prior to outcome review."
    if verification.status == "missing":
        return (
            "No pre-registration lock was located; this result is exploratory "
            "rather than confirmatory."
        )
    # mismatch
    return (
        "Pre-registration thresholds have drifted since lock; treat the "
        "result as exploratory until the discrepancy is reconciled."
    )


# ---------------------------------------------------------------------------
# Per-signal paragraph builders — each returns a list of sentences
# ---------------------------------------------------------------------------


def _convergence_sentences(analysis: AnalysisResult) -> list[str]:
    if not analysis.convergence_windows:
        return []
    strongest = max(analysis.convergence_windows, key=lambda w: w.convergence_ratio)
    features = strongest.features_converging
    feature_preview = ", ".join(features[:5])
    if len(features) > 5:
        feature_preview += f", and {len(features) - 5} more"
    return [
        (
            f"A convergence window beginning {strongest.start_date.isoformat()} "
            f"spans {len(features)} feature(s) shifting simultaneously "
            f"({feature_preview}), with an agreement ratio of "
            f"{strongest.convergence_ratio:.0%}."
        )
    ]


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
            f"This pattern was not observed in {control_count} natural-control "
            "author(s) drawn from the same corpus, supporting an "
            "author-specific rather than an editorial explanation."
        )
    ]


def _score_sentences(score: SurveyScore) -> list[str]:
    """Open the paragraph with the score tier and composite magnitude."""
    strength_label = score.strength.value.upper()
    pipelines = [
        f"Pipeline A = {score.pipeline_a_score:.2f}",
        f"Pipeline B = {score.pipeline_b_score:.2f}",
    ]
    if score.pipeline_c_score is not None:
        pipelines.append(f"Pipeline C = {score.pipeline_c_score:.2f}")
    pipelines.append(f"convergence = {score.convergence_score:.2f}")
    return [
        (
            f"Signal strength: {strength_label} "
            f"(composite = {score.composite:.3f}; "
            f"{', '.join(pipelines)})."
        )
    ]


def _caveat_sentence() -> str:
    return (
        "Findings describe statistical patterns in writing features; "
        "they do not by themselves demonstrate AI authorship and should be "
        "read alongside editorial and corpus caveats."
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_evidence_narrative(
    analysis_result: AnalysisResult,
    author_slug: str,
    *,
    score: SurveyScore | None = None,
    control_count: int = 0,
    preregistration: VerificationResult | None = None,
) -> str:
    """Produce a structured, factual evidence paragraph for a flagged author.

    The output is deterministic: identical inputs produce byte-identical
    output. This makes the function safe to include verbatim in reports
    under a pre-registration regime.

    Args:
        analysis_result: The per-author :class:`AnalysisResult` produced by
            the full analysis pipeline.
        author_slug: Author slug (e.g. ``"jane-doe"``) — appears verbatim in
            the opening sentence so the paragraph can be attributed.
        score: Optional :class:`SurveyScore`; if ``None``, it is computed
            from ``analysis_result`` on the fly. Supplying the score keeps
            the narrative consistent with an already-rendered ranking table.
        control_count: Number of natural-control authors whose scores were
            below threshold. ``0`` suppresses the controls sentence.
        preregistration: Optional outcome from
            :func:`forensics.preregistration.verify_preregistration`. When
            supplied, the narrative cites lock status.

    Returns:
        A single paragraph suitable for inclusion in a published report.
    """
    resolved_score = score if score is not None else compute_composite_score(analysis_result)

    header = (
        f"Author {author_slug} (analysis run {analysis_result.run_id[:8]}, "
        f"config {analysis_result.config_hash}): "
    )

    sentences: list[str] = []
    sentences.extend(_score_sentences(resolved_score))

    if resolved_score.strength == SignalStrength.NONE:
        sentences.append(
            "No evidence of AI-assisted writing was detected above the pre-registered thresholds."
        )
    else:
        sentences.extend(_convergence_sentences(analysis_result))
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


__all__ = ["generate_evidence_narrative"]
