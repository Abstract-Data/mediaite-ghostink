"""End-to-end pipeline orchestration (scrape → extract → analyze → report).

`forensics.cli.run_all` calls `run_all_pipeline` here. Order of operations:

1. **Audit** — ``PipelineContext`` records ``forensics all`` in ``analysis_runs``
   (best-effort; failures log a warning and the run continues).
2. **Scrape** — `asyncio.run(dispatch_scrape(...))` with all boolean stage flags false, which
   selects the same **full scrape** handler as a plain `forensics scrape` (discover → metadata
   → fetch → dedup → JSONL export). See `forensics.cli.scrape.dispatch_scrape`.
3. **Extract** — `extract_all_features` for all authors, embeddings on.
4. **Analyze** — `run_analyze(timeseries=True, convergence=True)` only (no changepoint,
   drift, compare-only, or AI baseline unless you edit this module).
5. **Report** — `run_report` with `ReportArgs` built from `get_settings().report.output_format`.

Operational detail and artifact layout: `docs/RUNBOOK.md`, `docs/ARCHITECTURE.md`.
"""

from __future__ import annotations

import asyncio
import logging

import typer

from forensics.cli.analyze import run_analyze
from forensics.cli.scrape import dispatch_scrape
from forensics.config import get_project_root, get_settings
from forensics.features.pipeline import extract_all_features
from forensics.models.report_args import ReportArgs
from forensics.pipeline_context import PipelineContext
from forensics.reporting import run_report

logger = logging.getLogger(__name__)


def run_all_pipeline() -> int:
    """Run the default full pipeline; returns process exit code.

    The pipeline refuses to start when preflight checks hard-fail (returns
    exit code ``2``) — this prevents cascading errors deeper in the run when
    the environment is known to be broken.
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

    root = get_project_root()
    db_path = root / "data" / "articles.db"
    PipelineContext.resolve().record_audit(
        "forensics all — preflight", optional=True, log=logger
    )
    PipelineContext.resolve().record_audit("forensics all", optional=True, log=logger)

    code = asyncio.run(
        dispatch_scrape(
            discover=False,
            metadata=False,
            fetch=False,
            dedup=False,
            archive=False,
            dry_run=False,
            force_refresh=False,
        )
    )
    if code != 0:
        return code

    extract_all_features(db_path, settings, author_slug=None, skip_embeddings=False)

    try:
        run_analyze(timeseries=True, convergence=True)
    except typer.Exit as exc:
        if exc.exit_code:
            return int(exc.exit_code or 1)

    report_args = ReportArgs(
        notebook=None,
        report_format=settings.report.output_format,
        verify=False,
    )
    return run_report(report_args)
