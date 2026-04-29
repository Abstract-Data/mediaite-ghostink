"""``forensics analyze --compare-pair`` and explicit target/control wiring.

Exercises three boundaries:

1. ``_parse_compare_pair`` returns ``None`` for the legacy bool flow and a
   typed pair otherwise — malformed input raises ``typer.BadParameter`` so
   operators get a clear error.
2. ``_resolve_targets_and_controls`` honours the explicit pair, bypassing
   the configured ``settings.authors`` role assignments.
3. ``run_compare_only`` drives ``compare_target_to_controls`` for the pair
   and writes the resulting report to ``comparison_report.json``.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import polars as pl
import pytest
import typer

from forensics.analysis import orchestrator as orch_mod
from forensics.analysis.orchestrator import (
    AnalysisMode,
    _resolve_max_workers,
    _resolve_parallel_refresh_workers,
    _resolve_targets_and_controls,
    run_compare_only,
)
from forensics.cli.analyze import _parse_compare_pair
from forensics.config import get_settings
from forensics.models import Author
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.parquet import write_parquet_atomic
from forensics.storage.repository import Repository, init_db
from forensics.utils.provenance import compute_analysis_config_hash

_PAIR_CONFIG_TOML = """
[[authors]]
name = "Target One"
slug = "tgt1"
outlet = "mediaite.com"
role = "target"
archive_url = "https://www.mediaite.com/author/tgt1/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[[authors]]
name = "Control One"
slug = "ctrl1"
outlet = "mediaite.com"
role = "control"
archive_url = "https://www.mediaite.com/author/ctrl1/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[[authors]]
name = "Spare Author"
slug = "spare"
outlet = "mediaite.com"
role = "control"
archive_url = "https://www.mediaite.com/author/spare/"
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


def _write_current_result(paths: AnalysisArtifactPaths, slug: str, settings) -> None:
    paths.result_json(slug).write_text(
        json.dumps({"config_hash": compute_analysis_config_hash(settings)}),
        encoding="utf-8",
    )


@pytest.fixture
def pair_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AnalysisArtifactPaths, Path]:
    cfg = tmp_path / "config.toml"
    cfg.write_text(_PAIR_CONFIG_TOML.strip() + "\n", encoding="utf-8")
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
        _author_row(author_id="author-tgt1", slug="tgt1", role="target"),
        _author_row(author_id="author-ctrl1", slug="ctrl1", role="control"),
        _author_row(author_id="author-spare", slug="spare", role="control"),
    )
    with Repository(db) as repo:
        repo.ensure_schema()
        for a in authors:
            repo.upsert_author(a)

    write_parquet_atomic(feat / "tgt1.parquet", _feature_frame("author-tgt1", ttr_base=0.55))
    write_parquet_atomic(feat / "ctrl1.parquet", _feature_frame("author-ctrl1", ttr_base=0.40))
    write_parquet_atomic(feat / "spare.parquet", _feature_frame("author-spare", ttr_base=0.42))

    paths = AnalysisArtifactPaths.from_layout(root, db, feat, emb, analysis_dir=ana)
    yield paths, cfg
    get_settings.cache_clear()


def test_parse_compare_pair_returns_none_for_missing_value() -> None:
    """``--compare-pair`` not supplied → ``None`` (legacy compare-only path)."""
    assert _parse_compare_pair(None) is None


def test_parse_compare_pair_splits_target_and_control() -> None:
    """Well-formed ``TARGET,CONTROL`` parses to a tuple, whitespace stripped."""
    assert _parse_compare_pair("isaac-schorr,john-doe") == ("isaac-schorr", "john-doe")
    assert _parse_compare_pair("  tgt , ctrl ") == ("tgt", "ctrl")


def test_parse_compare_pair_rejects_malformed_input() -> None:
    """Empty slugs or wrong arity raise ``typer.BadParameter`` for clear UX."""
    for bad in ("only-one", "a,b,c", ",ctrl", "tgt,", ",", ""):
        with pytest.raises(typer.BadParameter):
            _parse_compare_pair(bad)


