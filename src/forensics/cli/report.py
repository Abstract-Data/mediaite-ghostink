"""Report subcommand — Quarto rendering."""

from __future__ import annotations

import logging
from argparse import Namespace
from typing import Annotated, Literal

import typer

logger = logging.getLogger(__name__)

ReportFormat = Literal["html", "pdf", "both"]


def report(
    notebook: Annotated[
        str | None,
        typer.Option("--notebook", metavar="NN", help="Render one chapter by number or filename"),
    ] = None,
    report_format: Annotated[
        ReportFormat,
        typer.Option("--format", help="Output format: html, pdf, or both"),
    ] = "both",
    verify: Annotated[
        bool,
        typer.Option("--verify", help="Require corpus hash match before rendering"),
    ] = False,
) -> None:
    """Render Quarto forensic book."""
    from forensics.reporting import run_report

    try:
        args = Namespace(
            notebook=notebook,
            report_format=report_format,
            verify=verify,
        )
        rc = run_report(args)
    except ValueError as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=1) from exc
    raise typer.Exit(code=rc)
