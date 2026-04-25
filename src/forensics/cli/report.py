"""Report subcommand — Quarto rendering and deployment."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from forensics.models.report_args import ReportArgs
from forensics.pipeline_context import PipelineContext

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
    per_author: Annotated[
        bool,
        typer.Option(
            "--per-author",
            help="Generate and render one evidence page per configured author.",
        ),
    ] = False,
    author: Annotated[
        str | None,
        typer.Option(
            "--author",
            help="When used with --per-author, render only this author slug.",
        ),
    ] = None,
) -> None:
    """Render Quarto forensic book."""
    from forensics.reporting import run_report

    PipelineContext.resolve().record_audit("forensics report", optional=True, log=logger)
    logger.info(
        "report: starting render format=%s notebook=%s verify=%s",
        format,
        notebook or "all",
        verify,
    )

    if format not in {"html", "pdf", "both"}:
        raise typer.BadParameter(f"--format must be one of html, pdf, both (got {format!r})")
    if author and not per_author:
        raise typer.BadParameter("--author can only be used with --per-author")

    args = ReportArgs(
        notebook=notebook,
        report_format=format,
        verify=verify,
        per_author=per_author,
        author_slug=author,
    )
    try:
        rc = run_report(args)
    except ValueError as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=1) from exc
    if rc != 0:
        raise typer.Exit(code=rc)
