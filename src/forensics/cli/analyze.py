"""Analyze subcommand — change-point, time-series, drift, convergence."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Annotated

import typer

from forensics.cli._helpers import config_fingerprint
from forensics.config import get_project_root, get_settings
from forensics.storage.repository import insert_analysis_run
from forensics.utils.provenance import compute_corpus_hash

logger = logging.getLogger(__name__)


def run_analyze(
    *,
    changepoint: bool,
    timeseries: bool,
    drift: bool,
    convergence: bool,
    compare: bool,
    ai_baseline: bool,
    skip_generation: bool,
    verify_corpus: bool,
    author: str | None,
    openai_key: str | None,
    llm_model: str,
) -> int:
    """Core analyze stage; returns process exit code."""
    from forensics.analysis.changepoint import run_changepoint_analysis
    from forensics.analysis.drift import run_ai_baseline_command, run_drift_analysis
    from forensics.analysis.orchestrator import run_compare_only, run_full_analysis
    from forensics.analysis.timeseries import run_timeseries_analysis

    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"
    analysis_dir = root / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    corpus_hash = compute_corpus_hash(db_path)

    if verify_corpus:
        from forensics.baseline.custody import verify_raw_archive_integrity
        from forensics.utils.provenance import audit_scrape_timestamps

        if settings.chain_of_custody.verify_raw_archives and not verify_raw_archive_integrity(
            root / "data",
        ):
            logger.error("analyze: raw archive integrity check failed (--verify-corpus)")
            return 1
        aud = audit_scrape_timestamps(db_path)
        logger.info(
            "analyze: scrape audit total=%s with_scraped_at=%s missing=%s window_days=%s",
            aud.get("total_articles"),
            aud.get("articles_with_scraped_at"),
            aud.get("missing_scraped_at"),
            aud.get("scrape_duration_days"),
        )

    want_cp = changepoint
    want_ts = timeseries
    want_drift = drift
    want_ai = ai_baseline
    want_conv = convergence
    want_cmp = compare
    explicit = want_cp or want_ts or want_drift or want_ai or want_conv or want_cmp

    author_slug = author

    if want_cmp and not (want_cp or want_ts or want_drift or want_ai or want_conv):
        rid = insert_analysis_run(
            db_path,
            config_hash=config_fingerprint(),
            description="forensics analyze --compare",
            input_corpus_hash=corpus_hash,
        )
        meta = {
            "run_id": rid,
            "run_timestamp": datetime.now(UTC).isoformat(),
            "config_hash": config_fingerprint(),
            "compare_only": True,
            "author": author_slug,
        }
        (analysis_dir / "run_metadata.json").write_text(
            json.dumps(meta, indent=2),
            encoding="utf-8",
        )
        run_compare_only(settings, project_root=root, db_path=db_path, author_slug=author_slug)
        logger.info("analyze: compare-only complete author=%s", author_slug or "all")
        return 0

    if explicit:
        do_changepoint = want_cp
        do_timeseries = want_ts
        do_drift = want_drift
        do_full_analysis = want_conv
    else:
        do_changepoint = False
        do_timeseries = True
        do_drift = False
        do_full_analysis = True

    rid = insert_analysis_run(
        db_path,
        config_hash=config_fingerprint(),
        description="forensics analyze",
        input_corpus_hash=corpus_hash,
    )
    meta = {
        "run_id": rid,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "config_hash": config_fingerprint(),
        "changepoint": do_changepoint,
        "timeseries": do_timeseries,
        "drift": do_drift,
        "convergence_full": do_full_analysis,
        "author": author_slug,
    }
    (analysis_dir / "run_metadata.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )

    if do_changepoint:
        run_changepoint_analysis(
            db_path,
            settings,
            project_root=root,
            author_slug=author_slug,
        )
    if do_timeseries:
        run_timeseries_analysis(
            db_path,
            settings,
            project_root=root,
            author_slug=author_slug,
        )
    if do_drift:
        run_drift_analysis(
            db_path,
            settings,
            project_root=root,
            author_slug=author_slug,
        )
    if do_full_analysis:
        asyncio.run(
            run_full_analysis(
                db_path,
                root / "data" / "features",
                root / "data" / "embeddings",
                settings,
                project_root=root,
                author_slug=author_slug,
            )
        )
    if want_ai:
        run_ai_baseline_command(
            db_path,
            settings,
            project_root=root,
            author_slug=author_slug,
            skip_generation=skip_generation,
            openai_key=openai_key,
            llm_model=llm_model,
        )
    logger.info(
        "analyze: completed (changepoint=%s, timeseries=%s, drift=%s, "
        "full_analysis=%s, ai_baseline=%s, author=%s)",
        do_changepoint,
        do_timeseries,
        do_drift,
        do_full_analysis,
        want_ai,
        author_slug or "all",
    )
    return 0


def analyze(
    changepoint: Annotated[
        bool,
        typer.Option("--changepoint", help="Run change-point detection (PELT/BOCPD)"),
    ] = False,
    timeseries: Annotated[
        bool,
        typer.Option("--timeseries", help="Run rolling statistics + STL-style decomposition"),
    ] = False,
    drift: Annotated[
        bool,
        typer.Option("--drift", help="Run embedding drift analysis"),
    ] = False,
    convergence: Annotated[
        bool,
        typer.Option("--convergence", help="Phase 7 synthesis: convergence, hypothesis tests"),
    ] = False,
    compare: Annotated[
        bool,
        typer.Option("--compare", help="Target vs control comparison only"),
    ] = False,
    ai_baseline: Annotated[
        bool,
        typer.Option("--ai-baseline", help="Synthetic AI baseline articles + embeddings"),
    ] = False,
    skip_generation: Annotated[
        bool,
        typer.Option("--skip-generation", help="With --ai-baseline: re-embed only, no LLM"),
    ] = False,
    verify_corpus: Annotated[
        bool,
        typer.Option("--verify-corpus", help="Chain-of-custody checks before analysis"),
    ] = False,
    author: Annotated[
        str | None,
        typer.Option("--author", metavar="SLUG", help="Limit to one author slug"),
    ] = None,
    openai_key: Annotated[
        str | None,
        typer.Option("--openai-key", metavar="KEY", help="API key for --ai-baseline"),
    ] = None,
    llm_model: Annotated[
        str,
        typer.Option("--llm-model", metavar="MODEL", help="Chat model for --ai-baseline"),
    ] = "gpt-4o",
) -> None:
    """Run analysis pipeline (change-point, time-series, drift, convergence)."""
    try:
        rc = run_analyze(
            changepoint=changepoint,
            timeseries=timeseries,
            drift=drift,
            convergence=convergence,
            compare=compare,
            ai_baseline=ai_baseline,
            skip_generation=skip_generation,
            verify_corpus=verify_corpus,
            author=author,
            openai_key=openai_key,
            llm_model=llm_model,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=1) from exc
    raise typer.Exit(code=rc)