def test_resolve_targets_and_controls_honors_explicit_pair(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """Explicit ``compare_pair`` wins over ``settings.authors`` role assignments."""
    _paths, _cfg = pair_project
    settings = get_settings()

    # Without compare_pair: configured roles drive the resolution.
    targets, controls = _resolve_targets_and_controls(settings, author_slug=None)
    assert targets == ["tgt1"]
    assert set(controls) == {"ctrl1", "spare"}

    # With compare_pair: only the named pair is returned, regardless of role.
    targets, controls = _resolve_targets_and_controls(
        settings,
        author_slug=None,
        compare_pair=("spare", "ctrl1"),
    )
    assert targets == ["spare"]
    assert controls == ["ctrl1"]


def test_run_compare_only_with_pair_writes_report(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """``run_compare_only(compare_pair=...)`` runs the explicit pair and writes the report."""
    paths, _cfg = pair_project
    settings = get_settings()
    # Pre-seed empty changepoints so compare_target_to_controls has data to load.
    for slug in ("tgt1", "ctrl1", "spare"):
        paths.changepoints_json(slug).write_text("[]", encoding="utf-8")
        _write_current_result(paths, slug, settings)

    out = run_compare_only(
        settings,
        paths=paths,
        compare_pair=("spare", "ctrl1"),
        mode=AnalysisMode(exploratory=True),
    )
    # Only the explicit target is in the output — the configured target tgt1 is skipped.
    assert set(out["targets"]) == {"spare"}
    assert "feature_comparisons" in out["targets"]["spare"]

    report_path = paths.comparison_report_json()
    assert report_path.is_file()
    disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert set(disk["targets"]) == {"spare"}


def test_resolve_max_workers_precedence(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """Override > config > ``cpu_count - 1``; never returns < 1."""
    settings = get_settings()
    # Explicit override wins regardless of config.
    assert _resolve_max_workers(settings, 4) == 4
    assert _resolve_max_workers(settings, 1) == 1
    # Override of 0 / negative clamps to >= 1 so the serial fallback fires.
    assert _resolve_max_workers(settings, 0) == 1
    assert _resolve_max_workers(settings, -3) == 1
    # Config value (8) is read when no override is supplied.
    bumped = settings.model_copy(
        update={"analysis": settings.analysis.model_copy(update={"max_workers": 8})}
    )
    assert _resolve_max_workers(bumped, None) == 8
    # No override and no config falls back to ``cpu_count - 1`` (>= 1).
    fallback = _resolve_max_workers(settings, None)
    assert fallback == max(1, (os.cpu_count() or 1) - 1)


def test_resolve_parallel_refresh_workers_is_conservative_by_default(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """Parallel refresh defaults to at most three workers unless explicitly configured."""
    settings = get_settings()
    assert _resolve_parallel_refresh_workers(settings, None) == min(
        3,
        max(1, (os.cpu_count() or 1) - 1),
    )
    assert _resolve_parallel_refresh_workers(settings, 5) == 5

    configured = settings.model_copy(
        update={"analysis": settings.analysis.model_copy(update={"max_workers": 6})}
    )
    assert _resolve_parallel_refresh_workers(configured, None) == 6


def test_run_full_analysis_merges_run_metadata_in_single_write(
    pair_project: tuple[AnalysisArtifactPaths, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression (PR94 item 6): avoid multiple read/merge/write passes on ``run_metadata.json``."""
    from forensics.analysis.orchestrator import run_full_analysis
    from forensics.storage import json_io

    counts = {"run_metadata": 0}
    real_write = json_io.write_json_artifact

    def _counting_write(path: Path, payload: object) -> None:
        if path.name == "run_metadata.json":
            counts["run_metadata"] += 1
        real_write(path, payload)

    monkeypatch.setattr(json_io, "write_json_artifact", _counting_write)
    monkeypatch.setattr(
        "forensics.analysis.orchestrator.runner.write_json_artifact",
        _counting_write,
    )
    monkeypatch.setattr(
        "forensics.analysis.orchestrator.staleness.write_json_artifact",
        _counting_write,
    )
    paths, _cfg = pair_project
    settings = get_settings()
    for slug in ("ctrl1", "spare"):
        _write_current_result(paths, slug, settings)
    run_full_analysis(
        paths, settings, author_slug="tgt1", max_workers=1, mode=AnalysisMode(exploratory=True)
    )
    assert counts["run_metadata"] == 1


def test_run_full_analysis_timings_out_populates_per_stage_buckets(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """``timings_out`` is filled in-place with ``per_author`` + ``compare`` + ``total``."""
    from forensics.analysis.orchestrator import AnalysisTimings, run_full_analysis

    paths, _cfg = pair_project
    settings = get_settings()
    for slug in ("ctrl1", "spare"):
        _write_current_result(paths, slug, settings)
    timings = AnalysisTimings()
    run_full_analysis(
        paths,
        settings,
        author_slug="tgt1",
        max_workers=1,
        timings_out=timings,
        mode=AnalysisMode(exploratory=True),
    )
    assert timings.total > 0.0
    assert "tgt1" in timings.per_author
    stage_keys = set(timings.per_author["tgt1"])
    assert {"extract", "changepoint", "drift", "convergence", "hypothesis_tests"} <= stage_keys
    # Each per-stage bucket is non-negative; at least the extract bucket should fire.
    for stage, seconds in timings.per_author["tgt1"].items():
        assert seconds >= 0.0, f"{stage}={seconds}"
    assert timings.compare >= 0.0


def test_run_full_analysis_parallel_dispatch_returns_results(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """``max_workers >= 2`` exercises the ProcessPool branch and returns per-author results."""
    from forensics.analysis.orchestrator import run_full_analysis

    paths, _cfg = pair_project
    settings = get_settings()
    results = run_full_analysis(paths, settings, max_workers=2, mode=AnalysisMode(exploratory=True))
    # All three configured authors should have feature parquets; the worker
    # path writes per-author artifacts and returns the assembled dict.
    assert set(results) == {"tgt1", "ctrl1", "spare"}
    for slug in ("tgt1", "ctrl1", "spare"):
        result_path = paths.analysis_dir / f"{slug}_result.json"
        assert result_path.is_file()


def test_per_author_worker_returns_assembled_and_timings(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """Direct invocation of the ProcessPool worker (in-process so coverage tracks it)."""
    from forensics.analysis.orchestrator import _per_author_worker

    paths, _cfg = pair_project
    settings = get_settings()
    slug, assembled, stage_timings = _per_author_worker(
        "tgt1",
        paths.db_path,
        paths,
        settings,
        {},
        AnalysisMode(exploratory=True),
    )
    assert slug == "tgt1"
    assert assembled is not None
    assert assembled.author_id == "author-tgt1"
    # Each per-stage bucket lands in the timings dict.
    assert {"extract", "changepoint", "drift", "convergence", "hypothesis_tests"} <= set(
        stage_timings
    )
    # The worker writes the per-author artifacts in-place (atomic rename).
    assert (paths.analysis_dir / "tgt1_result.json").is_file()


def test_per_author_worker_handles_unknown_slug(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """Worker logs + returns ``(slug, None, {})`` instead of raising on missing authors."""
    from forensics.analysis.orchestrator import _per_author_worker

    paths, _cfg = pair_project
    settings = get_settings()
    slug, assembled, stage_timings = _per_author_worker(
        "ghost-author",
        paths.db_path,
        paths,
        settings,
        {},
        AnalysisMode(),
    )
    assert slug == "ghost-author"
    assert assembled is None
    assert stage_timings == {}


def test_isolated_author_worker_does_not_write_canonical_artifacts(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """The isolated worker writes under ``parallel/<run>/<slug>`` only."""
    from forensics.analysis.orchestrator import _isolated_author_worker

    paths, _cfg = pair_project
    settings = get_settings()
    isolated = _isolated_author_worker(
        "tgt1", paths, settings, {}, "run-1", AnalysisMode(exploratory=True)
    )

    assert isolated is not None
    assert isolated.analysis_dir == paths.analysis_dir / "parallel" / "run-1" / "tgt1"
    assert (isolated.analysis_dir / "tgt1_result.json").is_file()
    assert not paths.result_json("tgt1").exists()
    assert not paths.run_metadata_json().exists()


def test_run_parallel_author_refresh_promotes_after_validation(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """Parallel refresh stages privately, then promotes per-author artifacts once valid."""
    from forensics.analysis.orchestrator import run_parallel_author_refresh

    paths, _cfg = pair_project
    settings = get_settings()

    results = run_parallel_author_refresh(
        paths, settings, max_workers=1, mode=AnalysisMode(exploratory=True)
    )

    assert set(results) == {"tgt1", "ctrl1", "spare"}
    for slug in results:
        assert paths.result_json(slug).is_file()
        assert (paths.analysis_dir / "parallel").is_dir()
    assert paths.comparison_report_json().is_file()
    assert paths.run_metadata_json().is_file()


def test_validate_and_promote_isolated_outputs_is_all_or_nothing(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """A bad isolated author output must not partially promote earlier valid outputs."""
    paths, _cfg = pair_project
    settings = get_settings()
    valid = orch_mod._isolated_author_worker(
        "tgt1", paths, settings, {}, "run-validation", AnalysisMode(exploratory=True)
    )
    invalid = orch_mod._isolated_author_worker(
        "ctrl1", paths, settings, {}, "run-validation", AnalysisMode(exploratory=True)
    )
    assert valid is not None
    assert invalid is not None

    (invalid.analysis_dir / "ctrl1_convergence.json").unlink()

    with pytest.raises(ValueError, match="missing isolated companion artifacts"):
        orch_mod._validate_and_promote_isolated_outputs([valid, invalid], paths, settings)

    assert not paths.result_json("tgt1").exists()
    assert not paths.result_json("ctrl1").exists()


def test_validate_and_promote_isolated_outputs_rejects_stale_config_hash(
    pair_project: tuple[AnalysisArtifactPaths, Path],
) -> None:
    """A stale isolated result hash is rejected before any canonical promotion."""
    paths, _cfg = pair_project
    settings = get_settings()
    valid = orch_mod._isolated_author_worker(
        "tgt1", paths, settings, {}, "run-stale", AnalysisMode(exploratory=True)
    )
    stale = orch_mod._isolated_author_worker(
        "ctrl1", paths, settings, {}, "run-stale", AnalysisMode(exploratory=True)
    )
    assert valid is not None
    assert stale is not None

    stale_result_path = stale.analysis_dir / "ctrl1_result.json"
    payload = json.loads(stale_result_path.read_text(encoding="utf-8"))
    payload["config_hash"] = "stale-config"
    stale_result_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="stale isolated result for ctrl1"):
        orch_mod._validate_and_promote_isolated_outputs([valid, stale], paths, settings)

    assert not paths.result_json("tgt1").exists()
    assert not paths.result_json("ctrl1").exists()
    assert not paths.comparison_report_json().exists()
    assert not paths.run_metadata_json().exists()


def test_parallel_refresh_rebuilds_shared_artifacts_after_promotion(
    pair_project: tuple[AnalysisArtifactPaths, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared artifacts are absent through validation and created after promotion."""
    paths, _cfg = pair_project
    settings = get_settings()
    real_validate_and_promote = orch_mod._validate_and_promote_isolated_outputs
    observed: dict[str, bool] = {}

    def wrapped_validate_and_promote(*args, **kwargs) -> None:
        isolated_outputs, active_paths, _active_settings = args
        assert not active_paths.comparison_report_json().exists()
        assert not active_paths.run_metadata_json().exists()
        for isolated in isolated_outputs:
            assert not active_paths.result_json(isolated.slug).exists()

        real_validate_and_promote(*args, **kwargs)

        for isolated in isolated_outputs:
            assert active_paths.result_json(isolated.slug).is_file()
        assert not active_paths.comparison_report_json().exists()
        assert not active_paths.run_metadata_json().exists()
        observed["promoted_before_shared_rebuild"] = True

    import forensics.analysis.orchestrator.refresh as refresh_mod

    monkeypatch.setattr(
        refresh_mod,
        "_validate_and_promote_isolated_outputs",
        wrapped_validate_and_promote,
    )

    results = orch_mod.run_parallel_author_refresh(
        paths, settings, max_workers=1, mode=AnalysisMode(exploratory=True)
    )

    assert set(results) == {"tgt1", "ctrl1", "spare"}
    assert observed == {"promoted_before_shared_rebuild": True}
    assert paths.comparison_report_json().is_file()
    assert paths.run_metadata_json().is_file()
