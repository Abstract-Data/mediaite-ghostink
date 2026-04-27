"""Calibrate subcommand — validate detection accuracy (Phase 12 §4e)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer

from forensics.cli._decorators import forensics_examples
from forensics.cli._envelope import status
from forensics.cli.state import get_cli_state

logger = logging.getLogger(__name__)

_CALIB_EPILOG, _CALIB_EX = forensics_examples("forensics calibrate --dry-run")

calibrate_app = typer.Typer(
    name="calibrate",
    help="Validate detection accuracy against synthetic ground truth.",
    no_args_is_help=False,
    invoke_without_command=True,
)


@calibrate_app.callback(invoke_without_command=True, epilog=_CALIB_EPILOG)
@_CALIB_EX
def calibrate(
    ctx: typer.Context,
    positive_trials: Annotated[
        int,
        typer.Option("--positive-trials", help="Number of spliced-corpus trials (default: 5)."),
    ] = 5,
    negative_trials: Annotated[
        int,
        typer.Option("--negative-trials", help="Number of unmodified-corpus trials (default: 5)."),
    ] = 5,
    author: Annotated[
        str | None,
        typer.Option("--author", metavar="SLUG", help="Calibrate against a specific author."),
    ] = None,
    seed: Annotated[
        int,
        typer.Option("--seed", help="Deterministic seed for splice-date selection (default: 42)."),
    ] = 42,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            metavar="PATH",
            help="Write the JSON report here instead of data/calibration/.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Skip trial execution — return an empty report (smoke test only).",
        ),
    ] = False,
) -> None:
    """Run calibration trials and emit sensitivity / specificity / F1 metrics."""
    from forensics.calibration.runner import run_calibration
    from forensics.config import get_project_root, get_settings

    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"

    report = asyncio.run(
        run_calibration(
            settings,
            positive_trials=positive_trials,
            negative_trials=negative_trials,
            author=author,
            seed=seed,
            project_root=root,
            db_path=db_path,
            output_path=output,
            dry_run=dry_run,
        )
    )

    fmt = get_cli_state(ctx).output_format
    status("", output_format=fmt)
    status(f"Calibration Results ({len(report.trials)} trials)", output_format=fmt)
    status("=" * 50, output_format=fmt)
    typer.echo(f"  Sensitivity (TPR):  {report.sensitivity:.1%}")
    typer.echo(f"  Specificity (TNR):  {report.specificity:.1%}")
    typer.echo(f"  Precision:          {report.precision:.1%}")
    typer.echo(f"  F1 Score:           {report.f1_score:.3f}")
    if report.median_date_error_days is not None:
        typer.echo(f"  Date accuracy:      {report.median_date_error_days:.0f} days median error")
    if report.report_path is not None:
        typer.echo("")
        typer.echo(f"Report written to: {report.report_path}")
