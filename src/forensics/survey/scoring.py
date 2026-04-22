"""Composite AI adoption scoring + natural control cohort (Phase 12 §1d + §5c)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from forensics.models.analysis import AnalysisResult
from forensics.survey.qualification import QualifiedAuthor

# Phase 4 scalar feature count: Lexical(6) + Structural(9) + Readability(4) +
# Content(7) + Productivity(5) + POS(4) = 35. Dict-valued fields are excluded.
_TOTAL_SCALAR_FEATURES = 35


class SignalStrength(StrEnum):
    """Human-readable classification of an AI-adoption signal."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"
    ERROR = "error"


@dataclass(frozen=True)
class SurveyScore:
    """Composite AI-adoption score for a single author in the survey."""

    composite: float
    strength: SignalStrength
    pipeline_a_score: float
    pipeline_b_score: float
    pipeline_c_score: float | None
    convergence_score: float
    num_convergence_windows: int
    strongest_window_ratio: float
    max_effect_size: float
    evidence_summary: str


@dataclass(frozen=True)
class ControlValidation:
    """Summary of the natural control cohort used to validate flagged authors."""

    num_controls: int
    mean_composite: float
    max_composite: float
    control_slugs: list[str]


def _pipeline_a_score(analysis: AnalysisResult) -> tuple[float, int]:
    """Return ``(score, num_unique_cp_features)`` for stylometric change-points."""
    unique_cp_features = len({cp.feature_name for cp in analysis.change_points})
    # Normalise to a fraction of features with changepoints, capped at 1.0.
    denom = max(_TOTAL_SCALAR_FEATURES * 0.3, 1.0)
    return min(unique_cp_features / denom, 1.0), unique_cp_features


def _pipeline_b_score(analysis: AnalysisResult) -> float:
    """Embedding drift acceleration relative to the first half of the series."""
    if analysis.drift_scores is None:
        return 0.0
    velocities = analysis.drift_scores.monthly_centroid_velocities
    if len(velocities) < 6:
        return 0.0
    mid = len(velocities) // 2
    early = sum(velocities[:mid]) / max(mid, 1)
    late = sum(velocities[mid:]) / max(len(velocities) - mid, 1)
    if early <= 0:
        return 0.0
    acceleration = (late - early) / early
    return min(max(acceleration, 0.0), 1.0)


def _pipeline_c_score(analysis: AnalysisResult) -> float | None:
    """Mean Pipeline C (probability) score across convergence windows, if available."""
    scores = [
        w.pipeline_c_score for w in analysis.convergence_windows if w.pipeline_c_score is not None
    ]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _convergence_score(analysis: AnalysisResult) -> tuple[float, float]:
    """Return ``(convergence_score, strongest_ratio)``."""
    windows = analysis.convergence_windows
    if not windows:
        return 0.0, 0.0
    strongest_ratio = max(w.convergence_ratio for w in windows)
    score = min((len(windows) * 0.2) + (strongest_ratio * 0.8), 1.0)
    return score, strongest_ratio


def classify_signal(
    composite: float,
    conv_score: float = 0.0,
    max_effect: float = 0.0,
    num_windows: int = 0,
) -> SignalStrength:
    """Map numeric scores to a human-readable strength tier.

    Thresholds (§1d):
    - STRONG:   composite >= 0.7 AND conv_score >= 0.5 AND max_d >= 0.8 AND windows >= 2
    - MODERATE: composite >= 0.4 AND (conv_score >= 0.3 OR max_d >= 0.5)
    - WEAK:     composite >= 0.15
    - NONE:     otherwise
    """
    if composite >= 0.7 and conv_score >= 0.5 and max_effect >= 0.8 and num_windows >= 2:
        return SignalStrength.STRONG
    if composite >= 0.4 and (conv_score >= 0.3 or max_effect >= 0.5):
        return SignalStrength.MODERATE
    if composite >= 0.15:
        return SignalStrength.WEAK
    return SignalStrength.NONE


