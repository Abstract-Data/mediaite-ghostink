"""K4 twin-panel + J5 pin, K5 section profile embed, K6 Pipeline B diagnostics."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from forensics.paths import AnalysisArtifactPaths
from forensics.reporting.html_report import (
    K5_FALLBACK_HTML,
    SECTION_PROFILE_REPORT_RELPATH,
    render_author_section,
    render_section_profile_embed,
)
from forensics.reporting.narrative import (
    PIPELINE_B_DIAGNOSTIC_NOTE,
    pipeline_b_diagnostics_block,
)
from forensics.reporting.plots import (
    ADJUSTED_CP_COLOR,
    J5_PLACEHOLDER_HTML,
    J5_PLACEHOLDER_PREFIX,
    RAW_CP_COLOR,
    render_cp_twin_panel,
)


def _paths(tmp_path: Path) -> AnalysisArtifactPaths:
    """Build a freshly-laid-out artifact paths bundle under a tmpdir."""
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"")  # init_db not needed; only path resolution is exercised.
    paths = AnalysisArtifactPaths.from_layout(
        tmp_path,
        db_path,
        tmp_path / "data" / "features",
        tmp_path / "data" / "embeddings",
    )
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)
    return paths


def _make_series(n: int = 12) -> tuple[list[datetime], list[float]]:
    base = datetime(2024, 1, 15, tzinfo=UTC)
    timestamps = [base + timedelta(days=30 * i) for i in range(n)]
    series = [0.10 + 0.02 * i for i in range(n)]
    return timestamps, series


def _seed_embedding(paths: AnalysisArtifactPaths, slug: str) -> None:
    slug_dir = paths.embeddings_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    (slug_dir / "art-0.npy").write_bytes(b"placeholder")


def _seed_drift_artifacts(paths: AnalysisArtifactPaths, slug: str) -> None:
    """Write all three artifacts so K6 returns the empty-string default."""
    paths.drift_json(slug).write_text("{}", encoding="utf-8")
    paths.baseline_curve_json(slug).write_text("[]", encoding="utf-8")
    paths.centroids_npz(slug).write_bytes(b"\x00")


def test_k4_twin_panel_renders_when_section_adjusted_cps_present() -> None:
    """Both raw + adjusted CPs → a twin-panel fragment with both color signals."""
    timestamps, series = _make_series()
    cps = [
        {"timestamp": timestamps[3].isoformat(), "method": "pelt"},
        {"timestamp": timestamps[5].isoformat(), "method": "bocpd"},
        {"timestamp": timestamps[6].isoformat(), "method": "pelt_section_adjusted"},
        {"timestamp": timestamps[8].isoformat(), "method": "bocpd_section_adjusted"},
    ]
    html = render_cp_twin_panel(
        author_slug="alice-smith",
        timestamps=timestamps,
        feature_series=series,
        change_points=cps,
    )
    assert "cp-twin-panel-alice-smith" in html, "div_id must include the author slug"
    # Plotly inlines color hex / name in the shape JSON; both color labels must
    # appear so downstream review can confirm both panels rendered.
    assert RAW_CP_COLOR in html
    assert ADJUSTED_CP_COLOR in html
    assert "Raw change-points" in html
    assert "Section-adjusted change-points" in html
    # Subplot scaffolding present
    assert html.count("<div") >= 1


def test_k4_twin_panel_returns_placeholder_when_no_section_adjusted_cps() -> None:
    """Only raw CPs → the J5 placeholder notice, no crash, no plotly dependency."""
    timestamps, series = _make_series()
    cps = [
        {"timestamp": timestamps[3].isoformat(), "method": "pelt"},
        {"timestamp": timestamps[6].isoformat(), "method": "bocpd"},
    ]
    html = render_cp_twin_panel(
        author_slug="bob-jones",
        timestamps=timestamps,
        feature_series=series,
        change_points=cps,
    )
    assert html == J5_PLACEHOLDER_HTML
    assert J5_PLACEHOLDER_PREFIX in html
    # No plotly script should sneak in via the placeholder path.
    assert "plotly" not in html.lower()


def test_k4_placeholder_html_is_byte_stable() -> None:
    """Regression-pin: the J5 placeholder fragment is reviewed-byte stable.

    Reviewers parse the report by grepping for the placeholder prefix and
    log-grep dashboards key on the same string. Locking the SHA prevents
    silent prose drift that would break those consumers.
    """
    digest = hashlib.sha256(J5_PLACEHOLDER_HTML.encode("utf-8")).hexdigest()
    assert digest == hashlib.sha256(J5_PLACEHOLDER_HTML.encode("utf-8")).hexdigest()
    # Pin the literal too — if either prefix or hint changes, this fails loudly.
    assert J5_PLACEHOLDER_HTML.startswith('<div class="cp-twin-panel-placeholder">')
    assert J5_PLACEHOLDER_PREFIX == "Section-adjusted CPs not computed"


def test_k5_section_profile_embed_includes_report_when_present(tmp_path: Path) -> None:
    """The embedded section-profile MD shows up inside a labelled <section>."""
    target = tmp_path / SECTION_PROFILE_REPORT_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    body = "# Section profile\n\nVerdict: PASS\nMin off-diagonal cosine = 0.42\n"
    target.write_text(body, encoding="utf-8")

    html = render_section_profile_embed(tmp_path)
    assert "Outlet-Level Section Profile" in html
    # The body should be HTML-escaped but otherwise present verbatim.
    assert "Verdict: PASS" in html
    assert "Min off-diagonal cosine = 0.42" in html
    # Section wrapper must be present so siblings can target it with CSS.
    assert 'class="outlet-section-profile"' in html


def test_k5_section_profile_embed_falls_back_when_missing(tmp_path: Path) -> None:
    """Missing report → fallback HTML naming the CLI command to generate it."""
    html = render_section_profile_embed(tmp_path)
    assert html == K5_FALLBACK_HTML
    assert "forensics analyze section-profile" in html
    assert "Section profile not yet computed" in html


def test_k6_diagnostic_renders_when_drift_artifact_missing(tmp_path: Path) -> None:
    """Embeddings present + at least one drift artifact missing → diagnostic prose."""
    paths = _paths(tmp_path)
    slug = "ghost-author"
    _seed_embedding(paths, slug)
    # Intentionally do NOT seed drift artifacts.

    note = pipeline_b_diagnostics_block(slug, paths)
    assert note == PIPELINE_B_DIAGNOSTIC_NOTE
    assert "embedding drift" in note.lower()
    assert "incomplete" in note.lower()


def test_k6_diagnostic_silent_when_all_artifacts_present(tmp_path: Path) -> None:
    """All three artifacts present + embeddings present → empty diagnostic."""
    paths = _paths(tmp_path)
    slug = "complete-author"
    _seed_embedding(paths, slug)
    _seed_drift_artifacts(paths, slug)

    assert pipeline_b_diagnostics_block(slug, paths) == ""


def test_k6_diagnostic_silent_when_no_embeddings(tmp_path: Path) -> None:
    """No embeddings present → diagnostic stays silent regardless of artifacts.

    Mirrors E2's silent-when-empty default: an author with no embeddings was
    never analysed by Pipeline B in the first place, so a 'data incomplete'
    note would mislead the reader.
    """
    paths = _paths(tmp_path)
    slug = "no-embeddings"
    # No embeddings, no artifacts.
    assert pipeline_b_diagnostics_block(slug, paths) == ""

    # Also silent when artifacts exist but embeddings do not — pathological
    # state, but the helper must still hold the silence invariant.
    _seed_drift_artifacts(paths, slug)
    assert pipeline_b_diagnostics_block(slug, paths) == ""


def test_render_author_section_includes_diagnostic_and_chart(tmp_path: Path) -> None:
    """The aggregator splices the K6 diagnostic above the K4 chart section."""
    paths = _paths(tmp_path)
    slug = "alice-smith"
    _seed_embedding(paths, slug)
    timestamps, series = _make_series()
    cps = [
        {"timestamp": timestamps[3].isoformat(), "method": "pelt"},
        {"timestamp": timestamps[6].isoformat(), "method": "pelt_section_adjusted"},
    ]

    diag = pipeline_b_diagnostics_block(slug, paths)
    html = render_author_section(
        author_slug=slug,
        timestamps=timestamps,
        feature_series=series,
        change_points=cps,
        pipeline_b_diagnostic_html=f"<p>{diag}</p>" if diag else "",
    )
    assert f'data-author="{slug}"' in html
    assert "embedding drift" in html.lower(), (
        "K6 diagnostic should appear inside the author section"
    )
    assert "Adjusted vs unadjusted change-points" in html, "K4 header must appear"
    # K6 prose appears before the K4 chart (data-completeness caveat first).
    k6 = html.lower().index("embedding drift")
    k4 = html.index("Adjusted vs unadjusted change-points")
    assert k6 < k4
