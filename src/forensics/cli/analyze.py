"""Analyze CLI: default callback plus nested commands (e.g. ``section-profile``)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import typer

from forensics.analysis.orchestrator.mode import AnalysisMode
from forensics.cli._decorators import examples_epilog, forensics_examples, with_examples
from forensics.cli._errors import fail
from forensics.cli._exit import ExitCode
from forensics.cli.analyze_dispatch import dispatch_analysis_stages, write_run_metadata
from forensics.cli.analyze_models import (
    AnalyzeBaselineParams,
    AnalyzeContext,
    AnalyzeCustodyParams,
    AnalyzeRequest,
    AnalyzeStageFlags,
    AnalyzeSubcommandPaths,
    resolve_analyze_subcommand_context,
)
from forensics.cli.analyze_options import (
    AnalyzeAiBaselineFlag,
    AnalyzeAllowPrePhase16EmbeddingsFlag,
    AnalyzeArticlesPerCellOption,
    AnalyzeAuthorOption,
    AnalyzeBaselineModelOption,
    AnalyzeChangepointFlag,
    AnalyzeCompareFlag,
    AnalyzeComparePairOption,
    AnalyzeConvergenceFlag,
    AnalyzeDriftFlag,
    AnalyzeExploratoryFlag,
    AnalyzeIncludeAdvertorialFlag,
    AnalyzeIncludeSharedBylinesFlag,
    AnalyzeLogAllGenerationsFlag,
    AnalyzeMaxWorkersOption,
    AnalyzeParallelAuthorsFlag,
    AnalyzeResidualizeSectionsFlag,
    AnalyzeSkipGenerationFlag,
    AnalyzeTimeseriesFlag,
    AnalyzeVerifyCorpusFlag,
    AnalyzeVerifyRawArchivesFlag,
)
from forensics.cli.analyze_section import register_analyze_section_commands
from forensics.config import DEFAULT_DB_RELATIVE, get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.pipeline_context import PipelineContext  # noqa: F401 — tests monkeypatch this
from forensics.preregistration import VerificationResult, verify_preregistration
from forensics.storage.repository import Repository
from forensics.survey.shared_byline import is_shared_byline as _is_shared_byline_heuristic

logger = logging.getLogger(__name__)

__all__ = [
    "AnalyzeBaselineParams",
    "AnalyzeContext",
    "AnalyzeCustodyParams",
    "AnalyzeRequest",
    "AnalyzeStageFlags",
    "AnalyzeSubcommandPaths",
    "analyze",
    "analyze_app",
    "resolve_analyze_subcommand_context",
    "run_analyze",
]

_ANALYZE_EXAMPLES = (
    "forensics analyze --author isaac-schorr",
    "forensics analyze --compare-pair isaac-schorr,john-doe",
    "forensics analyze --parallel-authors --max-workers 4",
)

analyze_app = typer.Typer(
    name="analyze",
    help="Run analysis pipeline (change-point, drift, convergence, comparison).",
    no_args_is_help=False,
    invoke_without_command=True,
    epilog=examples_epilog(*_ANALYZE_EXAMPLES),
)

register_analyze_section_commands(analyze_app)


def _analyze_request_from_cli(
    *,
    changepoint: bool,
    timeseries: bool,
    drift: bool,
    convergence: bool,
    compare: bool,
    ai_baseline: bool,
    skip_generation: bool,
    verify_corpus: bool | None,
    verify_raw_archives: bool | None,
    log_all_generations: bool | None,
    baseline_model: str | None,
    articles_per_cell: int | None,
    author: str | None,
    exploratory: bool,
    include_advertorial: bool,
    residualize_sections: bool,
    include_shared_bylines: bool,
    max_workers: int | None,
    compare_pair: str | None,
    parallel_authors: bool,
    allow_pre_phase16_embeddings: bool,
    typer_context: typer.Context | None,
) -> AnalyzeRequest:
    parsed_pair = _parse_compare_pair(compare_pair)
    return AnalyzeRequest(
        stages=AnalyzeStageFlags(
            changepoint=changepoint,
            timeseries=timeseries,
            drift=drift,
            convergence=convergence,
            compare=compare,
            ai_baseline=ai_baseline,
            parallel_authors=parallel_authors,
        ),
        baseline=AnalyzeBaselineParams(
            skip_generation=skip_generation,
            baseline_model=baseline_model,
            articles_per_cell=articles_per_cell,
        ),
        custody=AnalyzeCustodyParams(
            verify_corpus=verify_corpus,
            verify_raw_archives=verify_raw_archives,
            log_all_generations=log_all_generations,
        ),
        author=author,
        include_advertorial=include_advertorial,
        residualize_sections=residualize_sections,
        include_shared_bylines=include_shared_bylines,
        max_workers=max_workers,
        compare_pair=parsed_pair,
        analysis_mode=AnalysisMode(
            exploratory=exploratory,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
        ),
        typer_context=typer_context,
    )


def _parse_compare_pair(raw: str | None) -> tuple[str, str] | None:
    """Parse ``TARGET,CONTROL`` for ``--compare-pair``; ``None`` if ``raw`` is unset."""
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 2 or not all(parts):
        msg = (
            f"--compare-pair expected 'TARGET,CONTROL' (got {raw!r}); "
            "both slugs must be non-empty and separated by a single comma."
        )
        raise typer.BadParameter(msg)
    return parts[0], parts[1]


def _enforce_shared_byline_gate(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    author_slug: str,
    include_shared_bylines: bool,
) -> None:
    """Block shared-byline authors unless ``--include-shared-bylines``.

    Uses DB ``is_shared_byline`` and slug heuristic.
    """
    if include_shared_bylines:
        return
    flagged = False
    matched_name: str | None = None
    matched_outlet: str | None = None
    with Repository(db_path) as repo:
        author = repo.get_author_by_slug(author_slug)
    if author is not None:
        flagged = bool(author.is_shared_byline)
        matched_name = author.name
        matched_outlet = author.outlet
    if not flagged:
        configured = next((a for a in settings.authors if a.slug == author_slug), None)
        if configured is not None:
            matched_name = matched_name or configured.name
            matched_outlet = matched_outlet or configured.outlet
        flagged = _is_shared_byline_heuristic(
            author_slug,
            matched_name or author_slug,
            matched_outlet or "",
        )
    if not flagged:
        return
    msg = (
        f"author '{author_slug}' is a shared byline (group account) and is "
        "disqualified by the Phase 15 D survey gate. Pass "
        "--include-shared-bylines to override."
    )
    logger.error(msg)
    raise typer.BadParameter(msg, param_hint="--author")


def _apply_per_run_overrides(
    settings: ForensicsSettings,
    *,
    include_advertorial: bool,
    residualize_sections: bool,
) -> ForensicsSettings:
    """Per-run advertorial and section-residualization overrides.

    Model copies only; does not mutate the ``get_settings()`` cache.
    """
    if include_advertorial:
        settings = settings.model_copy(
            update={
                "features": settings.features.model_copy(update={"excluded_sections": frozenset()}),
                "survey": settings.survey.model_copy(update={"excluded_sections": frozenset()}),
            }
        )
    if residualize_sections:
        settings = settings.model_copy(
            update={
                "analysis": settings.analysis.model_copy(
                    update={
                        "hypothesis": settings.analysis.hypothesis.model_copy(
                            update={"section_residualize_features": True}
                        ),
                    },
                ),
            }
        )
    return settings


def _verify_corpus_stage(
    *,
    db_path: Path,
    analysis_dir: Path,
    verify_corpus: bool,
    typer_context: typer.Context | None,
) -> None:
    """Chain-of-custody corpus hash check before analysis stages."""
    if not verify_corpus:
        return
    from forensics.utils.provenance import verify_corpus_hash

    ok, message = verify_corpus_hash(db_path, analysis_dir)
    if not ok:
        if "Corpus hash mismatch" in message:
            raise fail(
                typer_context,
                "analyze",
                "corpus_hash_mismatch",
                message,
                exit_code=ExitCode.CONFLICT,
            )
        if "No custody record" in message:
            raise fail(
                typer_context,
                "analyze",
                "corpus_custody_missing",
                message,
                exit_code=ExitCode.AUTH_OR_RESOURCE,
            )
        raise fail(
            typer_context,
            "analyze",
            "corpus_hash_error",
            message,
            exit_code=ExitCode.GENERAL_ERROR,
        )
    logger.info("corpus hash verified (%s)", message)


def _gate_preregistration(
    request: AnalyzeRequest,
    *,
    preregistration: VerificationResult,
    analysis_dir: Path,
) -> None:
    """Hard-stop when preregistration is not satisfied and run is confirmatory."""
    if preregistration.status == "ok" or request.analysis_mode.exploratory:
        return
    meta = {
        "run_timestamp": datetime.now(UTC).isoformat(),
        "last_processed_author": request.author,
        "authors_in_run": ([request.author] if request.author else []),
        "preregistration_status": preregistration.status,
        "preregistration_message": preregistration.message,
        "exploratory": False,
        "allow_pre_phase16_embeddings": request.analysis_mode.allow_pre_phase16_embeddings,
    }
    write_run_metadata(analysis_dir, rid="preregistration-blocked", meta=meta)
    raise fail(
        request.typer_context,
        "analyze",
        "preregistration_not_locked",
        preregistration.message,
        exit_code=ExitCode.CONFLICT,
        suggestion="run: forensics --yes lock-preregistration (or pass --exploratory to bypass)",
    )


def run_analyze(request: AnalyzeRequest) -> None:
    """Run analyze stages (callable from Typer and from ``forensics all``)."""
    settings = _apply_per_run_overrides(
        get_settings(),
        include_advertorial=request.include_advertorial,
        residualize_sections=request.residualize_sections,
    )
    coc_updates: dict[str, bool] = {}
    if request.custody.verify_raw_archives is not None:
        coc_updates["verify_raw_archives"] = request.custody.verify_raw_archives
    if request.custody.log_all_generations is not None:
        coc_updates["log_all_generations"] = request.custody.log_all_generations
    if coc_updates:
        settings = settings.model_copy(
            update={
                "chain_of_custody": settings.chain_of_custody.model_copy(update=coc_updates),
            }
        )
    root = get_project_root()
    db_path = root / DEFAULT_DB_RELATIVE
    if request.author is not None:
        _enforce_shared_byline_gate(
            db_path,
            settings,
            author_slug=request.author,
            include_shared_bylines=request.include_shared_bylines,
        )
    ctx = AnalyzeContext.build(
        db_path,
        settings,
        root=root,
        author=request.author,
        max_workers=request.max_workers,
        compare_pair=request.compare_pair,
        analysis_mode=request.analysis_mode,
    )
    analysis_dir = ctx.paths.analysis_dir

    verify_corpus = request.custody.verify_corpus
    if verify_corpus is None:
        verify_corpus = settings.chain_of_custody.verify_corpus_hash

    _verify_corpus_stage(
        db_path=db_path,
        analysis_dir=analysis_dir,
        verify_corpus=verify_corpus,
        typer_context=request.typer_context,
    )

    preregistration = verify_preregistration(settings)
    _gate_preregistration(request, preregistration=preregistration, analysis_dir=analysis_dir)

    dispatch_analysis_stages(
        request,
        ctx=ctx,
        analysis_dir=analysis_dir,
        preregistration=preregistration,
    )


@analyze_app.callback(invoke_without_command=True)
@with_examples(*_ANALYZE_EXAMPLES)
def analyze(
    ctx: typer.Context,
    changepoint: AnalyzeChangepointFlag = False,
    timeseries: AnalyzeTimeseriesFlag = False,
    drift: AnalyzeDriftFlag = False,
    convergence: AnalyzeConvergenceFlag = False,
    compare: AnalyzeCompareFlag = False,
    ai_baseline: AnalyzeAiBaselineFlag = False,
    skip_generation: AnalyzeSkipGenerationFlag = False,
    verify_corpus: AnalyzeVerifyCorpusFlag = None,
    verify_raw_archives: AnalyzeVerifyRawArchivesFlag = None,
    log_all_generations: AnalyzeLogAllGenerationsFlag = None,
    baseline_model: AnalyzeBaselineModelOption = None,
    articles_per_cell: AnalyzeArticlesPerCellOption = None,
    author: AnalyzeAuthorOption = None,
    exploratory: AnalyzeExploratoryFlag = False,
    include_advertorial: AnalyzeIncludeAdvertorialFlag = False,
    residualize_sections: AnalyzeResidualizeSectionsFlag = False,
    include_shared_bylines: AnalyzeIncludeSharedBylinesFlag = False,
    max_workers: AnalyzeMaxWorkersOption = None,
    parallel_authors: AnalyzeParallelAuthorsFlag = False,
    compare_pair: AnalyzeComparePairOption = None,
    allow_pre_phase16_embeddings: AnalyzeAllowPrePhase16EmbeddingsFlag = False,
) -> None:
    """Run analysis pipeline (change-point, drift, convergence, comparison)."""
    if ctx.invoked_subcommand is not None:
        return
    run_analyze(
        _analyze_request_from_cli(
            changepoint=changepoint,
            timeseries=timeseries,
            drift=drift,
            convergence=convergence,
            compare=compare,
            ai_baseline=ai_baseline,
            skip_generation=skip_generation,
            verify_corpus=verify_corpus,
            verify_raw_archives=verify_raw_archives,
            log_all_generations=log_all_generations,
            baseline_model=baseline_model,
            articles_per_cell=articles_per_cell,
            author=author,
            exploratory=exploratory,
            include_advertorial=include_advertorial,
            residualize_sections=residualize_sections,
            include_shared_bylines=include_shared_bylines,
            max_workers=max_workers,
            compare_pair=compare_pair,
            parallel_authors=parallel_authors,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
            typer_context=ctx,
        )
    )


_RUN_EPILOG, _run_ex = forensics_examples(
    "forensics analyze run --author colby-hall --drift --convergence",
)


@analyze_app.command(name="run", epilog=_RUN_EPILOG)
@_run_ex
def analyze_run(
    ctx: typer.Context,
    changepoint: AnalyzeChangepointFlag = False,
    timeseries: AnalyzeTimeseriesFlag = False,
    drift: AnalyzeDriftFlag = False,
    convergence: AnalyzeConvergenceFlag = False,
    compare: AnalyzeCompareFlag = False,
    ai_baseline: AnalyzeAiBaselineFlag = False,
    skip_generation: AnalyzeSkipGenerationFlag = False,
    verify_corpus: AnalyzeVerifyCorpusFlag = None,
    verify_raw_archives: AnalyzeVerifyRawArchivesFlag = None,
    log_all_generations: AnalyzeLogAllGenerationsFlag = None,
    baseline_model: AnalyzeBaselineModelOption = None,
    articles_per_cell: AnalyzeArticlesPerCellOption = None,
    author: AnalyzeAuthorOption = None,
    exploratory: AnalyzeExploratoryFlag = False,
    include_advertorial: AnalyzeIncludeAdvertorialFlag = False,
    residualize_sections: AnalyzeResidualizeSectionsFlag = False,
    include_shared_bylines: AnalyzeIncludeSharedBylinesFlag = False,
    max_workers: AnalyzeMaxWorkersOption = None,
    parallel_authors: AnalyzeParallelAuthorsFlag = False,
    compare_pair: AnalyzeComparePairOption = None,
    allow_pre_phase16_embeddings: AnalyzeAllowPrePhase16EmbeddingsFlag = False,
) -> None:
    """Explicit entrypoint (same flags as ``forensics analyze`` with no subcommand)."""
    run_analyze(
        _analyze_request_from_cli(
            changepoint=changepoint,
            timeseries=timeseries,
            drift=drift,
            convergence=convergence,
            compare=compare,
            ai_baseline=ai_baseline,
            skip_generation=skip_generation,
            verify_corpus=verify_corpus,
            verify_raw_archives=verify_raw_archives,
            log_all_generations=log_all_generations,
            baseline_model=baseline_model,
            articles_per_cell=articles_per_cell,
            author=author,
            exploratory=exploratory,
            include_advertorial=include_advertorial,
            residualize_sections=residualize_sections,
            include_shared_bylines=include_shared_bylines,
            max_workers=max_workers,
            compare_pair=compare_pair,
            parallel_authors=parallel_authors,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
            typer_context=ctx,
        )
    )


_CO_EPILOG, _co_ex = forensics_examples("forensics analyze compare-only --compare")


@analyze_app.command(name="compare-only", epilog=_CO_EPILOG)
@_co_ex
def analyze_compare_only(
    ctx: typer.Context,
    verify_corpus: AnalyzeVerifyCorpusFlag = None,
    author: AnalyzeAuthorOption = None,
    exploratory: AnalyzeExploratoryFlag = False,
    include_shared_bylines: AnalyzeIncludeSharedBylinesFlag = False,
    compare_pair: AnalyzeComparePairOption = None,
    allow_pre_phase16_embeddings: AnalyzeAllowPrePhase16EmbeddingsFlag = False,
) -> None:
    """Re-run target/control comparisons only (``--compare`` without other stages)."""
    run_analyze(
        _analyze_request_from_cli(
            changepoint=False,
            timeseries=False,
            drift=False,
            convergence=False,
            compare=True,
            ai_baseline=False,
            skip_generation=False,
            verify_corpus=verify_corpus,
            verify_raw_archives=None,
            log_all_generations=None,
            baseline_model=None,
            articles_per_cell=None,
            author=author,
            exploratory=exploratory,
            include_advertorial=False,
            residualize_sections=False,
            include_shared_bylines=include_shared_bylines,
            max_workers=None,
            compare_pair=compare_pair,
            parallel_authors=False,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
            typer_context=ctx,
        )
    )
