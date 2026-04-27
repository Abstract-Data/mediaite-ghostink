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

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from forensics.models.analysis import ConvergenceWindow, HypothesisTest


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


class ReportManifest(BaseModel):
    run_id: str
    title: str
    generated_at: datetime
    sections: list[str]
    output_paths: dict[str, str]