def _build_evidence_summary(
    strength: SignalStrength,
    num_windows: int,
    strongest_ratio: float,
    max_effect: float,
    num_cp_features: int,
    analysis: AnalysisResult,
) -> str:
    if strength == SignalStrength.NONE:
        return "No statistically significant AI adoption signal detected."
    if strength == SignalStrength.WEAK:
        return (
            f"Weak signal: {num_cp_features} feature(s) with changepoints, "
            f"max effect size d={max_effect:.2f}. "
            "Insufficient convergence for confident assessment."
        )
    if strength == SignalStrength.MODERATE:
        return (
            f"Moderate signal: {num_windows} convergence window(s) "
            f"(strongest {strongest_ratio:.0%} feature agreement), "
            f"max effect d={max_effect:.2f}."
        )
    # STRONG
    matching = sorted(
        w.start_date.isoformat()
        for w in analysis.convergence_windows
        if w.convergence_ratio == strongest_ratio
    )
    onset = matching[0] if matching else "unknown"
    return (
        f"Strong signal: {num_windows} convergence window(s) starting ~{onset}, "
        f"{strongest_ratio:.0%} feature agreement, effect size d={max_effect:.2f}. "
        "Multiple independent pipelines agree."
    )


def compute_composite_score(
    analysis: AnalysisResult,
    qualification: QualifiedAuthor | None = None,
) -> SurveyScore:
    """Compute a composite AI-adoption score for one author.

    Weighting (§1d):
    - If Pipeline C available: 25% A, 25% B, 15% C, 35% convergence
    - Otherwise: 30% A, 30% B, 40% convergence
    """
    # ``qualification`` is reserved for future author-level adjustments
    # (e.g. confidence weighting by article volume). Kept in the signature to
    # match the prompt and avoid churning call sites when those hooks land.
    del qualification

    pa_score, unique_cp_features = _pipeline_a_score(analysis)
    pb_score = _pipeline_b_score(analysis)
    pc_score = _pipeline_c_score(analysis)
    conv_score, strongest_ratio = _convergence_score(analysis)

    significant_tests = [t for t in analysis.hypothesis_tests if t.significant]
    max_effect = max(
        (abs(t.effect_size_cohens_d) for t in significant_tests),
        default=0.0,
    )

    if pc_score is not None:
        composite = 0.25 * pa_score + 0.25 * pb_score + 0.15 * pc_score + 0.35 * conv_score
    else:
        composite = 0.30 * pa_score + 0.30 * pb_score + 0.40 * conv_score

    strength = classify_signal(
        composite,
        conv_score=conv_score,
        max_effect=max_effect,
        num_windows=len(analysis.convergence_windows),
    )

    summary = _build_evidence_summary(
        strength,
        len(analysis.convergence_windows),
        strongest_ratio,
        max_effect,
        unique_cp_features,
        analysis,
    )

    return SurveyScore(
        composite=round(composite, 4),
        strength=strength,
        pipeline_a_score=round(pa_score, 4),
        pipeline_b_score=round(pb_score, 4),
        pipeline_c_score=round(pc_score, 4) if pc_score is not None else None,
        convergence_score=round(conv_score, 4),
        num_convergence_windows=len(analysis.convergence_windows),
        strongest_window_ratio=round(strongest_ratio, 4),
        max_effect_size=round(max_effect, 4),
        evidence_summary=summary,
    )


# ---------------------------------------------------------------------------
# §5c — Natural control cohort
# ---------------------------------------------------------------------------


def identify_natural_controls(
    scores: dict[str, SurveyScore],
    *,
    threshold: float = 0.2,
) -> list[str]:
    """Identify authors whose composite score falls below the control threshold.

    Authors tagged :class:`SignalStrength.NONE` with ``composite <= threshold``
    form the natural control cohort (§5c): controls are discovered rather than
    cherry-picked.
    """
    controls: list[str] = []
    for slug, score in scores.items():
        if score.strength == SignalStrength.ERROR:
            continue
        if score.composite <= threshold and score.strength == SignalStrength.NONE:
            controls.append(slug)
    return sorted(controls)


def validate_against_controls(
    scores: dict[str, SurveyScore],
    control_slugs: list[str],
) -> ControlValidation:
    """Summarise the control cohort to provide a robustness check.

    Returns the size, mean composite, and max composite of the control group —
    flagged authors can then be compared against this baseline distribution.
    """
    control_set = set(control_slugs)
    control_scores = [s.composite for slug, s in scores.items() if slug in control_set]
    if not control_scores:
        return ControlValidation(
            num_controls=0,
            mean_composite=0.0,
            max_composite=0.0,
            control_slugs=list(control_slugs),
        )
    return ControlValidation(
        num_controls=len(control_scores),
        mean_composite=round(sum(control_scores) / len(control_scores), 4),
        max_composite=round(max(control_scores), 4),
        control_slugs=sorted(control_set),
    )
