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


if __name__ == "__main__":
    raise SystemExit(main())
