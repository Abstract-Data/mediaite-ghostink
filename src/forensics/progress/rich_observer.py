"""Rich-based :class:`~forensics.progress.PipelineObserver` for normal CLI runs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from forensics.progress.observer import PipelineObserver, PipelineRunPhase, PipelineStage


class RichPipelineObserver:
    """Live Rich ``Progress`` display for scrape stages, fetch %, and pipeline phases.

    Use :func:`managed_rich_observer` so ``Progress.start`` / ``stop`` run around the work.
    Set :attr:`live_ui_mode` to ``\"textual\"`` on a Textual-backed observer subclass so callers
    never stack Rich and a full-screen TUI on the same run.
    """

    live_ui_mode: Literal["rich", "textual"] = "rich"

    __slots__ = ("_console", "_progress", "_started", "_task_id")

    def __init__(self, *, console: Console | None = None) -> None:
        self._console = console or Console(stderr=True)
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self._console,
            transient=False,
        )
        self._task_id: int | None = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._progress.start()
        self._started = True
        self._task_id = self._progress.add_task("forensics", total=None)

    def stop(self) -> None:
        if not self._started:
            return
        self._progress.stop()
        self._started = False
        self._task_id = None

    def _describe(self, text: str) -> None:
        if self._task_id is None:
            return
        self._progress.update(self._task_id, description=text)

    def pipeline_stage_start(self, stage: PipelineStage) -> None:
        self._describe(f"scrape: {stage.value} …")

    def pipeline_stage_end(self, stage: PipelineStage) -> None:
        self._describe(f"scrape: {stage.value} done")

    def metadata_author_started(self, slug: str) -> None:
        self._describe(f"metadata: {slug} …")

    def metadata_author_done(self, slug: str, inserted_count: int) -> None:
        self._describe(f"metadata: {slug} (+{inserted_count} rows)")

    def fetch_progress(self, done: int, total: int) -> None:
        """Fetch progress (already throttled by :class:`FetchProgressThrottle` in the fetcher)."""
        self._describe(f"fetch: {done}/{total} articles")

    def pipeline_run_phase_start(self, phase: PipelineRunPhase) -> None:
        self._describe(f"pipeline: {phase.value} …")

    def pipeline_run_phase_end(self, phase: PipelineRunPhase) -> None:
        self._describe(f"pipeline: {phase.value} done")

    def survey_author_started(self, slug: str, index: int, total: int) -> None:
        self._describe(f"survey [{index}/{total}] {slug} …")

    def survey_author_finished(self, slug: str, error: str | None = None) -> None:
        suffix = f" — {error}" if error else ""
        self._describe(f"survey: {slug} done{suffix}")


@contextmanager
def managed_rich_observer(show: bool) -> Iterator[RichPipelineObserver | None]:
    """Start/stop a :class:`RichPipelineObserver` when ``show`` is true; else yield ``None``."""
    if not show:
        yield None
        return
    obs = RichPipelineObserver()
    obs.start()
    try:
        yield obs
    finally:
        obs.stop()


def live_ui_mode(observer: PipelineObserver | None) -> Literal["none", "rich", "textual"]:
    """Return which live UI owns the terminal for coordination (Rich vs Textual, never both)."""
    if observer is None:
        return "none"
    mode = getattr(observer, "live_ui_mode", "rich")
    if mode == "textual":
        return "textual"
    return "rich"
