"""Survey subcommand — blind newsroom-wide AI-adoption analysis (Phase 12 §1f)."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Annotated

import typer

from forensics.config import get_project_root, get_settings
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


@survey_app.callback(invoke_without_command=True)
def survey(
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
) -> None:
    """Run a blind newsroom survey — analyze all qualified authors."""
    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"

    overrides: dict[str, int] = {}
    if min_articles is not None:
        overrides["min_articles"] = min_articles
    if min_span_days is not None:
        overrides["min_span_days"] = min_span_days
    criteria = replace(QualificationCriteria.from_settings(settings.survey), **overrides)

    if dry_run:
        qualified, disqualified = qualify_authors(db_path, criteria)
        typer.echo("")
        typer.echo(f"Qualified: {len(qualified)} authors")
        typer.echo(f"Disqualified: {len(disqualified)} authors")
        typer.echo("")
        for qa in qualified:
            typer.echo(
                f"  {qa.author.name:<30} {qa.total_articles:>5} articles  "
                f"{qa.date_range_days:>5}d span  {qa.articles_per_year:>5.1f}/yr"
            )
        if disqualified:
            typer.echo("")
            typer.echo(f"Disqualified ({len(disqualified)}):")
            for dq in disqualified[:10]:
                typer.echo(f"  {dq.author.name:<30} reason: {dq.disqualification_reason}")
            if len(disqualified) > 10:
                typer.echo(f"  ... and {len(disqualified) - 10} more")
        raise typer.Exit(0)

    from forensics.survey.orchestrator import run_survey

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
        )
    )

    typer.echo("")
    typer.echo("=" * 70)
    typer.echo(f"SURVEY COMPLETE — run_id={report.run_id}")
    typer.echo(f"{len(report.results)} authors analyzed")
    typer.echo("=" * 70)
    typer.echo("")

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
        typer.echo("")
        typer.echo(f"Natural control cohort: {len(report.natural_controls)} author(s)")

    if report.run_dir is not None:
        typer.echo("")
        typer.echo(f"Full results: {report.run_dir}")
