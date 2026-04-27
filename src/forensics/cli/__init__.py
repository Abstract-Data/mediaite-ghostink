"""Typer CLI for the AI Writing Forensics pipeline."""

from __future__ import annotations

import functools
import importlib.metadata
import logging
import sys
from pathlib import Path
from typing import Annotated, Literal

import httpx
import typer
from typer.main import get_command

from forensics.cli._commands import run_list_commands
from forensics.cli._decorators import examples_epilog, forensics_examples
from forensics.cli._envelope import emit, status, success
from forensics.cli._errors import fail
from forensics.cli._exit import ExitCode
from forensics.cli.state import ForensicsCliState, get_cli_state
from forensics.preflight import PreflightReport

app = typer.Typer(
    name="forensics",
    help="AI Writing Forensics Pipeline",
    no_args_is_help=True,
    epilog="Exit code reference: docs/EXIT_CODES.md (retry backoff only on code 4).",
)


def _version_callback(value: bool) -> None:
    if value:
        try:
            version = importlib.metadata.version("mediaite-ghostink")
        except importlib.metadata.PackageNotFoundError:
            version = "0.0.0+unknown"
        typer.echo(f"forensics {version}")
        raise typer.Exit(int(ExitCode.OK))


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
    output: Annotated[
        Literal["text", "json"],
        typer.Option(
            "--output",
            help=(
                "text (default): human-readable lines on stdout. "
                "json: one JSON envelope object on stdout (logs to stderr)."
            ),
        ),
    ] = "text",
    non_interactive: Annotated[
        bool,
        typer.Option(
            "--non-interactive",
            help="Disable TUI fallbacks and refuse any prompt; auto-fail if a prompt would block.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Bypass any confirmation prompt.",
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
    ctx.obj = ForensicsCliState(
        show_progress=not no_progress and output != "json",
        output_format=output,
        non_interactive=non_interactive,
        assume_yes=yes,
    )
    level = logging.DEBUG if verbose else logging.INFO
    _configure_logging(level, log_format)


# --- Register subcommands ---
from forensics.cli.analyze import analyze_app  # noqa: E402
from forensics.cli.calibrate import calibrate_app  # noqa: E402
from forensics.cli.dedup import dedup_app  # noqa: E402
from forensics.cli.extract import extract  # noqa: E402
from forensics.cli.migrate import features_app, migrate  # noqa: E402
from forensics.cli.report import report  # noqa: E402
from forensics.cli.scrape import scrape_app  # noqa: E402
from forensics.cli.survey import survey_app  # noqa: E402

app.add_typer(scrape_app, name="scrape")
app.add_typer(survey_app, name="survey")
app.add_typer(calibrate_app, name="calibrate")
app.add_typer(features_app, name="features")
app.add_typer(analyze_app, name="analyze")
app.add_typer(dedup_app, name="dedup")
app.command(
    name="extract",
    epilog=examples_epilog("forensics extract --author colby-hall"),
)(extract)
app.command(
    name="report",
    epilog=examples_epilog("forensics report --format html"),
)(report)
app.command(
    name="migrate",
    epilog=examples_epilog("forensics migrate"),
)(migrate)


def _preflight_json_envelope(
    report: PreflightReport,
    *,
    strict: bool,
) -> dict[str, object]:
    """Build the inner ``data`` payload for ``forensics --output json preflight``."""
    if report.has_failures:
        status = "fail"
    elif report.has_warnings:
        status = "warn"
    else:
        status = "ok"
    checks: list[dict[str, str]] = [
        {"name": c.name, "status": c.status, "message": c.message} for c in report.checks
    ]
    return {
        "checks": checks,
        "has_failures": report.has_failures,
        "has_warnings": report.has_warnings,
        "status": status,
        "strict": strict,
    }


@functools.lru_cache(maxsize=1)
def _settings_load_errors() -> tuple[type[BaseException], ...]:
    """Return the narrow exception tuple covering ``get_settings()`` failures.

    Cached so repeated CLI entry points (``preflight``, ``validate``, and any
    future command) don't re-import ``tomllib`` / ``pydantic`` on every
    invocation.
    """
    import tomllib

    from pydantic import ValidationError

    return (
        ValidationError,
        FileNotFoundError,
        tomllib.TOMLDecodeError,
        ValueError,
        OSError,
    )


_PREFLIGHT_EPILOG, _preflight_ex = forensics_examples(
    "forensics --output json preflight",
    "forensics preflight --strict",
)


@app.command(name="preflight", epilog=_PREFLIGHT_EPILOG)
@_preflight_ex
def preflight(
    ctx: typer.Context,
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
    state = get_cli_state(ctx)
    try:
        settings = get_settings()
    except _settings_load_errors() as exc:
        logger.error("Could not load settings for preflight: %s", exc)
        settings = None
    report = run_all_preflight_checks(settings, strict=strict)

    if state.output_format == "json":
        emit(success("preflight", _preflight_json_envelope(report, strict=strict)))
    else:
        icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
        for check in report.checks:
            status(
                f"  [{icons[check.status]}] {check.name}: {check.message}",
                output_format=state.output_format,
            )

        if report.has_failures:
            status(
                "\nSome required checks failed. Fix issues before running the pipeline.",
                output_format=state.output_format,
            )
        elif report.has_warnings:
            status(
                "\nAll required checks passed (some warnings).",
                output_format=state.output_format,
            )
        else:
            status("\nAll preflight checks passed.", output_format=state.output_format)

    if report.has_failures:
        raise typer.Exit(int(ExitCode.GENERAL_ERROR))
    raise typer.Exit(int(ExitCode.OK))


_LOCK_EPILOG, _lock_ex = forensics_examples(
    "forensics --yes lock-preregistration",
    "forensics lock-preregistration",
)


@app.command(name="lock-preregistration", epilog=_LOCK_EPILOG)
@_lock_ex
def lock_preregistration_cmd(ctx: typer.Context) -> None:
    """Lock analysis thresholds for pre-registration (run before analyzing data)."""
    from forensics.config import get_project_root, get_settings
    from forensics.preregistration import lock_preregistration

    st = get_cli_state(ctx)
    lock_path = get_project_root() / "data" / "preregistration" / "preregistration_lock.json"
    if lock_path.is_file() and not st.assume_yes:
        raise fail(
            ctx,
            "lock-preregistration",
            "lock_exists",
            f"Pre-registration lock already exists: {lock_path}",
            exit_code=ExitCode.CONFLICT,
            suggestion=(
                "re-run: forensics --yes lock-preregistration "
                "(place global --yes before the subcommand)"
            ),
        )
    settings = get_settings()
    path = lock_preregistration(settings)
    status(f"Pre-registration locked: {path}", output_format=st.output_format)
    status(
        "Run analysis AFTER this point. Threshold changes will trigger warnings.",
        output_format=st.output_format,
    )


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


_VALIDATE_EPILOG, _validate_ex = forensics_examples("forensics validate --check-endpoints")


@app.command(name="validate", epilog=_VALIDATE_EPILOG)
@_validate_ex
def validate_config(
    ctx: typer.Context,
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

    st = get_cli_state(ctx)
    try:
        settings = get_settings()
    except _settings_load_errors() as exc:
        raise fail(
            ctx,
            "validate",
            "config_invalid",
            f"Could not parse config.toml: {exc}",
            exit_code=ExitCode.USAGE_ERROR,
            suggestion="run: forensics preflight to see which check failed",
        ) from exc

    typer.echo(f"Config parsed: {len(settings.authors)} author(s)")

    report = run_all_preflight_checks(settings)
    icons = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    for check in report.checks:
        typer.echo(f"  [{icons[check.status]}] {check.name}: {check.message}")

    if check_endpoints:
        status(
            "\nEndpoint probes (warnings only, do not affect exit code):",
            output_format=st.output_format,
        )
        wp_ok, wp_detail = _probe_endpoint(_WP_TYPES_URL)
        status(
            f"  [{'PASS' if wp_ok else 'WARN'}] WordPress API: {wp_detail}",
            output_format=st.output_format,
        )
        oll_ok, oll_detail = _probe_endpoint(_OLLAMA_TAGS_URL)
        status(
            f"  [{'PASS' if oll_ok else 'WARN'}] Ollama: {oll_detail}",
            output_format=st.output_format,
        )

    if report.has_failures:
        status("\nSome required checks failed.", output_format=st.output_format)
        raise typer.Exit(int(ExitCode.GENERAL_ERROR))
    if report.has_warnings:
        status("\nAll required checks passed (some warnings).", output_format=st.output_format)
    else:
        status("\nAll validation checks passed.", output_format=st.output_format)
    raise typer.Exit(int(ExitCode.OK))


_EXPORT_EPILOG, _export_ex = forensics_examples(
    "forensics export --output data/forensics_2026-04-26.duckdb",
)


@app.command(name="export", epilog=_EXPORT_EPILOG)
@_export_ex
def export_data(
    ctx: typer.Context,
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

    st = get_cli_state(ctx)
    if not db_path.is_file():
        raise fail(
            ctx,
            "export",
            "database_missing",
            f"SQLite source not found: {db_path}",
            exit_code=ExitCode.AUTH_OR_RESOURCE,
            suggestion="run: forensics scrape --discover --metadata to populate data/articles.db",
        )

    report = export_to_duckdb(
        db_path,
        out_path,
        include_features=include_features,
        include_analysis=include_analysis,
    )
    typer.echo(f"Exported to {report.output_path} ({report.bytes_written} bytes)")
    for name, count in report.tables.items():
        typer.echo(f"  {name}: {count} rows")
    status(f"Query with: duckdb {report.output_path}", output_format=st.output_format)


_ALL_EPILOG, _all_ex = forensics_examples(
    "forensics all",
    "forensics --output json all",
)


@app.command(name="all", epilog=_ALL_EPILOG)
@_all_ex
def run_all(ctx: typer.Context) -> None:
    """Run full pipeline end-to-end: scrape → extract → analyze → report."""
    from forensics.pipeline import run_all_pipeline

    st = get_cli_state(ctx)
    rc = run_all_pipeline(show_progress=st.show_progress)
    if rc != 0:
        try:
            ec = ExitCode(rc)
        except ValueError:
            ec = ExitCode.GENERAL_ERROR
        raise fail(
            ctx,
            "all",
            "pipeline_failed",
            f"Pipeline exited with code {rc}",
            exit_code=ec,
        )


_SETUP_EPILOG, _setup_ex = forensics_examples("forensics setup")


@app.command(name="setup", epilog=_SETUP_EPILOG)
@_setup_ex
def setup_wizard(ctx: typer.Context) -> None:
    """Launch the interactive setup wizard (requires the 'tui' extra)."""
    if get_cli_state(ctx).non_interactive:
        raise fail(
            ctx,
            "setup",
            "tty_required",
            "This command requires an interactive terminal (TUI).",
            exit_code=ExitCode.USAGE_ERROR,
            suggestion="Omit --non-interactive for headless environments; "
            "use `forensics preflight` / `forensics all` instead.",
        )
    from forensics.tui import main as tui_main

    rc = tui_main()
    if rc != 0:
        raise typer.Exit(code=rc)


_DASH_EPILOG, _dash_ex = forensics_examples("forensics dashboard --survey --skip-scrape")


@app.command(name="dashboard", epilog=_DASH_EPILOG)
@_dash_ex
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
    if st.non_interactive:
        raise fail(
            ctx,
            "dashboard",
            "tty_required",
            "This command requires an interactive terminal (TUI).",
            exit_code=ExitCode.USAGE_ERROR,
            suggestion="Omit --non-interactive, or use `forensics all` / `forensics survey` "
            "for headless runs.",
        )
    if not st.show_progress:
        raise fail(
            ctx,
            "dashboard",
            "tty_required",
            "The dashboard needs an interactive terminal. "
            "Omit --no-progress, or use `forensics all` / `forensics survey` with --no-progress.",
            exit_code=ExitCode.USAGE_ERROR,
        )

    if not survey and (
        skip_scrape
        or resume is not None
        or author is not None
        or min_articles is not None
        or min_span_days is not None
        or post_year_min is not None
        or post_year_max is not None
    ):
        raise fail(
            ctx,
            "dashboard",
            "invalid_options",
            "Survey-only flags were passed without --survey.",
            exit_code=ExitCode.USAGE_ERROR,
            suggestion="Add --survey, or remove --skip-scrape / --resume / --author / "
            "--min-articles / --min-span-days / --post-year-*.",
        )

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


_COMMANDS_EPILOG, _commands_ex = forensics_examples(
    "forensics --output json commands | jq '.data.root.subcommands[].name'",
)


@app.command(name="commands", epilog=_COMMANDS_EPILOG)
@_commands_ex
def list_commands(ctx: typer.Context) -> None:
    """Dump the full command catalog (for agent discovery)."""
    run_list_commands(ctx, get_command(app))


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
