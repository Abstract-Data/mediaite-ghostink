"""Analyze subcommand — change-point, time-series, drift, convergence, comparison."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from forensics.cli._helpers import config_fingerprint
from forensics.config import get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.storage.repository import insert_analysis_run

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalyzeFlags:
    """Boolean flags for ``run_analyze`` routing."""

    changepoint: bool = False
    timeseries: bool = False
    drift: bool = False
    convergence: bool = False
    compare: bool = False
    ai_baseline: bool = False
    skip_generation: bool = False
    verify_corpus: bool = False


def _write_run_metadata(
    analysis_dir: Path,
    *,
    rid: str,
    meta: dict[str, object],
) -> None:
    (analysis_dir / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _run_compare_only_flow(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    root: Path,
    author: str | None,
) -> None:
    from forensics.analysis.orchestrator import run_compare_only

    rid = insert_analysis_run(
        db_path,
        config_hash=config_fingerprint(),
        description="forensics analyze --compare",
    )
    analysis_dir = root / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": rid,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "config_hash": config_fingerprint(),
        "compare_only": True,
        "author": author,
    }
    _write_run_metadata(analysis_dir, rid=rid, meta=meta)
    run_compare_only(settings, project_root=root, db_path=db_path, author_slug=author)
    logger.info("analyze: compare-only complete author=%s", author or "all")


def _resolve_mode_flags(flags: AnalyzeFlags) -> tuple[bool, bool, bool, bool]:
    explicit = (
        flags.changepoint
        or flags.timeseries
        or flags.drift
        or flags.ai_baseline
        or flags.convergence
        or flags.compare
    )
    if explicit:
        return flags.changepoint, flags.timeseries, flags.drift, flags.convergence
    return False, True, False, True


def _run_changepoint_stage(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    root: Path,
    author: str | None,
) -> None:
    from forensics.analysis.changepoint import run_changepoint_analysis

    run_changepoint_analysis(db_path, settings, project_root=root, author_slug=author)


def _run_timeseries_stage(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    root: Path,
    author: str | None,
) -> None:
    from forensics.analysis.timeseries import run_timeseries_analysis

    run_timeseries_analysis(db_path, settings, project_root=root, author_slug=author)


def _run_drift_stage(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    root: Path,
    author: str | None,
) -> None:
    from forensics.analysis.drift import run_drift_analysis

    run_drift_analysis(db_path, settings, project_root=root, author_slug=author)


def _run_full_analysis_stage(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    root: Path,
    author: str | None,
) -> None:
    from forensics.analysis.orchestrator import run_full_analysis

    asyncio.run(
        run_full_analysis(
            db_path,
            root / "data" / "features",
            root / "data" / "embeddings",
            settings,
            project_root=root,
            author_slug=author,
        )
    )


def _run_ai_baseline_stage(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    root: Path,
    author: str | None,
    skip_generation: bool,
    articles_per_cell: int | None,
    baseline_model: str | None,
) -> None:
    from forensics.analysis.drift import run_ai_baseline_command

    try:
        run_ai_baseline_command(
            db_path,
            settings,
            project_root=root,
            author_slug=author,
            skip_generation=skip_generation,
            articles_per_cell=articles_per_cell,
            model_filter=baseline_model,
        )
    except ValueError as exc:
        logger.error("ai-baseline failed: %s", exc)
        raise typer.Exit(code=1) from exc


def run_analyze(
    *,
    changepoint: bool = False,
    timeseries: bool = False,
    drift: bool = False,
    convergence: bool = False,
    compare: bool = False,
    ai_baseline: bool = False,
    skip_generation: bool = False,
    verify_corpus: bool = False,
    baseline_model: str | None = None,
    articles_per_cell: int | None = None,
    author: str | None = None,
) -> None:
    """Execute the analyze stage as a plain Python function.

    Kept separate from the Typer ``analyze`` callback so the `forensics all`
    orchestrator can call this without fighting Typer's option defaults.
    """
    flags = AnalyzeFlags(
        changepoint=changepoint,
        timeseries=timeseries,
        drift=drift,
        convergence=convergence,
        compare=compare,
        ai_baseline=ai_baseline,
        skip_generation=skip_generation,
        verify_corpus=verify_corpus,
    )

    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"
    analysis_dir = root / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    if flags.verify_corpus:
        from forensics.utils.provenance import verify_corpus_hash

        ok, message = verify_corpus_hash(db_path, analysis_dir)
        if not ok:
            logger.error("corpus hash verification failed: %s", message)
            raise typer.Exit(code=1)
        logger.info("corpus hash verified (%s)", message)

    if flags.compare and not (
        flags.changepoint
        or flags.timeseries
        or flags.drift
        or flags.ai_baseline
        or flags.convergence
    ):
        _run_compare_only_flow(db_path, settings, root=root, author=author)
        return

    do_changepoint, do_timeseries, do_drift, do_full_analysis = _resolve_mode_flags(flags)

    rid = insert_analysis_run(
        db_path,
        config_hash=config_fingerprint(),
        description="forensics analyze",
    )
    meta = {
        "run_id": rid,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "config_hash": config_fingerprint(),
        "changepoint": do_changepoint,
        "timeseries": do_timeseries,
        "drift": do_drift,
        "convergence_full": do_full_analysis,
        "author": author,
    }
    _write_run_metadata(analysis_dir, rid=rid, meta=meta)

    if do_changepoint:
        _run_changepoint_stage(db_path, settings, root=root, author=author)
    if do_timeseries:
        _run_timeseries_stage(db_path, settings, root=root, author=author)
    if do_drift:
        _run_drift_stage(db_path, settings, root=root, author=author)
    if do_full_analysis:
        _run_full_analysis_stage(db_path, settings, root=root, author=author)
    if flags.ai_baseline:
        _run_ai_baseline_stage(
            db_path,
            settings,
            root=root,
            author=author,
            skip_generation=flags.skip_generation,
            articles_per_cell=articles_per_cell,
            baseline_model=baseline_model,
        )
    logger.info(
        "analyze: completed (changepoint=%s, timeseries=%s, drift=%s, "
        "full_analysis=%s, ai_baseline=%s, author=%s)",
        do_changepoint,
        do_timeseries,
        do_drift,
        do_full_analysis,
        flags.ai_baseline,
        author or "all",
    )


def analyze(
    changepoint: Annotated[
        bool,
        typer.Option("--changepoint", help="Run change-point detection (PELT/BOCPD)"),
    ] = False,
    timeseries: Annotated[
        bool,
        typer.Option("--timeseries", help="Run rolling statistics + STL decomposition"),
    ] = False,
    drift: Annotated[
        bool,
        typer.Option("--drift", help="Run embedding drift analysis (Phase 6)"),
    ] = False,
    convergence: Annotated[
        bool,
        typer.Option(
            "--convergence",
            help="Cross-validate pipelines and run hypothesis tests (Phase 7)",
        ),
    ] = False,
    compare: Annotated[
        bool,
        typer.Option("--compare", help="Control author comparison only (Phase 7)"),
    ] = False,
    ai_baseline: Annotated[
        bool,
        typer.Option("--ai-baseline", help="Generate or refresh synthetic AI baseline articles"),
    ] = False,
    skip_generation: Annotated[
        bool,
        typer.Option(
            "--skip-generation",
            help="With --ai-baseline: re-embed existing JSON articles only",
        ),
    ] = False,
    verify_corpus: Annotated[
        bool,
        typer.Option(
            "--verify-corpus",
            help="Verify corpus hash against data/analysis/corpus_custody.json",
        ),
    ] = False,
    baseline_model: Annotated[
        str | None,
        typer.Option(
            "--baseline-model",
            metavar="MODEL",
            help="With --ai-baseline: restrict to one configured Ollama model",
        ),
    ] = None,
    articles_per_cell: Annotated[
        int | None,
        typer.Option(
            "--articles-per-cell",
            metavar="N",
            help="With --ai-baseline: override articles_per_cell (default from config)",
        ),
    ] = None,
    author: Annotated[
        str | None,
        typer.Option("--author", metavar="SLUG", help="Limit to one author slug"),
    ] = None,
) -> None:
    """Run analysis pipeline (change-point, drift, convergence, comparison)."""
    run_analyze(
        changepoint=changepoint,
        timeseries=timeseries,
        drift=drift,
        convergence=convergence,
        compare=compare,
        ai_baseline=ai_baseline,
        skip_generation=skip_generation,
        verify_corpus=verify_corpus,
        baseline_model=baseline_model,
        articles_per_cell=articles_per_cell,
        author=author,
    )
