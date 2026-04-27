"""End-to-end pipeline orchestration (scrape → extract → analyze → report).

`forensics.cli.run_all` calls `run_all_pipeline` here. Order of operations:

1. **Audit** — ``PipelineContext`` records ``forensics all`` in ``analysis_runs``
   (best-effort; failures log a warning and the run continues).
2. **Scrape** — `asyncio.run(dispatch_scrape(...))` with all boolean stage flags false, which
   selects the same **full scrape** handler as a plain `forensics scrape` (discover → metadata
   → fetch → dedup → JSONL export). See `forensics.cli.scrape.dispatch_scrape`.
3. **Extract** — `extract_all_features` for all authors, embeddings on.
4. **Analyze** — ``run_analyze(AnalyzeRequest(timeseries=True, convergence=True))`` only
   (no changepoint, drift, compare-only, or AI baseline unless you edit this module).
5. **Report** — `run_report` with `ReportArgs` built from `get_settings().report.output_format`.

Operational detail and artifact layout: `docs/RUNBOOK.md`, `docs/ARCHITECTURE.md`.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager

import typer

from forensics.cli.analyze import AnalyzeRequest, run_analyze
from forensics.cli.scrape import dispatch_scrape
from forensics.config import DEFAULT_DB_RELATIVE, get_project_root, get_settings
from forensics.features.pipeline import extract_all_features
from forensics.models.report_args import ReportArgs
from forensics.pipeline_context import PipelineContext
from forensics.progress import (
    PipelineObserver,
    PipelineRunPhase,
    live_ui_mode,
    managed_rich_observer,
)
from forensics.reporting import run_report

logger = logging.getLogger(__name__)


@contextmanager
def _pipeline_phase(obs: PipelineObserver | None, phase: PipelineRunPhase):
    if obs is not None:
        obs.pipeline_run_phase_start(phase)
    try:
        yield
    finally:
        if obs is not None:
            obs.pipeline_run_phase_end(phase)


def run_all_pipeline(
    *,
    show_progress: bool = True,
    observer: PipelineObserver | None = None,
) -> int:
    """Run the default full pipeline; returns process exit code.

    The pipeline refuses to start when preflight checks hard-fail (returns
    exit code ``2``) — this prevents cascading errors deeper in the run when
    the environment is known to be broken.

    Args:
        show_progress: When true and ``observer`` is ``None``, attach a
            :class:`~forensics.progress.RichPipelineObserver` for scrape + phase labels.
        observer: Optional pre-constructed observer (e.g. Rich session owned by the CLI).
            When set, ``show_progress`` only controls the feature-extract Rich bar, not
            observer construction.
    """
    from forensics.preflight import run_all_preflight_checks

    settings = get_settings()
    report = run_all_preflight_checks(settings)
    if report.has_failures:
        for failure in report.failures():
            logger.error("preflight FAIL: %s — %s", failure.name, failure.message)
        logger.error("Fix preflight failures before running the pipeline.")
        return 2
    for warning in report.warnings():
        logger.warning("preflight WARN: %s — %s", warning.name, warning.message)

    db_path = get_project_root() / DEFAULT_DB_RELATIVE
    PipelineContext.resolve().record_audit("forensics all — preflight", optional=True, log=logger)
    PipelineContext.resolve().record_audit("forensics all", optional=True, log=logger)

    def _run(obs: PipelineObserver | None) -> int:
        rich_extract = show_progress and live_ui_mode(obs) != "textual"

        with _pipeline_phase(obs, PipelineRunPhase.SCRAPE):
            code = asyncio.run(
                dispatch_scrape(
                    discover=False,
                    metadata=False,
                    fetch=False,
                    dedup=False,
                    archive=False,
                    dry_run=False,
                    force_refresh=False,
                    observer=obs,
                )
            )
        if code != 0:
            return code

        with _pipeline_phase(obs, PipelineRunPhase.EXTRACT):
            extract_all_features(
                db_path,
                settings,
                author_slug=None,
                skip_embeddings=False,
                show_rich_progress=rich_extract,
            )

        with _pipeline_phase(obs, PipelineRunPhase.ANALYZE):
            try:
                run_analyze(AnalyzeRequest(timeseries=True, convergence=True))
            except typer.Exit as exc:
                if exc.exit_code:
                    return int(exc.exit_code or 1)

        with _pipeline_phase(obs, PipelineRunPhase.REPORT):
            report_args = ReportArgs(
                notebook=None,
                report_format=settings.report.output_format,
                verify=False,
            )
            return run_report(report_args)

    if observer is not None:
        return _run(observer)
    if show_progress:
        with managed_rich_observer(True) as obs:
            return _run(obs)
    return _run(None)
