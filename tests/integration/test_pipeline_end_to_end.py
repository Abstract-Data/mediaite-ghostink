"""End-to-end pipeline smoke: seeded DB → extract → analyze → optional Quarto report.

Scrape is not invoked; the SQLite corpus is built in-process. Network is unused.

When ``quarto`` is on ``PATH``, renders ``index.qmd`` into ``data/reports/`` after
analysis prerequisites pass. CI images without Quarto still validate extract +
analysis + ``comparison_report.json`` (the target-role regression gate).
"""

from __future__ import annotations

import importlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from tests.integration.fixtures.e2e.corpus_seed import seed_two_regime_corpus

from forensics.analysis.orchestrator import run_full_analysis
from forensics.config import get_settings
from forensics.features.pipeline import extract_all_features
from forensics.models.analysis import AnalysisResult, HypothesisTest
from forensics.models.report_args import ReportArgs
from forensics.paths import AnalysisArtifactPaths
from forensics.reporting import run_report
from forensics.survey.scoring import compute_composite_score

_FIXTURE_CONFIG = Path(__file__).resolve().parent / "fixtures" / "e2e" / "config.toml"
_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_pipeline_extract_analyze_comparison_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e2e_root = tmp_path / "workspace"
    (e2e_root / "data").mkdir(parents=True)
    cfg_dest = e2e_root / "config.toml"
    shutil.copyfile(_FIXTURE_CONFIG, cfg_dest)
    shutil.copyfile(_REPO_ROOT / "index.qmd", e2e_root / "index.qmd")
    shutil.copyfile(_REPO_ROOT / "quarto.yml", e2e_root / "quarto.yml")

    db_path = e2e_root / "data" / "articles.db"
    shift = seed_two_regime_corpus(db_path)

    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg_dest))

    def _fake_project_root() -> Path:
        return e2e_root

    _settings_mod = importlib.import_module("forensics.config.settings")
    monkeypatch.setattr(_settings_mod, "_project_root", _fake_project_root)

    settings = get_settings()
    assert settings.db_path == db_path

    n = extract_all_features(
        db_path,
        settings,
        skip_embeddings=True,
        project_root=e2e_root,
        show_rich_progress=False,
    )
    assert n > 0

    paths = AnalysisArtifactPaths.from_project(e2e_root, db_path)
    for slug in ("fixture-target", "fixture-control"):
        p = paths.features_parquet(slug)
        assert p.is_file(), f"missing features parquet for {slug}"
        frame = pl.read_parquet(p)
        assert "ttr" in frame.columns
        assert "flesch_kincaid" in frame.columns
        assert "ai_marker_frequency" in frame.columns

    results = run_full_analysis(paths, settings, exploratory=True, max_workers=1)
    assert "fixture-target" in results
    assert "fixture-control" in results

    target_result_path = paths.result_json("fixture-target")
    assert target_result_path.is_file()
    target_ar = AnalysisResult.model_validate_json(target_result_path.read_text(encoding="utf-8"))
    control_ar = AnalysisResult.model_validate_json(
        paths.result_json("fixture-control").read_text(encoding="utf-8")
    )

    window_lo = shift - timedelta(days=30)
    window_hi = shift + timedelta(days=30)

    def _as_utc(ts: datetime) -> datetime:
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC)

    near_shift = [
        cp for cp in target_ar.change_points if window_lo <= _as_utc(cp.timestamp) <= window_hi
    ]
    assert near_shift, (
        "expected at least one evidence-filtered changepoint near seeded regime shift "
        f"({window_lo.isoformat()} .. {window_hi.isoformat()}); got {target_ar.change_points!r}"
    )

    assert not control_ar.change_points, (
        "single-regime control should not emit evidence-filtered changepoints; got "
        f"{control_ar.change_points!r}"
    )

    # ``compute_composite_score(...).convergence_score`` applies Phase-15 J6 gates
    # (AI-marker-family windows, post-2022-11-30 starts, …) that can zero both
    # scores on small fixtures. Sum of window ``convergence_ratio`` stays a
    # direct measure of multi-feature agreement from the same pipeline output.
    target_window_signal = sum(w.convergence_ratio for w in target_ar.convergence_windows)
    control_window_signal = sum(w.convergence_ratio for w in control_ar.convergence_windows)
    assert target_window_signal > control_window_signal
    assert target_window_signal >= 0.5

    target_conv = compute_composite_score(target_ar).convergence_score
    control_conv = compute_composite_score(control_ar).convergence_score
    assert target_conv >= control_conv

    hyp_path = paths.hypothesis_tests_json("fixture-target")
    assert hyp_path.is_file()
    hyp_raw = json.loads(hyp_path.read_text(encoding="utf-8"))
    assert isinstance(hyp_raw, list)
    if hyp_raw:
        HypothesisTest.from_legacy(hyp_raw[0])

    comparison_path = paths.comparison_report_json()
    assert comparison_path.is_file()
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    targets = comparison.get("targets") or {}
    assert isinstance(targets, dict)
    assert "fixture-target" in targets
    assert targets["fixture-target"], "comparison targets.fixture-target must be non-empty"

    monkeypatch.setattr("forensics.reporting.get_project_root", _fake_project_root)
    quarto = shutil.which("quarto")
    if quarto is None:
        return
    code = run_report(
        ReportArgs(
            notebook="index.qmd",
            report_format="html",
            verify=False,
        )
    )
    assert code == 0
    reports_dir = e2e_root / "data" / "reports"
    assert reports_dir.is_dir()
    assert any(reports_dir.iterdir()), (
        "quarto should write at least one artifact under data/reports/"
    )


@pytest.mark.integration
def test_get_settings_reflects_env_after_cache_clear(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing FORENSICS_CONFIG_FILE must not stick while the LRU cache still holds."""
    cfg_a = tmp_path / "a.toml"
    cfg_b = tmp_path / "b.toml"
    base = (
        '[[authors]]\nname = "A"\nslug = "a"\noutlet = "mediaite.com"\n'
        'role = "target"\narchive_url = "https://www.mediaite.com/author/a/"\n'
        "baseline_start = 2020-01-01\nbaseline_end = 2024-12-31\n\n"
        "[scraping]\n\n[analysis]\n\n[features]\n\n[report]\n"
    )
    cfg_a.write_text(base, encoding="utf-8")
    cfg_b.write_text(
        base.replace('slug = "a"', 'slug = "b"').replace('name = "A"', 'name = "B"'),
        encoding="utf-8",
    )
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg_a))
    get_settings.cache_clear()
    first = get_settings()
    assert first.authors[0].slug == "a"
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg_b))
    get_settings.cache_clear()
    second = get_settings()
    assert second.authors[0].slug == "b"
    assert first is not second
