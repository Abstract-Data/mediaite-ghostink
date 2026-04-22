"""Report generation manifests (stub for later phases).

Phase 8 leaves several report-sidecar structures unimplemented until Quarto render
emits a unified metadata bundle next to HTML/PDF outputs.

TODO(phase-8): Add build provenance (Quarto/git/tooling versions), per-chapter
artifact manifests (figures, tables, custody cross-refs), and optional deploy
bundle URIs when ``forensics report`` writes a single JSON manifest.

TODO(phase-8): Extend ``ReportManifest.output_paths`` with stable keys for
``html_index``, ``pdf_bundle``, ``custody_attestation``, and figure asset dirs.
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
    """Map statistical evidence to a coarse strength label for reporting."""
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
    if len(significant_tests) >= 2:
        return FindingStrength.MODERATE
    if len(significant_tests) >= 1:
        return FindingStrength.WEAK
    return FindingStrength.NONE


# TODO(phase-8): ``ReportManifest`` is a minimal stub; wire writers when the
# report CLI persists manifests alongside rendered books.


class ReportManifest(BaseModel):
    run_id: str
    title: str
    generated_at: datetime
    sections: list[str]
    output_paths: dict[str, str]
