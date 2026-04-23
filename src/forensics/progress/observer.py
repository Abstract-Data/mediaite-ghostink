"""Pipeline stage labels and an observer protocol with a no-op default."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable


class PipelineStage(StrEnum):
    """High-level scrape / export phases surfaced to UIs."""

    DISCOVER = "discover"
    METADATA = "metadata"
    FETCH = "fetch"
    DEDUP = "dedup"
    EXPORT = "export"
    ARCHIVE = "archive"


class PipelineRunPhase(StrEnum):
    """End-to-end pipeline / survey phases (above individual scrape stages)."""

    SCRAPE = "scrape"
    EXTRACT = "extract"
    ANALYZE = "analyze"
    REPORT = "report"
    SURVEY_FINALIZE = "survey_finalize"


@runtime_checkable
class PipelineObserver(Protocol):
    """Optional callbacks for scrape dispatch and sub-stages (thread-safe callers required)."""

    def pipeline_stage_start(self, stage: PipelineStage) -> None:
        """Notify that a macro stage has begun."""

    def pipeline_stage_end(self, stage: PipelineStage) -> None:
        """Notify that a macro stage has finished (success or handled failure)."""

    def metadata_author_started(self, slug: str) -> None:
        """Per-author metadata ingestion is about to run for ``slug``."""

    def metadata_author_done(self, slug: str, inserted_count: int) -> None:
        """Per-author metadata ingestion finished for ``slug``."""

    def fetch_progress(self, done: int, total: int) -> None:
        """Article fetch progress (``done`` inclusive, ``total`` rows in this run)."""

    def pipeline_run_phase_start(self, phase: PipelineRunPhase) -> None:
        """Notify that a coarse pipeline phase (scrape / extract / …) has begun."""

    def pipeline_run_phase_end(self, phase: PipelineRunPhase) -> None:
        """Notify that a coarse pipeline phase has finished."""

    def survey_author_started(self, slug: str, index: int, total: int) -> None:
        """Survey loop is about to process ``slug`` (``index`` of ``total``)."""

    def survey_author_finished(self, slug: str, error: str | None = None) -> None:
        """Survey loop finished ``slug``; ``error`` set when processing failed."""


class NoOpPipelineObserver:
    """Default observer; all methods are no-ops."""

    def pipeline_stage_start(self, _stage: PipelineStage) -> None:
        return None

    def pipeline_stage_end(self, _stage: PipelineStage) -> None:
        return None

    def metadata_author_started(self, _slug: str) -> None:
        return None

    def metadata_author_done(self, _slug: str, _inserted_count: int) -> None:
        return None

    def fetch_progress(self, _done: int, _total: int) -> None:
        return None

    def pipeline_run_phase_start(self, _phase: PipelineRunPhase) -> None:
        return None

    def pipeline_run_phase_end(self, _phase: PipelineRunPhase) -> None:
        return None

    def survey_author_started(self, _slug: str, _index: int, _total: int) -> None:
        return None

    def survey_author_finished(self, _slug: str, _error: str | None = None) -> None:
        return None


class FetchProgressThrottle:
    """Coalesce high-frequency ``fetch_progress`` emissions (per completion under concurrency)."""

    __slots__ = ("_last_emitted_done",)

    def __init__(self) -> None:
        self._last_emitted_done = 0

    def maybe_emit(self, observer: PipelineObserver, done: int, total: int) -> None:
        """Invoke ``observer.fetch_progress`` when progress crosses a reporting threshold."""
        if total <= 0:
            return
        if done <= self._last_emitted_done:
            return
        emit = done == 1 or done == total
        if not emit:
            last_pct = (100 * self._last_emitted_done) // total if self._last_emitted_done else -1
            cur_pct = (100 * done) // total
            step = max(25, max(1, total // 50))
            emit = cur_pct >= last_pct + 2 or (done - self._last_emitted_done) >= step
        if emit:
            observer.fetch_progress(done, total)
            self._last_emitted_done = done
