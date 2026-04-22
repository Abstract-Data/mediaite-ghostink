"""Tests for analysis path bundles, model cache helper, and comparison utilities."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.comparison import compute_signal_attribution
from forensics.models.analysis import ConvergenceWindow
from forensics.utils.model_cache import KeyedModelCache


def test_keyed_model_cache_reuses_factory() -> None:
    cache = KeyedModelCache()
    calls = {"n": 0}

    def factory() -> int:
        calls["n"] += 1
        return 42

    assert cache.get_or_load("k", factory) == 42
    assert cache.get_or_load("k", factory) == 42
    assert calls["n"] == 1
    cache.clear()
    assert cache.get_or_load("k", factory) == 42
    assert calls["n"] == 2


def test_analysis_artifact_paths_layout(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    db = tmp_path / "articles.db"
    feat = tmp_path / "f"
    emb = tmp_path / "e"
    ana = tmp_path / "custom_analysis"
    paths = AnalysisArtifactPaths.from_layout(root, db, feat, emb, analysis_dir=ana)
    assert paths.project_root == root
    assert paths.db_path == db
    assert paths.features_dir == feat
    assert paths.embeddings_dir == emb
    assert paths.analysis_dir == ana

    paths2 = AnalysisArtifactPaths.from_project(root, db)
    assert paths2.analysis_dir == root / "data" / "analysis"


def _window(start_d: int, end_d: int) -> ConvergenceWindow:
    return ConvergenceWindow(
        start_date=date(2024, 1, start_d),
        end_date=date(2024, 1, end_d),
        features_converging=["f1"],
        convergence_ratio=0.5,
        pipeline_a_score=0.1,
        pipeline_b_score=0.2,
    )


def test_compute_signal_attribution_empty_targets_controls() -> None:
    assert compute_signal_attribution([], {}) == 0.5
    tw = [_window(1, 5)]
    assert compute_signal_attribution(tw, {}) == 1.0


def test_compute_signal_attribution_overlap_logic() -> None:
    target = [_window(10, 20)]
    controls = {"c1": [_window(12, 18)], "c2": [_window(1, 5)]}
    out = compute_signal_attribution(target, controls)
    assert 0.0 <= out <= 1.0
