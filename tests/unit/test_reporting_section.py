"""K1–K3 reporting: narrative family path, section mix/contrast HTML, H2 hash pins."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from forensics.models.analysis import (
    AnalysisResult,
    ChangePoint,
    ConvergenceWindow,
    DriftScores,
    HypothesisTest,
)
from forensics.reporting.html_report import (
    SECTION_MIX_CAPTION,
    render_section_contrast_table,
    render_section_mix_chart,
)
from forensics.reporting.narrative import generate_evidence_narrative


def _result_with_families() -> AnalysisResult:
    """``AnalysisResult`` with five families represented (post-registry regroup)."""
    slug = "david-gilmour"
    cps = [
        ChangePoint(
            feature_name=feat,
            author_id=slug,
            timestamp=datetime(2025, 6, 10, tzinfo=UTC),
            confidence=0.9,
            method="pelt",
            effect_size_cohens_d=0.8,
            direction="increase",
        )
        for feat in (
            "flesch_kincaid",
            "mattr",
            "sent_length_mean",
            "ai_marker_frequency",
            "bigram_entropy",
        )
    ]
    window = ConvergenceWindow(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 2, 28),
        features_converging=[
            "ai_marker_frequency",
            "bigram_entropy",
            "flesch_kincaid",
            "mattr",
            "sent_length_mean",
        ],
        families_converging=[
            "ai_markers",
            "entropy",
            "lexical_richness",
            "readability",
            "sentence_structure",
        ],
        convergence_ratio=5.0 / 6.0,
        pipeline_a_score=0.72,
        pipeline_b_score=0.0,
        pipeline_c_score=None,
        passes_via=["ratio"],
    )
    tests = [
        HypothesisTest(
            test_name="welch",
            feature_name="flesch_kincaid",
            author_id=slug,
            raw_p_value=0.001,
            corrected_p_value=0.005,
            effect_size_cohens_d=0.9,
            confidence_interval_95=(0.6, 1.2),
            significant=True,
        ),
    ]
    return AnalysisResult(
        author_id=slug,
        run_id="00000000-0000-0000-0000-000000000001",
        run_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        config_hash="cafebabedeadbeef",
        change_points=cps,
        convergence_windows=[window],
        drift_scores=None,
        hypothesis_tests=tests,
    )


def _result_legacy_no_families() -> AnalysisResult:
    """Pre-Phase-15 ``AnalysisResult`` with only ``features_converging`` populated."""
    slug = "jane-legacy"
    window = ConvergenceWindow(
        start_date=date(2024, 5, 1),
        end_date=date(2024, 7, 31),
        features_converging=["ttr", "flesch_kincaid", "ai_marker_frequency"],
        # Note: families_converging defaults to []
        convergence_ratio=0.5,
        pipeline_a_score=0.5,
        pipeline_b_score=0.0,
        pipeline_c_score=None,
        passes_via=["ratio"],
    )
    drift = DriftScores(
        author_id=slug,
        baseline_centroid_similarity=0.5,
        ai_baseline_similarity=None,
        monthly_centroid_velocities=[0.1, 0.2, 0.3, 0.4, 0.5],
        intra_period_variance_trend=[0.05, 0.06, 0.07, 0.08, 0.09],
    )
    hyp = HypothesisTest(
        test_name="mann_whitney_ai_marker_frequency",
        feature_name="ai_marker_frequency",
        author_id=slug,
        raw_p_value=0.01,
        corrected_p_value=0.02,
        effect_size_cohens_d=0.85,
        confidence_interval_95=(0.5, 1.2),
        significant=True,
        n_pre=20,
        n_post=20,
    )
    return AnalysisResult(
        author_id=slug,
        run_id="00000000-0000-0000-0000-000000000002",
        run_timestamp=datetime(2025, 6, 1, tzinfo=UTC),
        config_hash="0123456789abcdef",
        change_points=[
            ChangePoint(
                feature_name="ai_marker_frequency",
                author_id=slug,
                timestamp=datetime(2024, 5, 15, tzinfo=UTC),
                confidence=0.85,
                method="pelt",
                effect_size_cohens_d=0.7,
                direction="increase",
            ),
        ],
        convergence_windows=[window],
        drift_scores=drift,
        hypothesis_tests=[hyp],
    )


def test_narrative_uses_families_converging() -> None:
    """K1: narrative names families with their representative features."""
    text = generate_evidence_narrative(_result_with_families(), "david-gilmour")
    # Spec example wording: "<slug>'s <Mon YYYY> window shows convergence
    # across N of M feature families: family (feat), ..."
    expected_phrase = (
        "david-gilmour's Dec 2025 window shows convergence across 5 of 6 feature families"
    )
    assert expected_phrase in text
    # Every family/representative pair should appear in "family (feature)" form.
    for family, feat in [
        ("ai_markers", "ai_marker_frequency"),
        ("entropy", "bigram_entropy"),
        ("lexical_richness", "mattr"),
        ("readability", "flesch_kincaid"),
        ("sentence_structure", "sent_length_mean"),
    ]:
        assert f"{family} ({feat})" in text


def test_narrative_falls_back_to_features_when_no_families() -> None:
    """K1: empty ``families_converging`` triggers the legacy sentence."""
    text = generate_evidence_narrative(_result_legacy_no_families(), "jane-legacy")
    # Legacy wording is preserved for back-compat.
    assert "convergence window beginning 2024-05-01" in text
    assert "feature families" not in text  # Make sure we did NOT emit the K1 wording.


def _write_section_mix(tmp_path: Path, slug: str = "david-gilmour") -> Path:
    payload = {
        "author_id": slug,
        "months": ["2025-10", "2025-11", "2025-12"],
        "sections": ["opinion", "politics"],
        "shares": [
            [0.5, 0.5],
            [0.4, 0.6],
            [0.3, 0.7],
        ],
    }
    path = tmp_path / f"{slug}_section_mix.json"
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def test_section_mix_chart_renders_with_caption(tmp_path: Path) -> None:
    """K2: chart fragment carries a Plotly <div>, the data, and the verbatim caption."""
    path = _write_section_mix(tmp_path)
    fragment = render_section_mix_chart(path, author_slug="david-gilmour")
    assert "<div" in fragment
    # Plotly emits a <div id="..."> per chart; we set it deterministically.
    assert "section-mix-david-gilmour" in fragment
    # Verbatim caption from the spec.
    assert SECTION_MIX_CAPTION in fragment
    # Sections appear (legend / hover labels include the names).
    assert "opinion" in fragment
    assert "politics" in fragment


def test_section_mix_chart_missing_artifact_soft_fails(tmp_path: Path) -> None:
    """K2: a missing JSON yields the placeholder fragment, not an exception."""
    fragment = render_section_mix_chart(
        tmp_path / "absent_section_mix.json",
        author_slug="ghost",
    )
    assert "section-mix-missing" in fragment
    assert "No section-mix data" in fragment


def _write_section_contrast(tmp_path: Path, slug: str = "david-gilmour") -> Path:
    payload = {
        "author_id": slug,
        "pairs": [
            {
                "section_a": "opinion",
                "section_b": "politics",
                "n_a": 92,
                "n_b": 204,
                "significant_features_by_family": {
                    "voice": ["first_person_ratio"],
                    "readability": ["flesch_kincaid", "gunning_fog"],
                },
            },
        ],
    }
    path = tmp_path / f"{slug}_section_contrast.json"
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def test_section_contrast_table_renders_rows_and_columns(tmp_path: Path) -> None:
    """K3: table contains row per pair, column per family with significant features."""
    path = _write_section_contrast(tmp_path)
    fragment = render_section_contrast_table(path, author_slug="david-gilmour")
    assert "<table" in fragment
    assert "section-contrast-table" in fragment
    # Row label encodes the section pair.
    assert "opinion vs politics" in fragment
    # Family column headers present.
    assert "<th>readability</th>" in fragment
    assert "<th>voice</th>" in fragment
    # Cell content carries the feature names.
    assert "first_person_ratio" in fragment
    assert "flesch_kincaid" in fragment
    assert "gunning_fog" in fragment


def test_section_contrast_table_missing_artifact(tmp_path: Path) -> None:
    """K3: missing JSON renders the 'No section-contrast data' fallback."""
    fragment = render_section_contrast_table(
        tmp_path / "absent_section_contrast.json",
        author_slug="ghost",
    )
    assert "No section-contrast data" in fragment


def test_section_contrast_table_insufficient_volume(tmp_path: Path) -> None:
    """K3: ``insufficient_section_volume`` disposition skips with a short note."""
    payload = {
        "author_id": "lowvol",
        "pairs": [],
        "disposition": "insufficient_section_volume",
    }
    path = tmp_path / "lowvol_section_contrast.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    fragment = render_section_contrast_table(path, author_slug="lowvol")
    assert "Insufficient section volume" in fragment
    assert "<table" not in fragment


# Pinned SHA-256 of the K3 contrast-table fixture. If this drifts, the
# rendered HTML format changed — update both the producer and this pin in
# the same commit (intentional change) or revert (regression).
_EXPECTED_CONTRAST_SHA256 = "34857d10b61bebdb20a3d1ce2fbfd71fe5da5ea9811653d87a0d61b53170e785"


def test_section_contrast_table_sha256_byte_pin(tmp_path: Path) -> None:
    """A fixed-seed fixture produces a stable SHA-256 of the rendered fragment."""
    path = _write_section_contrast(tmp_path)
    fragment = render_section_contrast_table(path, author_slug="david-gilmour")
    digest = hashlib.sha256(fragment.encode("utf-8")).hexdigest()
    assert digest == _EXPECTED_CONTRAST_SHA256, (
        f"Section contrast HTML hash drifted. New hash: {digest!r}; fragment: {fragment!r}"
    )


def test_section_contrast_table_is_byte_deterministic(tmp_path: Path) -> None:
    """Calling the helper twice with the same input yields identical bytes."""
    path = _write_section_contrast(tmp_path)
    a = render_section_contrast_table(path, author_slug="david-gilmour")
    b = render_section_contrast_table(path, author_slug="david-gilmour")
    assert a == b
    assert a.encode("utf-8") == b.encode("utf-8")


@pytest.mark.parametrize("slug", ["one", "two", "three"])
def test_section_mix_chart_div_id_is_deterministic(tmp_path: Path, slug: str) -> None:
    """K2 div id is keyed on slug — required for stable HTML output."""
    path = _write_section_mix(tmp_path, slug=slug)
    fragment = render_section_mix_chart(path, author_slug=slug)
    assert f"section-mix-{slug}" in fragment
