"""Resilience of isolated parallel author refresh (PR94 / critical item 1)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from forensics.analysis.orchestrator.parallel import (
    IsolatedAuthorAnalysis,
    _run_isolated_author_jobs,
)
from forensics.config.settings import AnalysisConfig, ForensicsSettings
from forensics.models.analysis import AnalysisResult
from forensics.paths import AnalysisArtifactPaths


def _minimal_result(author_id: str) -> AnalysisResult:
    return AnalysisResult(
        author_id=author_id,
        run_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        config_hash="test",
        change_points=[],
    )


def test_isolated_refresh_continues_after_worker_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = AnalysisArtifactPaths.from_layout(
        tmp_path,
        tmp_path / "articles.db",
        tmp_path / "features",
        tmp_path / "embeddings",
    )
    cfg = ForensicsSettings(authors=[], analysis=AnalysisConfig())

    good: list[str] = []

    def fake_worker(slug: str, *args: object, **kwargs: object) -> IsolatedAuthorAnalysis | None:
        if slug == "bad":
            raise RuntimeError("boom")
        good.append(slug)
        adir = tmp_path / "iso" / slug
        adir.mkdir(parents=True)
        return IsolatedAuthorAnalysis(
            slug=slug,
            analysis_dir=adir,
            result=_minimal_result("aid"),
            stage_timings={},
        )

    monkeypatch.setattr(
        "forensics.analysis.orchestrator.parallel._isolated_author_worker",
        fake_worker,
    )

    out = _run_isolated_author_jobs(
        paths,
        cfg,
        ["ok-a", "bad", "ok-b"],
        run_id="run-test",
        max_workers=1,
        probability_trajectory_by_slug={},
        exploratory=True,
        allow_pre_phase16_embeddings=False,
    )

    assert {item.slug for item in out} == {"ok-a", "ok-b"}
    assert good == ["ok-a", "ok-b"]
    err = paths.scrape_errors_path / "isolated_refresh_bad.json"
    assert err.is_file()
    payload = err.read_text(encoding="utf-8")
    assert "boom" in payload
    assert "bad" in payload
