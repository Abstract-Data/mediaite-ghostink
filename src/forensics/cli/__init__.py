"""Typer CLI for the AI Writing Forensics pipeline."""

from __future__ import annotations

import importlib.metadata
import logging
import sys
from pathlib import Path
from typing import Annotated, Literal

import httpx
import typer

from forensics.cli.state import ForensicsCliState, get_cli_state

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


def _configure_logging(
    level: int,
    log_format: Literal["text", "json"],
) -> None:
    """Configure root logging once per process (P2-OPS-001)."""
    if log_format == "json":
        from pythonjsonlogger.jsonlogger import JsonFormatter

        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter(fmt="%(levelname)s %(name)s %(message)s"))
        logging.basicConfig(level=level, handlers=[handler], force=True)
    else:
        logging.basicConfig(
            level=level,
            format="%(levelname)s %(name)s: %(message)s",
            force=True,
        )


@app.callback()
def _root(
    ctx: typer.Context,
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
    no_progress: Annotated[
        bool,
        typer.Option(
            "--no-progress",
            help="Disable Rich progress bars and pipeline observers (CI, logs, minimal TTY).",
        ),
    ] = False,
    log_format: Annotated[
        Literal["text", "json"],
        typer.Option(
            "--log-format",
            help="Log output format: plain text (default) or JSON for aggregation.",
        ),
    ] = "text",
) -> None:
    """AI Writing Forensics Pipeline."""
    ctx.obj = ForensicsCliState(show_progress=not no_progress)
    level = logging.DEBUG if verbose else logging.INFO
    _configure_logging(level, log_format)


# --- Register subcommands ---
from forensics.cli.analyze import analyze  # noqa: E402
from forensics.cli.calibrate import calibrate_app  # noqa: E402
from forensics.cli.extract import extract  # noqa: E402
from forensics.cli.migrate import features_app, migrate  # noqa: E402
from forensics.cli.report import report  # noqa: E402
from forensics.cli.scrape import scrape_app  # noqa: E402
from forensics.cli.survey import survey_app  # noqa: E402

app.add_typer(scrape_app, name="scrape")
app.add_typer(survey_app, name="survey")
app.add_typer(calibrate_app, name="calibrate")
app.add_typer(features_app, name="features")
app.command(name="extract")(extract)
app.command(name="analyze")(analyze)
app.command(name="report")(report)
app.command(name="migrate")(migrate)


_SETTINGS_LOAD_ERRORS: tuple[type[BaseException], ...] | None = None


def _settings_load_errors() -> tuple[type[BaseException], ...]:
    """Return the narrow exception tuple covering ``get_settings()`` failures.

    Cached after first call so repeated CLI entry points (``preflight``,
    ``validate``, and any future command) don't re-import ``tomllib`` /
    ``pydantic`` on every invocation.
    """
    global _SETTINGS_LOAD_ERRORS
    if _SETTINGS_LOAD_ERRORS is None:
        import tomllib

        from pydantic import ValidationError

        _SETTINGS_LOAD_ERRORS = (
            ValidationError,
            FileNotFoundError,
            tomllib.TOMLDecodeError,
            ValueError,
            OSError,
        )
    return _SETTINGS_LOAD_ERRORS


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
    except _settings_load_errors() as exc:
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


@app.command(name="lock-preregistration")
def lock_preregistration_cmd() -> None:
    """Lock analysis thresholds for pre-registration (run before analyzing data)."""
    from forensics.config import get_settings
    from forensics.preregistration import lock_preregistration

    settings = get_settings()
    path = lock_preregistration(settings)
    typer.echo(f"Pre-registration locked: {path}")
    typer.echo("Run analysis AFTER this point. Threshold changes will trigger warnings.")


_WP_TYPES_URL = "https://www.mediaite.com/wp-json/wp/v2/types"
_OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"


