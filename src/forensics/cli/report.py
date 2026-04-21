"""Report subcommand — Quarto rendering and deployment."""

from __future__ import annotations

import logging
from argparse import Namespace
from typing import Annotated

import typer

logger = logging.getLogger(__name__)


def report(
    notebook: Annotated[
        str | None,
        typer.Option(
            "--notebook",
            metavar="NN",
            help="Render one chapter by number (e.g. 05) or notebook filename",
        ),
    ] = None,
    format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format for quarto render: html, pdf, or both",
            case_sensitive=False,
        ),
    ] = "both",
    verify: Annotated[
        bool,
        typer.Option(
            "--verify",
            help="Require corpus hash to match data/analysis/corpus_custody.json",
        ),
    ] = False,
) -> None:
    """Render Quarto forensic book."""
    from forensics.reporting import run_report

    if format not in {"html", "pdf", "both"}:
        raise typer.BadParameter(f"--format must be one of html, pdf, both (got {format!r})")

    args = Namespace(
        notebook=notebook,
        report_format=format,
        verify=verify,
    )
    try:
        rc = run_report(args)
    except ValueError as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=1) from exc
    if rc != 0:
        raise typer.Exit(code=rc)
