"""Full-screen Textual dashboard for scrape → extract → analyze → report (or survey)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Header, RichLog, Static
from textual.worker import Worker, WorkerState

from forensics.progress.observer import PipelineObserver, PipelineRunPhase, PipelineStage

logger = logging.getLogger(__name__)

_PIPELINE_WORKER_NAME = "forensics-pipeline"

_PipelineRunner = Callable[[PipelineObserver], int]

_PHASE_LABELS: dict[str, str] = {
    PipelineRunPhase.SCRAPE.value: "Scrape",
    PipelineRunPhase.EXTRACT.value: "Extract",
    PipelineRunPhase.ANALYZE.value: "Analyze",
    PipelineRunPhase.REPORT.value: "Report",
    PipelineRunPhase.SURVEY_FINALIZE.value: "Finalize",
}

_SCRAPE_SUB: dict[str, str] = {
    PipelineStage.DISCOVER.value: "discover",
    PipelineStage.METADATA.value: "metadata",
    PipelineStage.FETCH.value: "fetch",
    PipelineStage.DEDUP.value: "dedup",
    PipelineStage.EXPORT.value: "export",
    PipelineStage.ARCHIVE.value: "archive",
}


class TextualPipelineObserver:
    """Marshals worker-thread observer calls onto the Textual loop (``call_from_thread``)."""

    live_ui_mode: Literal["textual"] = "textual"

    __slots__ = ("_app",)

    def __init__(self, app: PipelineDashboardApp) -> None:
        self._app = app

    def _dispatch(self, fn: Callable[[], None]) -> None:
        self._app.call_from_thread(fn)

    def pipeline_stage_start(self, stage: PipelineStage) -> None:
        label = _SCRAPE_SUB.get(stage.value, stage.value)
        self._dispatch(lambda: self._app._log_event(f"scrape stage: {label} ..."))

    def pipeline_stage_end(self, stage: PipelineStage) -> None:
        label = _SCRAPE_SUB.get(stage.value, stage.value)
        self._dispatch(lambda: self._app._log_event(f"scrape stage: {label} done"))

    def metadata_author_started(self, slug: str) -> None:
        self._dispatch(lambda s=slug: self._app._on_metadata_author_started(s))

    def metadata_author_done(self, slug: str, inserted_count: int) -> None:
        self._dispatch(lambda s=slug, n=inserted_count: self._app._on_metadata_author_done(s, n))

    def fetch_progress(self, done: int, total: int) -> None:
        self._dispatch(lambda d=done, t=total: self._app._log_event(f"fetch {d}/{t}"))

    def pipeline_run_phase_start(self, phase: PipelineRunPhase) -> None:
        self._dispatch(lambda p=phase: self._app._on_run_phase_start(p))

    def pipeline_run_phase_end(self, phase: PipelineRunPhase) -> None:
        self._dispatch(lambda p=phase: self._app._on_run_phase_end(p))

    def survey_author_started(self, slug: str, index: int, total: int) -> None:
        self._dispatch(
            lambda s=slug, i=index, t=total: self._app._on_survey_author_started(s, i, t)
        )

    def survey_author_finished(self, slug: str, error: str | None = None) -> None:
        self._dispatch(lambda s=slug, e=error: self._app._on_survey_author_finished(s, e))


class PipelineDashboardApp(App[None]):
    """Live pipeline progress: macro phases, per-author scrape/survey rows, event log."""

    TITLE = "Forensics — Pipeline"
    CSS_PATH = str(Path(__file__).with_name("pipeline_styles.tcss"))
    BINDINGS = [Binding("q", "quit", "Quit")]

    def __init__(
        self,
        *,
        survey_mode: bool = False,
        survey_kwargs: dict | None = None,
        pipeline_runner: _PipelineRunner | None = None,
    ) -> None:
        super().__init__()
        self._survey_mode = survey_mode
        self._survey_kwargs: dict = dict(survey_kwargs or {})
        self._pipeline_runner = pipeline_runner
        self._observer = TextualPipelineObserver(self)
        self._author_row_keys: dict[str, object] = {}
        self._col_scrape: object | None = None
        self._col_extract: object | None = None
        self._col_analyze: object | None = None
        self._col_notes: object | None = None
        #: Set when the pipeline worker finishes (``None`` until terminal state).
        self._worker_result_code: int | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Pipeline dashboard (press q to quit).", id="dashboard-title")
        yield Horizontal(id="phases")
        yield DataTable(id="authors", zebra_stripes=True)
        yield RichLog(id="events", highlight=False, markup=False)
        yield Footer()

    def on_mount(self) -> None:
        phases = self.query_one("#phases", Horizontal)
        phase_keys = (
            (
                PipelineRunPhase.SCRAPE,
                PipelineRunPhase.EXTRACT,
                PipelineRunPhase.ANALYZE,
                PipelineRunPhase.SURVEY_FINALIZE,
            )
            if self._survey_mode
            else (
                PipelineRunPhase.SCRAPE,
                PipelineRunPhase.EXTRACT,
                PipelineRunPhase.ANALYZE,
                PipelineRunPhase.REPORT,
            )
        )
        for ph in phase_keys:
            label = _PHASE_LABELS[ph.value]
            phases.mount(Static(f"{label}: pending", classes="phase", id=f"phase-{ph.value}"))

        table = self.query_one("#authors", DataTable)
        table.add_column("Author", key="author")
        self._col_scrape = table.add_column("Scrape", key="scrape")
        self._col_extract = table.add_column("Extract", key="extract")
        self._col_analyze = table.add_column("Analyze", key="analyze")
        self._col_notes = table.add_column("Notes", key="notes")

        self._log_event("Starting pipeline in a background thread...")
        self.run_worker(
            self._thread_pipeline,
            name=_PIPELINE_WORKER_NAME,
            thread=True,
            exclusive=True,
            exit_on_error=False,
        )

    def action_quit(self) -> None:
        cancelled = self._cancel_pipeline_worker_if_running()
        if cancelled:
            self.exit(return_code=130)
            return
        code = 0 if self._worker_result_code is None else self._worker_result_code
        self.exit(return_code=code)

    def _cancel_pipeline_worker_if_running(self) -> bool:
        cancelled = False
        for w in self.workers:
            if w.name != _PIPELINE_WORKER_NAME or w.is_finished:
                continue
            w.cancel()
            cancelled = True
        return cancelled

    def _thread_pipeline(self) -> int:
        if self._pipeline_runner is not None:
            return self._pipeline_runner(self._observer)
        if self._survey_mode:
            from forensics.config import get_settings
            from forensics.survey.orchestrator import run_survey, survey_completion_exit_code

            settings = get_settings()
            kw = {
                k: v
                for k, v in self._survey_kwargs.items()
                if k not in ("observer", "show_rich_progress")
            }

            async def _go():
                return await run_survey(
                    settings,
                    observer=self._observer,
                    show_rich_progress=True,
                    **kw,
                )

            report = asyncio.run(_go())
            return survey_completion_exit_code(report)
        from forensics.pipeline import run_all_pipeline

        return run_all_pipeline(show_progress=True, observer=self._observer)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        w = event.worker
        if w.name != _PIPELINE_WORKER_NAME:
            return
        if event.state not in (WorkerState.SUCCESS, WorkerState.ERROR):
            return
        if event.state == WorkerState.ERROR:
            err = w.error
            msg = f"Worker failed: {err!r}" if err else "Worker failed"
            self._log_event(escape(msg))
            self._worker_result_code = 1
            self.exit(return_code=1)
            return
        rc = w.result
        self._worker_result_code = 0 if rc is None else int(rc)
        self._log_event(
            f"Pipeline worker finished (exit code {self._worker_result_code}). "
            "Press q to quit."
        )
        if self._worker_result_code != 0:
            self.exit(return_code=self._worker_result_code)

    def _phase_widget(self, phase: PipelineRunPhase) -> Static:
        return self.query_one(f"#phase-{phase.value}", Static)

    def _on_run_phase_start(self, phase: PipelineRunPhase) -> None:
        label = _PHASE_LABELS.get(phase.value, phase.value)
        try:
            self._phase_widget(phase).update(f"{label}: running")
        except Exception:
            logger.debug("phase widget missing for %s", phase.value, exc_info=True)
        self._log_event(f"Phase {label} started")

    def _on_run_phase_end(self, phase: PipelineRunPhase) -> None:
        label = _PHASE_LABELS.get(phase.value, phase.value)
        try:
            self._phase_widget(phase).update(f"{label}: done")
        except Exception:
            logger.debug("phase widget missing for %s", phase.value, exc_info=True)
        self._log_event(f"Phase {label} finished")

    def _ensure_author_row(self, slug: str) -> object:
        table = self.query_one("#authors", DataTable)
        if slug in self._author_row_keys:
            return self._author_row_keys[slug]
        key = table.add_row(slug, "...", "-", "-", "", key=slug)
        self._author_row_keys[slug] = key
        return key

    def _on_metadata_author_started(self, slug: str) -> None:
        self._ensure_author_row(slug)
        if self._col_scrape is not None:
            self.query_one("#authors", DataTable).update_cell(slug, self._col_scrape, "...")

    def _on_metadata_author_done(self, slug: str, inserted: int) -> None:
        self._ensure_author_row(slug)
        if self._col_scrape is not None:
            self.query_one("#authors", DataTable).update_cell(
                slug, self._col_scrape, f"+{inserted} rows"
            )

    def _on_survey_author_started(self, slug: str, index: int, total: int) -> None:
        self._ensure_author_row(slug)
        if self._col_extract is not None:
            self.query_one("#authors", DataTable).update_cell(
                slug, self._col_extract, f"[{index}/{total}] ..."
            )

    def _on_survey_author_finished(self, slug: str, error: str | None) -> None:
        self._ensure_author_row(slug)
        tbl = self.query_one("#authors", DataTable)
        if self._col_extract is not None:
            tbl.update_cell(slug, self._col_extract, "done")
        if self._col_analyze is not None:
            tbl.update_cell(slug, self._col_analyze, "error" if error else "ok")
        if self._col_notes is not None and error:
            tbl.update_cell(slug, self._col_notes, escape(error[:80]))

    def _log_event(self, message: str) -> None:
        self.query_one("#events", RichLog).write(message + "\n")


def run_dashboard_interactive(
    *,
    survey_mode: bool = False,
    survey_kwargs: dict | None = None,
    pipeline_runner: _PipelineRunner | None = None,
) -> int:
    """Run the dashboard until the user closes the app; returns a CLI exit code."""
    app = PipelineDashboardApp(
        survey_mode=survey_mode,
        survey_kwargs=survey_kwargs,
        pipeline_runner=pipeline_runner,
    )
    app.run()
    return app.return_code


__all__ = [
    "PipelineDashboardApp",
    "TextualPipelineObserver",
    "run_dashboard_interactive",
]