def _probe_endpoint(url: str, *, timeout: float = 3.0) -> tuple[bool, str]:
    """Synchronous GET that tolerates network / transport errors (returns ``(ok, detail)``)."""
    try:
        resp = httpx.get(url, timeout=timeout)
    except (httpx.HTTPError, OSError, ValueError, TypeError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if 200 <= resp.status_code < 400:
        return True, f"HTTP {resp.status_code}"
    return False, f"HTTP {resp.status_code}"


@app.command(name="validate")
def validate_config(
    check_endpoints: Annotated[
        bool,
        typer.Option(
            "--check-endpoints",
            help="Probe WordPress + Ollama endpoints (reported as warnings).",
        ),
    ] = False,
) -> None:
    """Validate config.toml, run preflight, and optionally probe live endpoints."""
    from forensics.config import get_settings
    from forensics.preflight import run_all_preflight_checks

    logger = logging.getLogger(__name__)
    try:
        settings = get_settings()
    except _settings_load_errors() as exc:
        logger.error("Config error: %s", exc)
        typer.echo(f"Config error: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"Config parsed: {len(settings.authors)} author(s)")

    report = run_all_preflight_checks(settings)
    icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    for check in report.checks:
        typer.echo(f"  [{icons[check.status]}] {check.name}: {check.message}")

    if check_endpoints:
        typer.echo("\nEndpoint probes (warnings only, do not affect exit code):")
        wp_ok, wp_detail = _probe_endpoint(_WP_TYPES_URL)
        typer.echo(f"  [{'PASS' if wp_ok else 'WARN'}] WordPress API: {wp_detail}")
        oll_ok, oll_detail = _probe_endpoint(_OLLAMA_TAGS_URL)
        typer.echo(f"  [{'PASS' if oll_ok else 'WARN'}] Ollama: {oll_detail}")

    if report.has_failures:
        typer.echo("\nSome required checks failed.")
        raise typer.Exit(code=1)
    if report.has_warnings:
        typer.echo("\nAll required checks passed (some warnings).")
    else:
        typer.echo("\nAll validation checks passed.")
    raise typer.Exit(code=0)


@app.command(name="export")
def export_data(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output path for the single-file DuckDB export.",
        ),
    ] = Path("data/forensics_export.duckdb"),
    include_features: Annotated[
        bool,
        typer.Option(
            "--features/--no-features",
            help="Include the features parquet shards (default: on).",
        ),
    ] = True,
    include_analysis: Annotated[
        bool,
        typer.Option(
            "--analysis/--no-analysis",
            help="Include per-author analysis *_result.json artifacts (default: on).",
        ),
    ] = True,
) -> None:
    """Export SQLite + features + analysis into a single ``.duckdb`` file."""
    from forensics.config import get_project_root
    from forensics.storage.duckdb_queries import export_to_duckdb

    root = get_project_root()
    db_path = root / "data" / "articles.db"
    out_path = output if output.is_absolute() else root / output

    if not db_path.is_file():
        typer.echo(f"SQLite source not found: {db_path}")
        raise typer.Exit(code=1)

    report = export_to_duckdb(
        db_path,
        out_path,
        include_features=include_features,
        include_analysis=include_analysis,
    )
    typer.echo(f"Exported to {report.output_path} ({report.bytes_written} bytes)")
    for name, count in report.tables.items():
        typer.echo(f"  {name}: {count} rows")
    typer.echo(f"Query with: duckdb {report.output_path}")


@app.command(name="all")
def run_all(ctx: typer.Context) -> None:
    """Run full pipeline end-to-end: scrape → extract → analyze → report."""
    from forensics.pipeline import run_all_pipeline

    logger = logging.getLogger(__name__)
    st = get_cli_state(ctx)
    rc = run_all_pipeline(show_progress=st.show_progress)
    if rc != 0:
        logger.error("pipeline exited with code %d", rc)
        raise typer.Exit(code=rc)


@app.command(name="setup")
def setup_wizard() -> None:
    """Launch the interactive setup wizard (requires the 'tui' extra)."""
    from forensics.tui import main as tui_main

    rc = tui_main()
    if rc != 0:
        raise typer.Exit(code=rc)


@app.command(name="dashboard")
def dashboard_cmd(
    ctx: typer.Context,
    survey: Annotated[
        bool,
        typer.Option("--survey", help="Run blind survey flow (finalize instead of report)."),
    ] = False,
    skip_scrape: Annotated[
        bool,
        typer.Option("--skip-scrape", help="Survey only: skip scrape and use existing corpus."),
    ] = False,
    resume: Annotated[
        str | None,
        typer.Option("--resume", metavar="RUN_ID", help="Survey only: resume a prior run id."),
    ] = None,
    author: Annotated[
        str | None,
        typer.Option("--author", metavar="SLUG", help="Survey only: single author slug."),
    ] = None,
    min_articles: Annotated[
        int | None,
        typer.Option("--min-articles", help="Survey only: override minimum article count."),
    ] = None,
    min_span_days: Annotated[
        int | None,
        typer.Option("--min-span-days", help="Survey only: override minimum date span (days)."),
    ] = None,
    post_year_min: Annotated[
        int | None,
        typer.Option("--post-year-min", help="Survey scrape: inclusive min calendar year."),
    ] = None,
    post_year_max: Annotated[
        int | None,
        typer.Option("--post-year-max", help="Survey scrape: inclusive max calendar year."),
    ] = None,
) -> None:
    """Full-screen pipeline dashboard (``tui`` extra). Incompatible with ``--no-progress``."""
    st = get_cli_state(ctx)
    if not st.show_progress:
        typer.echo(
            "The dashboard needs an interactive terminal. "
            "Omit --no-progress, or use `forensics all` / `forensics survey` with --no-progress.",
            err=True,
        )
        raise typer.Exit(code=1)

    if not survey and (
        skip_scrape
        or resume is not None
        or author is not None
        or min_articles is not None
        or min_span_days is not None
        or post_year_min is not None
        or post_year_max is not None
    ):
        typer.echo(
            "Survey-only options (--skip-scrape, --resume, --author, --min-articles, "
            "--min-span-days, --post-year-min, --post-year-max) require --survey.",
            err=True,
        )
        raise typer.Exit(code=2)

    from dataclasses import replace

    from forensics.config import get_project_root, get_settings
    from forensics.survey.qualification import QualificationCriteria
    from forensics.tui import main_dashboard

    root = get_project_root()
    db_path = root / "data" / "articles.db"
    survey_kw: dict = {
        "project_root": root,
        "db_path": db_path,
        "resume": resume,
        "skip_scrape": skip_scrape,
        "author": author,
        "post_year_min": post_year_min,
        "post_year_max": post_year_max,
    }
    if survey:
        settings = get_settings()
        overrides: dict[str, int] = {}
        if min_articles is not None:
            overrides["min_articles"] = min_articles
        if min_span_days is not None:
            overrides["min_span_days"] = min_span_days
        criteria = replace(QualificationCriteria.from_settings(settings.survey), **overrides)
        survey_kw["criteria"] = criteria

    rc = main_dashboard(survey_mode=survey, survey_kwargs=survey_kw if survey else None)
    if rc != 0:
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
