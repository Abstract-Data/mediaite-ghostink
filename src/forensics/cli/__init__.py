"""Typer CLI for the AI Writing Forensics pipeline."""

from __future__ import annotations

import importlib.metadata
import logging
from typing import Annotated

import typer

app = typer.Typer(
    name="forensics",
    help="AI Writing Forensics Pipeline",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        try:
            version = importlib.metadata.version("mediaite-ghostink")
        except importlib.metadata.PackageNotFoundError:
            version = "0.0.0+unknown"
        typer.echo(f"forensics {version}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Enable DEBUG logging")] = False,
) -> None:
    """AI Writing Forensics Pipeline."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


# --- Register subcommands ---
from forensics.cli.analyze import analyze  # noqa: E402
from forensics.cli.extract import extract  # noqa: E402
from forensics.cli.report import report  # noqa: E402
from forensics.cli.scrape import scrape_app  # noqa: E402

app.add_typer(scrape_app, name="scrape")
app.command(name="extract")(extract)
app.command(name="analyze")(analyze)
app.command(name="report")(report)


@app.command(name="preflight")
def preflight(
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Promote warnings to failures (useful in CI).",
        ),
    ] = False,
) -> None:
    """Run preflight checks and report pass/warn/fail for each boundary."""
    from forensics.config import get_settings
    from forensics.preflight import run_all_preflight_checks

    logger = logging.getLogger(__name__)
    try:
        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not load settings for preflight: %s", exc)
        settings = None
    report = run_all_preflight_checks(settings, strict=strict)

    icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    for check in report.checks:
        typer.echo(f"  [{icons[check.status]}] {check.name}: {check.message}")

    if report.has_failures:
        typer.echo("\nSome required checks failed. Fix issues before running the pipeline.")
        raise typer.Exit(code=1)
    if report.has_warnings:
        typer.echo("\nAll required checks passed (some warnings).")
    else:
        typer.echo("\nAll preflight checks passed.")
    raise typer.Exit(code=0)


@app.command(name="all")
def run_all() -> None:
    """Run full pipeline end-to-end: scrape → extract → analyze → report."""
    from forensics.pipeline import run_all_pipeline

    logger = logging.getLogger(__name__)
    rc = run_all_pipeline()
    if rc != 0:
        logger.error("pipeline exited with code %d", rc)
        raise typer.Exit(code=rc)


def main() -> int:
    """Entrypoint called by pyproject.toml [project.scripts]."""
    try:
        app()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


# Typer ``app`` and console ``main`` only; subcommands live in ``forensics.cli.*``.
__all__ = ["app", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
