"""Pipeline observer hooks, Rich opt-out, and Textual dashboard smoke tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from forensics.models.author import AuthorManifest
from forensics.progress import managed_rich_observer
from forensics.progress.observer import PipelineRunPhase, PipelineStage


class RecordingObserver:
    """Captures observer call order for assertions."""

    def __init__(self) -> None:
        self.events: list[tuple[str, ...]] = []

    def pipeline_stage_start(self, stage: PipelineStage) -> None:
        self.events.append(("pipeline_stage_start", stage.value))

    def pipeline_stage_end(self, stage: PipelineStage) -> None:
        self.events.append(("pipeline_stage_end", stage.value))

    def metadata_author_started(self, slug: str) -> None:
        self.events.append(("metadata_author_started", slug))

    def metadata_author_done(self, slug: str, inserted_count: int) -> None:
        self.events.append(("metadata_author_done", slug, str(inserted_count)))

    def fetch_progress(self, done: int, total: int) -> None:
        self.events.append(("fetch_progress", str(done), str(total)))

    def pipeline_run_phase_start(self, phase: PipelineRunPhase) -> None:
        self.events.append(("pipeline_run_phase_start", phase.value))

    def pipeline_run_phase_end(self, phase: PipelineRunPhase) -> None:
        self.events.append(("pipeline_run_phase_end", phase.value))

    def survey_author_started(self, slug: str, index: int, total: int) -> None:
        self.events.append(("survey_author_started", slug, str(index), str(total)))

    def survey_author_finished(self, slug: str, error: str | None = None) -> None:
        self.events.append(("survey_author_finished", slug, error or ""))


@pytest.mark.asyncio
async def test_collect_metadata_emits_author_events_in_order(
    tmp_path: Path,
    forensics_config_path: Path,
    tmp_db: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from forensics.scraper import crawler

    monkeypatch.setattr(crawler, "get_project_root", lambda: tmp_path)
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    m = AuthorManifest(
        wp_id=1,
        name="Fixture Author",
        slug="fixture-author",
        total_posts=3,
        discovered_at=datetime.now(UTC),
    )
    (data / "authors_manifest.jsonl").write_text(m.model_dump_json() + "\n", encoding="utf-8")

    class _DummyClient:
        async def __aenter__(self) -> _DummyClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(crawler, "create_scraping_client", lambda _scraping: _DummyClient())

    async def _fake_ingest(*_a: object, **_kw: object) -> int:
        return 0

    monkeypatch.setattr(crawler, "_ingest_author_posts", _fake_ingest)

    obs = RecordingObserver()
    inserted = await crawler.collect_article_metadata(tmp_db, settings, observer=obs)
    assert inserted == 0
    assert obs.events == [
        ("metadata_author_started", "fixture-author"),
        ("metadata_author_done", "fixture-author", "0"),
    ]


def test_managed_rich_observer_false_yields_none() -> None:
    with managed_rich_observer(False) as obs:
        assert obs is None


def test_dashboard_cli_rejects_no_progress(forensics_config_path: Path) -> None:
    from typer.testing import CliRunner

    from forensics.cli import app

    runner = CliRunner()
    r = runner.invoke(app, ["--no-progress", "dashboard"])
    assert r.exit_code == 1
    combined = (r.stdout or "") + (r.stderr or "")
    assert "no-progress" in combined.lower() or "omit" in combined.lower()


def test_run_author_batches_skips_rich_when_disabled(
    tmp_path: Path,
    forensics_config_path: Path,
    tmp_db: Path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from forensics.features import pipeline as fp
    from forensics.paths import AnalysisArtifactPaths

    def _boom() -> object:
        raise AssertionError("_make_progress must not be called when use_rich_progress is False")

    monkeypatch.setattr(fp, "_make_progress", _boom)
    paths = AnalysisArtifactPaths.from_project(tmp_path, tmp_db)
    paths.features_dir.mkdir(parents=True, exist_ok=True)
    paths.embeddings_dir.mkdir(parents=True, exist_ok=True)

    fp._run_author_batches(
        by_author={},
        repo=MagicMock(),
        nlp=None,
        settings=settings,
        paths=paths,
        skip_embeddings=True,
        use_rich_progress=False,
    )


@pytest.mark.asyncio
async def test_pipeline_dashboard_mounts_and_observer_updates_ui() -> None:
    pytest.importorskip("textual")
    from textual.widgets import DataTable, Static

    from forensics.progress.observer import PipelineObserver
    from forensics.tui.pipeline_app import PipelineDashboardApp

    def _runner(obs: PipelineObserver) -> int:
        obs.pipeline_run_phase_start(PipelineRunPhase.SCRAPE)
        obs.metadata_author_started("alpha")
        obs.metadata_author_done("alpha", 2)
        obs.pipeline_run_phase_end(PipelineRunPhase.SCRAPE)
        return 0

    app = PipelineDashboardApp(pipeline_runner=_runner)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.05)
        assert isinstance(app.query_one("#authors", DataTable), DataTable)
        # Thread worker: allow completion and call_from_thread UI updates.
        for _ in range(50):
            await pilot.pause(0.1)
            scrape = app.query_one("#phase-scrape", Static)
            if "done" in str(scrape.content):
                break
        assert "done" in str(app.query_one("#phase-scrape", Static).content)
        tbl = app.query_one("#authors", DataTable)
        assert tbl.row_count == 1
        await pilot.press("q")
