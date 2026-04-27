"""Report-side metadata and finding labels for the forensic pipeline.

Phase 8 reporting is implemented (Quarto-driven outputs); this module holds
types used by analysis and reporting code paths, not a dormant placeholder.

:class:`ReportManifest` is the canonical Pydantic shape for optional run-scoped
metadata (``run_id``, ``title``, ``generated_at``, ``sections``,
``output_paths``). Persisting a full sidecar manifest next to rendered books,
plus richer ``output_paths`` keys (for example ``html_index``, ``pdf_bundle``,
custody cross-refs, or build provenance), remains **optional** follow-up when
the report CLI standardizes on a single emitted JSON bundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from forensics.models.analysis import ConvergenceWindow, HypothesisTest
from forensics.models.direction_priors import AI_TYPICAL_DIRECTION, direction_from_d


class FindingStrength(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


def classify_finding_strength(
    convergence_window: ConvergenceWindow,
    hypothesis_tests: list[HypothesisTest],
    control_comparison: dict,
    *,
    probability_features_available: bool = False,
) -> FindingStrength:
    """Map statistical evidence to a coarse strength label for reporting.

    Tier definitions (callers SHOULD pass window-scoped ``hypothesis_tests``,
    i.e. tests whose ``feature_name`` appears in
    ``convergence_window.features_converging``):

    - **STRONG**: ≥3 strong significant tests (corrected p < 0.01 AND
      |Cohen's d| ≥ 0.8) AND controls clean (editorial_vs_author_signal > 0.7)
      AND Pipeline C OK when probability features are available.
    - **MODERATE**: ≥3 significant tests AND ≥1 strong significant test.
      The ``≥1 strong`` floor is what separates MODERATE from WEAK — without
      it, a window with three marginally-significant tests (e.g. p ≈ 0.04,
      |d| ≈ 0.3) would be classified the same as one with three large-effect
      tests at p < 10⁻⁵. The ``≥3 sig`` count keeps the MODERATE bar above
      the trivial 2-test threshold that previously bucketed authors with
      vastly different evidence strength into the same tier.
    - **WEAK**: ≥1 significant test (no effect-size requirement).
    - **NONE**: no significant tests.
    """
    significant_tests = [t for t in hypothesis_tests if t.significant]
    strong_tests = [
        t
        for t in significant_tests
        if t.corrected_p_value < 0.01 and abs(t.effect_size_cohens_d) >= 0.8
    ]
    controls_negative = control_comparison.get("editorial_vs_author_signal", 0.0) > 0.7
    pipeline_c_ok = not probability_features_available or (
        convergence_window.pipeline_c_score is not None
        and convergence_window.pipeline_c_score >= 0.5
    )

    if len(strong_tests) >= 3 and controls_negative and pipeline_c_ok:
        return FindingStrength.STRONG
    if len(significant_tests) >= 3 and len(strong_tests) >= 1:
        return FindingStrength.MODERATE
    if len(significant_tests) >= 1:
        return FindingStrength.WEAK
    return FindingStrength.NONE


def _strictly_stronger_hypothesis(a: HypothesisTest, b: HypothesisTest) -> bool:
    am, bm = abs(a.effect_size_cohens_d), abs(b.effect_size_cohens_d)
    if am > bm:
        return True
    if am < bm:
        return False
    return a.test_name < b.test_name


def _collapse_tests_by_max_abs_d(
    window_hypothesis_tests: list[HypothesisTest],
) -> dict[str, HypothesisTest]:
    by_feature: dict[str, HypothesisTest] = {}
    for test in window_hypothesis_tests:
        prev = by_feature.get(test.feature_name)
        if prev is None or _strictly_stronger_hypothesis(test, prev):
            by_feature[test.feature_name] = test
    return by_feature


class DirectionConcordance(StrEnum):
    """Exploratory diagnostic: how window effects align with AI-typical directions."""

    AI = "direction_ai"
    MIXED = "direction_mixed"
    NON_AI = "direction_non_ai"
    NA = "direction_na"


@dataclass(frozen=True)
class DirectionBreakdown:
    """Per-window counts after collapsing to one test per ``feature_name`` (max |d|)."""

    n_match: int
    n_oppose: int
    n_no_prior: int
    matched_features: tuple[str, ...]
    opposed_features: tuple[str, ...]


def classify_direction_concordance(
    convergence_window: ConvergenceWindow,
    window_hypothesis_tests: list[HypothesisTest],
) -> tuple[DirectionConcordance, DirectionBreakdown]:
    """Score how many window features moved in the AI-typical direction.

    Callers **must** pre-scope ``window_hypothesis_tests`` to the window (same
    convention as :func:`classify_finding_strength`). When
    ``convergence_window.features_converging`` is non-empty, only hypothesis rows
    whose ``feature_name`` appears in that list participate (aligned with
    :func:`classify_finding_strength`); when it is empty, all passed-in tests are
    used so odd callers are not silently emptied.

    For each distinct ``feature_name``, the test with the largest
    ``abs(effect_size_cohens_d)`` is kept; ties break on ``test_name`` for
    determinism. The empirical ≥50% match rule (among features with a non-null
    prior) is **exploratory** until locked in pre-registration.
    """
    scoped = window_hypothesis_tests
    fc = convergence_window.features_converging
    if fc:
        allow = frozenset(fc)
        scoped = [t for t in window_hypothesis_tests if t.feature_name in allow]
    by_feature = _collapse_tests_by_max_abs_d(scoped)

    matched: list[str] = []
    opposed: list[str] = []
    n_no_prior = 0
    for feature_name in sorted(by_feature):
        prior = AI_TYPICAL_DIRECTION.get(feature_name)
        observed = direction_from_d(by_feature[feature_name].effect_size_cohens_d)
        if prior is None:
            n_no_prior += 1
            continue
        if observed is None:
            n_no_prior += 1
            continue
        if observed == prior:
            matched.append(feature_name)
        else:
            opposed.append(feature_name)

    n_match = len(matched)
    n_oppose = len(opposed)
    prior_total = n_match + n_oppose
    if prior_total == 0:
        return (
            DirectionConcordance.NA,
            DirectionBreakdown(
                n_match=0,
                n_oppose=0,
                n_no_prior=n_no_prior,
                matched_features=tuple(),
                opposed_features=tuple(),
            ),
        )
    if n_match * 2 >= prior_total:
        concordance = DirectionConcordance.AI
    elif n_match > 0:
        concordance = DirectionConcordance.MIXED
    else:
        concordance = DirectionConcordance.NON_AI
    return (
        concordance,
        DirectionBreakdown(
            n_match=n_match,
            n_oppose=n_oppose,
            n_no_prior=n_no_prior,
            matched_features=tuple(matched),
            opposed_features=tuple(opposed),
        ),
    )


class VolumeRampFlag(StrEnum):
    """Exploratory diagnostic for pre/post article-count ratio inside the window."""

    STABLE = "volume_stable"
    GROWTH = "volume_growth"
    RAMP = "volume_ramp"
    DECLINE = "volume_decline"
    UNKNOWN = "volume_unknown"


def compute_volume_ramp_flag(
    window_hypothesis_tests: list[HypothesisTest],
) -> tuple[VolumeRampFlag, float | None]:
    """Classify corpus volume change using ``n_post / n_pre`` from the first usable row.

    The first **non-degenerate** test with ``n_pre > 0``, ``n_pre != -1``,
    ``n_post >= 0``, and ``n_post != -1`` supplies the ratio. Heterogeneous lists
    are rare; the first-wins rule is documented for transparency.

    Bands: stable ``[0.5, 2.0]``, growth ``(2, 5]``, ramp ``> 5``, decline
    ``< 0.5``. The 5× ramp cutoff is **exploratory** until pre-registration lock.
    """
    for test in window_hypothesis_tests:
        if test.degenerate:
            continue
        if test.n_pre <= 0 or test.n_pre == -1:
            continue
        if test.n_post < 0 or test.n_post == -1:
            continue
        ratio = test.n_post / test.n_pre
        if ratio < 0.5:
            return VolumeRampFlag.DECLINE, ratio
        if ratio <= 2.0:
            return VolumeRampFlag.STABLE, ratio
        if ratio <= 5.0:
            return VolumeRampFlag.GROWTH, ratio
        return VolumeRampFlag.RAMP, ratio
    return VolumeRampFlag.UNKNOWN, None


class ReportManifest(BaseModel):
    run_id: str
    title: str
    generated_at: datetime
    sections: list[str]
    output_paths: dict[str, str]
