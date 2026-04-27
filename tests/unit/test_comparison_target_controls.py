"""Target-vs-control comparison and ``run_compare_only`` (orchestrator) coverage."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import polars as pl
import pytest

from forensics.analysis.comparison import compare_target_to_controls
from forensics.analysis.orchestrator import run_compare_only
from forensics.config import get_settings
from forensics.models import Author
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.parquet import write_parquet_atomic
from forensics.storage.repository import Repository, init_db
from forensics.utils.provenance import compute_analysis_config_hash

_COMPARE_CONFIG_TOML = """
[[authors]]
name = "Target One"
slug = "t1"
outlet = "mediaite.com"
role = "target"
archive_url = "https://www.mediaite.com/author/t1/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[[authors]]
name = "Control One"
slug = "c1"
outlet = "mediaite.com"
role = "control"
archive_url = "https://www.mediaite.com/author/c1/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[[authors]]
name = "Control Two"
slug = "c2"
outlet = "mediaite.com"
role = "control"
archive_url = "https://www.mediaite.com/author/c2/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[scraping]
[analysis]
[report]
"""


def _author_row(
    *,
    author_id: str,
    slug: str,
    role: Literal["target", "control"],
) -> Author:
    return Author(
        id=author_id,
        name=slug.upper(),
        slug=slug,
        outlet="mediaite.com",
        role=role,
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url=f"https://www.mediaite.com/author/{slug}/",
    )


def _feature_frame(author_id: str, *, ttr_base: float, n: int = 6) -> pl.DataFrame:
    """Minimal rows: ``timestamp`` + ``ttr`` satisfy comparison + parquet sort contract."""
    rows = []
    for i in range(n):
        rows.append(
            {
                "article_id": f"art-{author_id}-{i}",
                "author_id": author_id,
                "timestamp": datetime(2024, 1, 1 + i, tzinfo=UTC),
                "ttr": float(ttr_base + i * 0.02),
            }
        )
    return pl.DataFrame(rows)


def _write_current_result_hashes(paths: AnalysisArtifactPaths, slugs: tuple[str, ...]) -> None:
    current_hash = compute_analysis_config_hash(get_settings())
    for slug in slugs:
        paths.result_json(slug).write_text(
            json.dumps({"config_hash": current_hash}),
            encoding="utf-8",
        )


@pytest.fixture
def compare_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AnalysisArtifactPaths, Path]:
    cfg = tmp_path / "config.toml"
    cfg.write_text(_COMPARE_CONFIG_TOML.strip() + "\n", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg))
    get_settings.cache_clear()

    root = tmp_path / "proj"
    data = root / "data"
    feat = data / "features"
    ana = data / "analysis"
    emb = data / "embeddings"
    db = data / "articles.db"
    for d in (feat, ana, emb):
        d.mkdir(parents=True, exist_ok=True)
    init_db(db)

    authors = (
        _author_row(author_id="author-t1", slug="t1", role="target"),
        _author_row(author_id="author-c1", slug="c1", role="control"),
        _author_row(author_id="author-c2", slug="c2", role="control"),
    )
    with Repository(db) as repo:
        repo.ensure_schema()
        for a in authors:
            repo.upsert_author(a)

    write_parquet_atomic(feat / "t1.parquet", _feature_frame("author-t1", ttr_base=0.55))
    write_parquet_atomic(feat / "c1.parquet", _feature_frame("author-c1", ttr_base=0.40))
    write_parquet_atomic(feat / "c2.parquet", _feature_frame("author-c2", ttr_base=0.42))

    paths = AnalysisArtifactPaths.from_layout(root, db, feat, emb, analysis_dir=ana)
    yield paths, cfg
    get_settings.cache_clear()


def test_compare_target_to_controls_returns_stable_shape(
    compare_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    paths, _cfg_path = compare_project
    settings = get_settings()
    memory = {"t1": [], "c1": [], "c2": []}
    _write_current_result_hashes(paths, ("t1", "c1", "c2"))
    out = compare_target_to_controls(
        "t1",
        ["c1", "c2"],
        paths,
        settings=settings,
        changepoints_memory=memory,
    )
    assert set(out) == {
        "feature_comparisons",
        "feature_coverage_diagnostics",
        "control_change_points",
        "control_drift_scores",
        "editorial_vs_author_signal",
    }
    assert isinstance(out["feature_comparisons"], dict)
    assert "ttr" in out["feature_comparisons"]
    fc = out["feature_comparisons"]["ttr"]["all"]
    assert "p_value" in fc and "t_stat" in fc
    assert out["control_change_points"] == {"c1": [], "c2": []}
    assert out["control_drift_scores"] == {"c1": None, "c2": None}
    assert isinstance(out["editorial_vs_author_signal"], float)
    assert 0.0 <= out["editorial_vs_author_signal"] <= 1.0


def test_run_compare_only_writes_comparison_report_json(
    compare_project: tuple[AnalysisArtifactPaths, Path], caplog: pytest.LogCaptureFixture
) -> None:
    paths, _cfg_path = compare_project
    settings = get_settings()
    for slug in ("t1", "c1", "c2"):
        paths.changepoints_json(slug).write_text("[]", encoding="utf-8")
    _write_current_result_hashes(paths, ("t1", "c1", "c2"))

    report_path = paths.comparison_report_json()
    assert not report_path.is_file()

    out = run_compare_only(settings, paths=paths, author_slug=None)
    assert report_path.is_file()
    disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert disk == out
    assert "targets" in out and "t1" in out["targets"]
    assert "feature_comparisons" in out["targets"]["t1"]


def test_comparison_report_non_empty_when_configured_target_exists(
    compare_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """T-01 — regression guard: comparison must emit real stats when a target has features."""
    paths, _cfg_path = compare_project
    settings = get_settings()
    for slug in ("t1", "c1", "c2"):
        paths.changepoints_json(slug).write_text("[]", encoding="utf-8")
    _write_current_result_hashes(paths, ("t1", "c1", "c2"))

    out = run_compare_only(settings, paths=paths, author_slug=None)
    t1 = out["targets"]["t1"]
    fc = t1["feature_comparisons"]
    assert fc, "feature_comparisons must not be empty when target parquet has rows"
    sample = next(iter(fc.values()))
    assert "all" in sample
    assert "p_value" in sample["all"] and "t_stat" in sample["all"]


def test_run_compare_only_forces_slug_with_warning(
    compare_project: tuple[AnalysisArtifactPaths, Path], caplog: pytest.LogCaptureFixture
) -> None:
    """``author_slug`` not in configured targets → warning + single-slug compare (orchestrator)."""
    paths, _cfg_path = compare_project
    settings = get_settings()
    orphan = _author_row(author_id="author-orph", slug="orph", role="control")
    with Repository(paths.db_path) as repo:
        repo.upsert_author(orphan)
    write_parquet_atomic(
        paths.features_dir / "orph.parquet",
        _feature_frame("author-orph", ttr_base=0.50),
    )
    paths.changepoints_json("orph").write_text("[]", encoding="utf-8")
    for slug in ("c1", "c2"):
        paths.changepoints_json(slug).write_text("[]", encoding="utf-8")
    _write_current_result_hashes(paths, ("orph", "c1", "c2"))

    caplog.set_level("WARNING", logger="forensics.analysis.orchestrator")
    out = run_compare_only(settings, paths=paths, author_slug="orph")
    assert "orph" in out["targets"]
    assert any("compare-only" in r.message for r in caplog.records)


def test_compare_target_to_controls_filters_nan_values(
    compare_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    paths, _cfg_path = compare_project
    write_parquet_atomic(
        paths.features_dir / "t1.parquet",
        pl.DataFrame(
            {
                "article_id": [f"t-{i}" for i in range(5)],
                "author_id": ["author-t1"] * 5,
                "timestamp": [datetime(2024, 1, 1 + i, tzinfo=UTC) for i in range(5)],
                "ttr": [0.6, float("nan"), 0.7, 0.8, 0.9],
            }
        ),
    )
    write_parquet_atomic(
        paths.features_dir / "c1.parquet",
        pl.DataFrame(
            {
                "article_id": [f"c-{i}" for i in range(5)],
                "author_id": ["author-c1"] * 5,
                "timestamp": [datetime(2024, 1, 1 + i, tzinfo=UTC) for i in range(5)],
                "ttr": [0.3, 0.4, float("nan"), 0.5, 0.6],
            }
        ),
    )
    _write_current_result_hashes(paths, ("t1", "c1", "c2"))
    out = compare_target_to_controls(
        "t1",
        ["c1", "c2"],
        paths,
        settings=get_settings(),
        changepoints_memory={"t1": [], "c1": [], "c2": []},
    )
    fc = out["feature_comparisons"]["ttr"]["all"]
    assert fc["p_value"] == pytest.approx(fc["p_value"])
    assert "ttr" in out["feature_coverage_diagnostics"]["target"]["has_non_finite"]
