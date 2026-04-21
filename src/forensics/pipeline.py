"""End-to-end pipeline orchestration (scrape → extract → analyze → report)."""

from __future__ import annotations

import asyncio
import logging

import typer

from forensics.cli._helpers import config_fingerprint
from forensics.cli.analyze import run_analyze
from forensics.cli.scrape import dispatch_scrape
from forensics.config import get_project_root, get_settings
from forensics.features.pipeline import extract_all_features
from forensics.models.report_args import ReportArgs
from forensics.reporting import run_report
from forensics.storage.repository import insert_analysis_run

logger = logging.getLogger(__name__)


def run_all_pipeline() -> int:
    """Run the default full pipeline; returns process exit code."""
    root = get_project_root()
    db_path = root / "data" / "articles.db"
    try:
        insert_analysis_run(
            db_path,
            config_hash=config_fingerprint(),
            description="forensics all",
        )
    except OSError as exc:
        logger.warning("Could not record analysis_runs row: %s", exc)

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

    settings = get_settings()
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
