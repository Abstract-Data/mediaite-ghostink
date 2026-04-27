"""Phase 15 E1+E2 — Pipeline B diagnostics: DEBUG component logging + missing-artifact WARNING.

These tests pin the diagnostics-only behaviour added in Phase 15 E1 (per-window
component logging in ``_score_single_window``) and E2 (WARNING on missing drift
artifacts when embeddings exist on disk). No formulas are exercised here — only
log emission, levels, and message format.

The WARNING template is ``_DRIFT_ARTIFACT_MISSING_WARNING``; the regression-pin
test below imports it directly so log-grep dashboards keyed on the prefix break
loudly if the wording ever changes.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from forensics.analysis.convergence import ConvergenceInput, compute_convergence_scores
from forensics.analysis.drift import (
    _DRIFT_ARTIFACT_MISSING_WARNING,
    load_drift_summary,
)
from forensics.analysis.orchestrator import AnalysisMode
from forensics.config.settings import AnalysisConfig, ForensicsSettings, ScrapingConfig
from forensics.models.analysis import ChangePoint
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.repository import init_db


def _settings() -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(baseline_embedding_count=3),
    )


def _paths(tmp_path: Path) -> AnalysisArtifactPaths:
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    paths = AnalysisArtifactPaths.from_layout(
        tmp_path,
        db_path,
        tmp_path / "data" / "features",
        tmp_path / "data" / "embeddings",
    )
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)
    return paths


def _seed_embedding_dir(paths: AnalysisArtifactPaths, slug: str) -> Path:
    """Create ``data/embeddings/<slug>/`` with one placeholder file.

    The E2 detection only checks for directory existence + at least one entry;
    the file content is irrelevant since :func:`load_drift_summary` falls back
    silently when the manifest is absent.
    """
    slug_dir = paths.embeddings_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    (slug_dir / "art-0.npy").write_bytes(b"placeholder")
    return slug_dir


def _cp(feature_name: str, ts: datetime) -> ChangePoint:
    return ChangePoint(
        feature_name=feature_name,
        author_id="author-diag",
        timestamp=ts,
        confidence=0.9,
        method="pelt",  # type: ignore[arg-type]
        effect_size_cohens_d=0.8,
        direction="increase",  # type: ignore[arg-type]
    )


def test_e1_score_single_window_emits_debug_components(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Phase 15 E1: a scored window emits DEBUG with all four named components."""
    caplog.set_level(logging.DEBUG, logger="forensics.analysis.convergence")
    base = datetime(2024, 6, 1, tzinfo=UTC)
    cps = [
        _cp("ttr", base),
        _cp("flesch_kincaid", base + timedelta(days=2)),
    ]

    compute_convergence_scores(
        ConvergenceInput.build(
            change_points=cps,
            centroid_velocities=[("2024-06", 0.5)],
            baseline_similarity_curve=[],
            window_days=30,
            total_feature_count=2,
        )
    )

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert debug_records, "expected at least one DEBUG record from convergence scoring"
    assert any(
        all(
            token in r.message
            for token in ("peak_signal=", "sim_signal=", "ai_signal=", "pipeline_b=")
        )
        for r in debug_records
    ), "DEBUG record must name all four Pipeline-B component signals"
    assert any("author=author-diag" in r.message for r in debug_records), (
        "DEBUG record must identify the author so per-author diagnostics is possible"
    )


def test_e2_warns_when_artifacts_missing_but_embeddings_exist(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Phase 15 E2: missing drift artifacts + embeddings on disk → one WARNING per artifact."""
    paths = _paths(tmp_path)
    slug = "ghost-author"
    _seed_embedding_dir(paths, slug)

    caplog.set_level(logging.WARNING, logger="forensics.analysis.drift")
    load_drift_summary(slug, paths, settings=_settings(), mode=AnalysisMode(exploratory=True))

    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name == "forensics.analysis.drift"
    ]
    # Three artifacts checked: drift.json, baseline_curve.json, centroids.npz.
    assert len(warnings) == 3, (
        f"expected exactly one WARNING per missing artifact, got {len(warnings)}: "
        f"{[r.message for r in warnings]}"
    )
    artifact_labels = {"drift.json", "baseline_curve.json", "centroids.npz"}
    for record in warnings:
        assert slug in record.message, f"WARNING must name the slug: {record.message!r}"
    logged_artifacts = {
        label for label in artifact_labels if any(label in r.message for r in warnings)
    }
    assert logged_artifacts == artifact_labels, (
        f"each missing artifact must produce its own WARNING; got {logged_artifacts}"
    )


def test_e2_silent_when_no_embeddings_exist(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Phase 15 E2: no embeddings + no artifacts → no WARNING (avoid log noise)."""
    paths = _paths(tmp_path)
    slug = "untouched-author"

    caplog.set_level(logging.WARNING, logger="forensics.analysis.drift")
    load_drift_summary(slug, paths, settings=_settings(), mode=AnalysisMode(exploratory=True))

    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name == "forensics.analysis.drift"
    ]
    assert warnings == [], (
        "no WARNING expected when author has no embeddings on disk; "
        f"got {[r.message for r in warnings]}"
    )


def test_e2_warning_message_format_is_stable(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Phase 15 E2 regression-pin: the WARNING template stays stable for log-grep dashboards.

    Dashboards filter on the leading prefix ``"drift summary: missing artifact"``;
    breaking that prefix would silently break those dashboards.
    """
    # Pin the template literal first so the constant itself can't drift.
    assert _DRIFT_ARTIFACT_MISSING_WARNING == (
        "drift summary: missing artifact %s for slug=%s but embeddings exist on disk"
    )

    paths = _paths(tmp_path)
    slug = "format-pin"
    _seed_embedding_dir(paths, slug)

    caplog.set_level(logging.WARNING, logger="forensics.analysis.drift")
    load_drift_summary(slug, paths, settings=_settings(), mode=AnalysisMode(exploratory=True))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "expected at least one WARNING when artifacts are missing and embeddings exist"
    for record in warnings:
        assert record.message.startswith("drift summary: missing artifact "), (
            f"log-grep dashboards key on the prefix; got {record.message!r}"
        )
        assert f"slug={slug}" in record.message, (
            f"WARNING must include 'slug=<slug>' for dashboard filtering; got {record.message!r}"
        )
        assert "embeddings exist on disk" in record.message, (
            f"WARNING must explain why this is unexpected; got {record.message!r}"
        )
