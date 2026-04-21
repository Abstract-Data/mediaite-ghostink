"""Typer CLI for the AI Writing Forensics pipeline."""

from __future__ import annotations

import asyncio
import importlib.metadata
import logging
from argparse import Namespace
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
    from forensics.cli.scrape import _dispatch as _scrape_dispatch
    from forensics.config import get_settings
    from forensics.features.pipeline import extract_all_features
    from forensics.reporting import run_report

    logger = logging.getLogger(__name__)

    code = asyncio.run(
        _scrape_dispatch(
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
        raise typer.Exit(code=code)

    from forensics.config import get_project_root

    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"
    extract_all_features(db_path, settings, author_slug=None, skip_embeddings=False)

    from forensics.cli.analyze import analyze as analyze_cmd

    try:
        analyze_cmd(
            changepoint=False,
            timeseries=True,
            drift=False,
            convergence=True,
            compare=False,
            ai_baseline=False,
            skip_generation=False,
            verify_corpus=False,
            openai_key=None,
            llm_model="gpt-4o",
            author=None,
        )
    except typer.Exit as exc:
        if exc.exit_code:
            raise

    report_args = Namespace(
        notebook=None,
        report_format=settings.report.output_format,
        verify=False,
    )
    rc = run_report(report_args)
    if rc != 0:
        logger.error("report stage exited with code %d", rc)
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
