"""Composite AI adoption scoring + natural control cohort (Phase 12 §1d + §5c)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from forensics.analysis.feature_families import family_for
from forensics.models.analysis import AnalysisResult, ChangePoint
from forensics.models.features import count_scalar_features
from forensics.survey.qualification import QualifiedAuthor

# Denominator tracks scalar feature count from the family registry (P3-MAINT-001).
_TOTAL_SCALAR_FEATURES = count_scalar_features()

# AI-marker CPs get a targeted bonus in ``_pipeline_a_score``; weight tuned for registry size.
_AI_MARKER_FAMILY = "ai_markers"
_AI_MARKER_PER_HIT_WEIGHT = 0.35

# Post–2022-11-30 AI-marker CPs only; drop tail window (BOCPD/PELT boundary over-detection).
_AI_ERA_CUTOFF = datetime(2022, 11, 30, tzinfo=UTC)
_TAIL_TRIM_DAYS = 30


def _corpus_tail_cutoff(analysis: AnalysisResult) -> datetime | None:
    """Cut-off after which a CP is considered too close to the analysis run
    to have enough post-CP data for BOCPD/PELT to confirm a sustained shift.

    Uses ``analysis.run_timestamp`` as the reference because we don't have
    the latest article date stored on AnalysisResult. The run_timestamp is
    set at the start of the analyze stage, immediately after the corpus is
    materialised, so it is within hours of the actual corpus end.
    """
    return analysis.run_timestamp - timedelta(days=_TAIL_TRIM_DAYS)


def _is_admissible_ai_evidence(cp: ChangePoint, tail_cutoff: datetime | None) -> bool:
    """Per change-point gate: only count *post-AI-era*, *increase*-direction
    AI-marker CPs detected outside the tail-of-series window as positive AI
    evidence. Decreases on AI-markers, pre-2022-11-30 CPs, and tail CPs are
    diagnostic noise, not signal.
    """
    if family_for(cp.feature_name) != _AI_MARKER_FAMILY:
        return False
    if cp.direction != "increase":
        return False
    if cp.timestamp < _AI_ERA_CUTOFF:
        return False
    if tail_cutoff is not None and cp.timestamp > tail_cutoff:
        return False
    return True


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
    """Control cohort size and composite aggregates; per-feature tests are out of scope here."""

    num_controls: int
    mean_composite: float
    max_composite: float
    control_slugs: list[str]


def _pipeline_a_score(analysis: AnalysisResult) -> tuple[float, int]:
    """Return ``(score, num_unique_cp_features)`` — the AI-targeted-evidence
    score for Pipeline A.

    Phase 15 J6 calibration removed the prior "breadth" path (fraction of all
    scalar features with any CP) because it folded normal stylistic variation
    into the AI-adoption score: PELT's per-feature std-scaled penalty fires
    on continuous features (TTR, sentence length, readability) at moderate
    effect sizes whenever a writer's style evolves over years — not specific
    to AI use. The targeted path is the only AI-diagnostic Pipeline A signal.

    Targeted score = count of distinct AI-marker family features with at
    least one *admissible* change-point (post-2022-11-30, ``increase``
    direction, outside the tail-trim window). Each unique feature
    contributes ``_AI_MARKER_PER_HIT_WEIGHT``; capped at 1.0.

    The second tuple element (``num_unique_cp_features``) still reports the
    raw count of distinct CP features for diagnostics in evidence summaries.
    """
    unique_cp_features = len({cp.feature_name for cp in analysis.change_points})

    tail_cutoff = _corpus_tail_cutoff(analysis)
    targeted_features = {
        cp.feature_name
        for cp in analysis.change_points
        if _is_admissible_ai_evidence(cp, tail_cutoff)
    }
    targeted_score = min(len(targeted_features) * _AI_MARKER_PER_HIT_WEIGHT, 1.0)

    return targeted_score, unique_cp_features


def _pipeline_b_score(analysis: AnalysisResult) -> float:
    """Embedding drift acceleration relative to the first half of the series."""
    if analysis.drift_scores is None:
        return 0.0
    return analysis.drift_scores.velocity_acceleration_ratio


def _pipeline_c_score(analysis: AnalysisResult) -> float | None:
    """Mean Pipeline C (probability) score across convergence windows, if available."""
    scores = [
        w.pipeline_c_score for w in analysis.convergence_windows if w.pipeline_c_score is not None
    ]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _convergence_score(analysis: AnalysisResult) -> tuple[float, float]:
    """Return ``(convergence_score, strongest_ratio)``.

    Phase 15 J6 calibration applies four filters:

    1. ``passes_via`` must contain ``ratio`` or ``ab`` — drift-only windows
       lack multi-pipeline corroboration and were inflating non-AI signal.
    2. ``features_converging`` must include at least one AI-marker family
       feature — convergence on stylistic features alone (TTR, sentence
       length, readability) is "the writer changed in many ways" rather than
       "the writer adopted AI", and PELT's per-feature std-scaled penalty
       fires on those features for normal multi-year writing evolution.
    3. ``start_date`` must be on or after the AI-era cutoff (2022-11-30,
       ChatGPT public launch). Pre-AI-era convergence cannot evidence LLM
       adoption — those windows reflect normal stylistic evolution or
       BOCPD/PELT warm-up artifacts.
    4. ``start_date`` must be before the tail-trim cutoff (run_timestamp -
       30d). Windows starting in the last 30 days of the analysis run lack
       sufficient post-window data for the constituent CPs to confirm a
       sustained regime shift — same instability that filters CPs at the
       Pipeline A level.
    """
    ai_era_cutoff_date = _AI_ERA_CUTOFF.date()
    tail_cutoff_date = _corpus_tail_cutoff(analysis).date()
    windows = [
        w
        for w in analysis.convergence_windows
        if any(channel in {"ratio", "ab"} for channel in w.passes_via)
        and any(family_for(f) == _AI_MARKER_FAMILY for f in w.features_converging)
        and ai_era_cutoff_date <= w.start_date < tail_cutoff_date
    ]
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
    targeted_max_effect: float = 0.0,
) -> SignalStrength:
    """Map numeric scores to a human-readable strength tier.

    Thresholds (§1d):
    - STRONG:   composite >= 0.7 AND conv_score >= 0.5 AND max_d >= 0.8 AND windows >= 2
    - MODERATE: composite >= 0.4 AND (conv_score >= 0.3 OR max_d >= 0.5)
    - WEAK:     composite >= 0.15
    - NONE:     otherwise

    Effect-size escape hatch: when ``targeted_max_effect`` (the largest
    Cohen's d on an AI-marker-family feature among significant hypothesis
    tests) is very large, the classifier promotes regardless of composite.
    A d ≥ 1.0 on the purpose-built AI-detection features is more diagnostic
    than the convergence-windows gate it would otherwise have to clear, and
    leaving it at NONE because Pipeline B saw no semantic drift produces
    false negatives on stylistic-only AI assistance.
    """
    if composite >= 0.7 and conv_score >= 0.5 and max_effect >= 0.8 and num_windows >= 2:
        return SignalStrength.STRONG
    if targeted_max_effect >= 2.0:
        return SignalStrength.STRONG
    if composite >= 0.4 and (conv_score >= 0.3 or max_effect >= 0.5):
        return SignalStrength.MODERATE
    if targeted_max_effect >= 1.0:
        return SignalStrength.MODERATE
    if composite >= 0.15 or targeted_max_effect >= 0.5:
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
    # Targeted effect size restricted to AI-marker family AND positive
    # (`d > 0`) effects — a *decrease* on `formula_opening_score` is the
    # *opposite* of an AI-adoption signal (writing got less formulaic).
    # Phase 15 J6 calibration also requires *temporal corroboration* via an
    # admissible change-point on the same feature: a hypothesis test alone
    # tells us baseline vs post-baseline means differ, but doesn't say when
    # the shift happened, so a sig test driven by a tail-of-series outlier
    # would otherwise spuriously trigger the escape hatch in classify_signal.
    tail_cutoff = _corpus_tail_cutoff(analysis)
    admissible_features = {
        cp.feature_name
        for cp in analysis.change_points
        if _is_admissible_ai_evidence(cp, tail_cutoff)
    }
    targeted_max_effect = max(
        (
            t.effect_size_cohens_d
            for t in significant_tests
            if family_for(t.feature_name) == _AI_MARKER_FAMILY
            and t.effect_size_cohens_d > 0
            and t.feature_name in admissible_features
        ),
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
        targeted_max_effect=targeted_max_effect,
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
    """Composite-level control cohort aggregates only (no per-feature Parquet tests)."""
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
