"""Survey subcommand — blind newsroom-wide AI-adoption analysis (Phase 12 §1f)."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Annotated, Literal

import typer

from forensics.cli._envelope import status
from forensics.cli._exit import ExitCode
from forensics.cli.state import get_cli_state
from forensics.config import get_project_root, get_settings
from forensics.progress import managed_rich_observer
from forensics.survey.qualification import QualificationCriteria, qualify_authors

survey_app = typer.Typer(
    name="survey",
    help="Blind newsroom-wide AI-adoption survey.",
    no_args_is_help=False,
    invoke_without_command=True,
)


_STRENGTH_ICONS: dict[str, str] = {
    "strong": "!!!",
    "moderate": " ! ",
    "weak": " . ",
    "none": "   ",
    "error": "ERR",
}


def _survey_dry_run_echo(
    db_path,
    criteria,
    *,
    output_format: Literal["text", "json"],
) -> None:
    qualified, disqualified = qualify_authors(db_path, criteria)
    status("", output_format=output_format)
    status(f"Qualified: {len(qualified)} authors", output_format=output_format)
    status(f"Disqualified: {len(disqualified)} authors", output_format=output_format)
    status("", output_format=output_format)
    if output_format == "text":
        for qa in qualified:
            typer.echo(
                f"  {qa.author.name:<30} {qa.total_articles:>5} articles  "
                f"{qa.date_range_days:>5}d span  {qa.articles_per_year:>5.1f}/yr"
            )
    if disqualified:
        status("", output_format=output_format)
        status(f"Disqualified ({len(disqualified)}):", output_format=output_format)
        if output_format == "text":
            for dq in disqualified[:10]:
                typer.echo(f"  {dq.author.name:<30} reason: {dq.disqualification_reason}")
            if len(disqualified) > 10:
                typer.echo(f"  ... and {len(disqualified) - 10} more")


def _survey_print_report(
    report,
    *,
    output_format: Literal["text", "json"],
) -> None:
    status("", output_format=output_format)
    status("=" * 70, output_format=output_format)
    status(f"SURVEY COMPLETE — run_id={report.run_id}", output_format=output_format)
    status(f"{len(report.results)} authors analyzed", output_format=output_format)
    status("=" * 70, output_format=output_format)
    status("", output_format=output_format)

    if output_format == "text":
        for r in report.results[:20]:
            if r.score is not None:
                icon = _STRENGTH_ICONS.get(r.score.strength.value, "???")
                typer.echo(
                    f"  [{icon}] {r.author_name:<30} "
                    f"score={r.score.composite:.3f}  "
                    f"strength={r.score.strength.value:<10} "
                    f"{r.score.evidence_summary[:60]}"
                )
            elif r.error is not None:
                typer.echo(f"  [ERR] {r.author_name:<30} {r.error[:60]}")

    if report.natural_controls:
        status("", output_format=output_format)
        status(
            f"Natural control cohort: {len(report.natural_controls)} author(s)",
            output_format=output_format,
        )

    if report.run_dir is not None:
        status("", output_format=output_format)
        if output_format == "text":
            typer.echo(f"Full results: {report.run_dir}")


@survey_app.callback(invoke_without_command=True)
def survey(
    ctx: typer.Context,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="List qualified authors without running analysis."),
    ] = False,
    resume: Annotated[
        str | None,
        typer.Option(
            "--resume",
            metavar="RUN_ID",
            help="Resume a previous survey run by id (skip completed authors).",
        ),
    ] = None,
    skip_scrape: Annotated[
        bool,
        typer.Option(
            "--skip-scrape",
            help="Skip the discovery/scrape phase and reuse the existing corpus.",
        ),
    ] = False,
    author: Annotated[
        str | None,
        typer.Option(
            "--author",
            metavar="SLUG",
            help="Restrict the survey to a single author slug (debugging).",
        ),
    ] = None,
    min_articles: Annotated[
        int | None,
        typer.Option(
            "--min-articles",
            help="Override the minimum article count threshold (default from config).",
        ),
    ] = None,
    min_span_days: Annotated[
        int | None,
        typer.Option(
            "--min-span-days",
            help="Override the minimum date-span threshold in days (default from config).",
        ),
    ] = None,
    post_year_min: Annotated[
        int | None,
        typer.Option(
            "--post-year-min",
            help=(
                "Inclusive calendar year for WordPress posts during survey scrape "
                "(use with --post-year-max); overrides config when set"
            ),
        ),
    ] = None,
    post_year_max: Annotated[
        int | None,
        typer.Option(
            "--post-year-max",
            help=(
                "Inclusive calendar year for WordPress posts during survey scrape "
                "(use with --post-year-min); overrides config when set"
            ),
        ),
    ] = None,
    include_shared_bylines: Annotated[
        bool,
        typer.Option(
            "--include-shared-bylines",
            help=(
                "Include newsroom-shared accounts (e.g. mediaite-staff) in the "
                "survey; default OFF — shared bylines are disqualified."
            ),
        ),
    ] = False,
    include_advertorial: Annotated[
        bool,
        typer.Option(
            "--include-advertorial",
            help=(
                "Re-include sponsored / partner-content / crosspost articles in "
                "qualification volume / recency / frequency stats; default OFF "
                "— advertorial sections are excluded per Phase 15 J2."
            ),
        ),
    ] = False,
) -> None:
    """Run a blind newsroom survey — analyze all qualified authors."""
    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"

    overrides: dict[str, object] = {}
    if min_articles is not None:
        overrides["min_articles"] = min_articles
    if min_span_days is not None:
        overrides["min_span_days"] = min_span_days
    if include_shared_bylines:
        overrides["exclude_shared_bylines"] = False
    if include_advertorial:
        overrides["excluded_sections"] = frozenset()
    criteria = replace(QualificationCriteria.from_settings(settings.survey), **overrides)

    if dry_run:
        _survey_dry_run_echo(db_path, criteria, output_format=get_cli_state(ctx).output_format)
        raise typer.Exit(int(ExitCode.OK))

    from forensics.survey.orchestrator import run_survey

    show = get_cli_state(ctx).show_progress
    with managed_rich_observer(show) as observer:
        report = asyncio.run(
            run_survey(
                settings,
                project_root=root,
                db_path=db_path,
                resume=resume,
                skip_scrape=skip_scrape,
                author=author,
                criteria=criteria,
                post_year_min=post_year_min,
                post_year_max=post_year_max,
                observer=observer,
                show_rich_progress=show,
            )
        )

    _survey_print_report(report, output_format=get_cli_state(ctx).output_format)
