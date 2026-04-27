"""Confirmatory (non-exploratory) embedding drift input gates."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from forensics.analysis.drift import EmbeddingDriftInputsError
from forensics.analysis.orchestrator import AnalysisMode
from forensics.analysis.orchestrator.per_author import _load_drift_signals
from forensics.cli import app
from forensics.config.settings import AnalysisConfig, ForensicsSettings, ScrapingConfig
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.repository import Repository, init_db


def _paths(tmp_path: Path) -> AnalysisArtifactPaths:
    db_path = tmp_path / "data" / "articles.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    return AnalysisArtifactPaths.from_layout(
        tmp_path,
        db_path,
        tmp_path / "data" / "features",
        tmp_path / "data" / "embeddings",
    )


def _forensics_settings() -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(),
    )


@pytest.mark.integration
def test_load_drift_signals_insufficient_embeddings_confirmatory(
    tmp_path: Path,
    sample_author,
) -> None:
    paths = _paths(tmp_path)
    cfg = _forensics_settings()
    with Repository(paths.db_path) as repo:
        repo.upsert_author(sample_author)
    with pytest.raises(EmbeddingDriftInputsError, match="Insufficient article embeddings"):
        _load_drift_signals(
            sample_author.slug,
            sample_author.id,
            paths,
            cfg,
            mode=AnalysisMode(),
        )


@pytest.mark.integration
def test_load_drift_signals_exploratory_allows_empty_embeddings(
    tmp_path: Path,
    sample_author,
) -> None:
    paths = _paths(tmp_path)
    cfg = _forensics_settings()
    with Repository(paths.db_path) as repo:
        repo.upsert_author(sample_author)
    drift, baseline, vel, ai = _load_drift_signals(
        sample_author.slug,
        sample_author.id,
        paths,
        cfg,
        mode=AnalysisMode(exploratory=True),
    )
    assert drift is None
    assert baseline == []
    assert vel == []
    assert ai is None


@pytest.mark.integration
def test_analyze_cli_maps_embedding_drift_inputs_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``forensics analyze --drift`` maps :class:`EmbeddingDriftInputsError` to exit code 3."""
    from forensics import config as forensics_config

    project_root = tmp_path / "proj"
    (project_root / "data").mkdir(parents=True)
    db_path = project_root / "data" / "articles.db"
    init_db(db_path)
    cfg = project_root / "config.toml"
    cfg.write_text(
        "[[authors]]\n"
        'name = "A"\n'
        'slug = "a1"\n'
        'outlet = "mediaite.com"\n'
        'role = "target"\n'
        'archive_url = "https://www.mediaite.com/author/a1/"\n'
        "baseline_start = 2020-01-01\n"
        "baseline_end = 2023-12-31\n"
        "[scraping]\n[analysis]\n"
        "[chain_of_custody]\nverify_corpus_hash = false\n[report]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg))
    forensics_config.get_settings.cache_clear()
    monkeypatch.setattr("forensics.cli.analyze.get_project_root", lambda: project_root)
    monkeypatch.setattr(
        "forensics.cli.analyze.verify_preregistration",
        lambda _settings: type("PR", (), {"status": "ok", "message": "stub"})(),
    )
    monkeypatch.setattr(
        "forensics.cli.analyze.PipelineContext.resolve",
        lambda: type(
            "PC",
            (),
            {
                "record_audit": lambda self, *a, **k: "test-rid",
                "config_hash": "deadbeef",
            },
        )(),
    )

    def _raise_drift_inputs(*_args: object, **_kwargs: object) -> None:
        raise EmbeddingDriftInputsError("simulated missing embeddings for test")

    monkeypatch.setattr(
        "forensics.analysis.drift.run_drift_analysis",
        _raise_drift_inputs,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "--drift"], color=False)
    assert result.exit_code == 3, (result.stdout, result.stderr)
    assert "embedding_drift_inputs" in (result.stderr or "") or "simulated missing" in (
        result.stderr or ""
    )
    forensics_config.get_settings.cache_clear()
