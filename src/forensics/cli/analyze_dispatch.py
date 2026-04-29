"""Serial and early-exit dispatch for ``forensics analyze`` (split from analyze.py).

Full multi-author analysis (convergence slice) is delegated to
:func:`forensics.analysis.orchestrator.runner.run_full_analysis` via
``_run_full_analysis_stage``. Optional upstream stages stay here so
``run_full_analysis`` remains focused on the per-author + comparison core
(RF-ARCH-001).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import typer

from forensics.analysis.drift import EmbeddingDriftInputsError, EmbeddingRevisionGateError
from forensics.cli._errors import fail
from forensics.cli._exit import ExitCode
from forensics.cli.analyze_models import (
    AnalyzeContext,
    AnalyzeRequest,
    AnalyzeStageFlags,
)
from forensics.pipeline_context import PipelineContext
from forensics.preregistration import VerificationResult
from forensics.storage.json_io import write_json_artifact

logger = logging.getLogger(__name__)


def write_run_metadata(
    analysis_dir: Path,
    *,
    rid: str,
    meta: dict[str, object],
) -> None:
    write_json_artifact(analysis_dir / "run_metadata.json", meta)


def _run_compare_only_flow(ctx: AnalyzeContext) -> None:
    from forensics.analysis.orchestrator import run_compare_only

    pipeline_ctx = PipelineContext.resolve()
    rid = pipeline_ctx.record_audit("forensics analyze --compare", optional=False, log=logger)
    assert rid is not None
    analysis_dir = ctx.paths.analysis_dir
    meta = {
        "run_id": rid,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "config_hash": pipeline_ctx.config_hash,
        "compare_only": True,
        "last_processed_author": ctx.author_slug,
        "authors_in_run": ([ctx.author_slug] if ctx.author_slug else []),
        "compare_pair": list(ctx.compare_pair) if ctx.compare_pair else None,
    }
    write_run_metadata(analysis_dir, rid=rid, meta=meta)
    run_compare_only(
        ctx.settings,
        paths=ctx.paths,
        author_slug=ctx.author_slug,
        compare_pair=ctx.compare_pair,
        mode=ctx.analysis_mode,
    )
    logger.info("analyze: compare-only complete author=%s", ctx.author_slug or "all")


def _resolve_mode_flags(
    *,
    changepoint: bool,
    timeseries: bool,
    drift: bool,
    convergence: bool,
    compare: bool,
    ai_baseline: bool,
) -> tuple[bool, bool, bool, bool]:
    explicit = changepoint or timeseries or drift or ai_baseline or convergence or compare
    if explicit:
        return changepoint, timeseries, drift, convergence
    return False, True, False, True


def _run_changepoint_stage(ctx: AnalyzeContext) -> None:
    from forensics.analysis.changepoint import run_changepoint_analysis

    run_changepoint_analysis(
        ctx.db_path, ctx.settings, project_root=ctx.root, author_slug=ctx.author_slug
    )


def _run_timeseries_stage(ctx: AnalyzeContext) -> None:
    from forensics.analysis.timeseries import run_timeseries_analysis

    run_timeseries_analysis(
        ctx.db_path, ctx.settings, project_root=ctx.root, author_slug=ctx.author_slug
    )


def _run_drift_stage(ctx: AnalyzeContext) -> None:
    from forensics.analysis.drift import run_drift_analysis

    run_drift_analysis(
        ctx.settings,
        paths=ctx.paths,
        author_slug=ctx.author_slug,
        mode=ctx.analysis_mode,
    )


def _run_full_analysis_stage(ctx: AnalyzeContext) -> None:
    from forensics.analysis.orchestrator import run_full_analysis

    run_full_analysis(
        ctx.paths,
        ctx.settings,
        author_slug=ctx.author_slug,
        max_workers=ctx.max_workers,
        compare_pair=ctx.compare_pair,
        mode=ctx.analysis_mode,
    )


def _raise_analyze_embedding_failure(
    typer_context: typer.Context | None,
    *,
    cmd: str,
    exc: BaseException,
) -> typer.Exit:
    if isinstance(exc, EmbeddingRevisionGateError):
        return fail(
            typer_context,
            cmd,
            "embedding_revision_gate",
            str(exc),
            exit_code=ExitCode.CONFLICT,
        )
    if isinstance(exc, EmbeddingDriftInputsError):
        return fail(
            typer_context,
            cmd,
            "embedding_drift_inputs",
            str(exc),
            exit_code=ExitCode.AUTH_OR_RESOURCE,
            suggestion=(
                "Run feature extraction with embeddings, pass --exploratory for permissive mode, "
                "or use --allow-pre-phase16-embeddings only when intentionally matching legacy "
                "vectors."
            ),
        )
    raise RuntimeError(f"unexpected embedding failure: {exc!r}") from exc


def _run_analyze_stage_embedding_guarded(
    request: AnalyzeRequest,
    *,
    cmd: str,
    runner: Callable[[], None],
) -> None:
    try:
        runner()
    except (EmbeddingDriftInputsError, EmbeddingRevisionGateError) as exc:
        raise _raise_analyze_embedding_failure(
            request.typer_context,
            cmd=cmd,
            exc=exc,
        ) from exc


def _run_parallel_author_refresh_stage(ctx: AnalyzeContext) -> None:
    from forensics.analysis.orchestrator import run_parallel_author_refresh

    pipeline_ctx = PipelineContext.resolve()
    rid = pipeline_ctx.record_audit(
        "forensics analyze --parallel-authors",
        optional=False,
        log=logger,
    )
    assert rid is not None
    analysis_dir = ctx.paths.analysis_dir
    write_run_metadata(
        analysis_dir,
        rid=rid,
        meta={
            "run_id": rid,
            "run_timestamp": datetime.now(UTC).isoformat(),
            "config_hash": pipeline_ctx.config_hash,
            "parallel_authors_preflight": True,
            "last_processed_author": ctx.author_slug,
            "authors_in_run": ([ctx.author_slug] if ctx.author_slug else []),
        },
    )

    results = run_parallel_author_refresh(
        ctx.paths,
        ctx.settings,
        author_slug=ctx.author_slug,
        max_workers=ctx.max_workers,
        mode=ctx.analysis_mode,
    )
    logger.info(
        "analyze: parallel author refresh complete refreshed=%d author=%s",
        len(results),
        ctx.author_slug or "all",
    )


def _run_ai_baseline_stage(
    ctx: AnalyzeContext,
    *,
    skip_generation: bool,
    articles_per_cell: int | None,
    baseline_model: str | None,
    typer_context: typer.Context | None,
) -> None:
    from forensics.cli.baseline import run_ai_baseline_command

    try:
        run_ai_baseline_command(
            ctx.db_path,
            ctx.settings,
            project_root=ctx.root,
            author_slug=ctx.author_slug,
            skip_generation=skip_generation,
            articles_per_cell=articles_per_cell,
            model_filter=baseline_model,
        )
    except ValueError as exc:
        raise fail(
            typer_context,
            "analyze",
            "ai_baseline_failed",
            str(exc),
            exit_code=ExitCode.GENERAL_ERROR,
        ) from exc


def _verify_requested_ai_baseline_vectors(
    ctx: AnalyzeContext,
    *,
    typer_context: typer.Context | None,
) -> None:
    from forensics.analysis.drift import load_ai_baseline_embeddings

    slugs = (
        [ctx.author_slug] if ctx.author_slug else [author.slug for author in ctx.settings.authors]
    )
    missing: list[str] = []
    for slug in slugs:
        if not ctx.paths.drift_json(slug).is_file():
            continue
        if not load_ai_baseline_embeddings(
            slug,
            ctx.paths,
            expected_dim=int(ctx.settings.analysis.embedding.embedding_vector_dim),
        ):
            missing.append(slug)
    if missing:
        raise fail(
            typer_context,
            "analyze",
            "ai_baseline_vectors_missing",
            (
                "ai-baseline requested but drift artifacts have no usable AI baseline vectors: "
                + ", ".join(missing)
            ),
            exit_code=ExitCode.AUTH_OR_RESOURCE,
        )


def _serial_stage_flags_set(sf: AnalyzeStageFlags) -> bool:
    return any(
        (
            sf.changepoint,
            sf.timeseries,
            sf.drift,
            sf.ai_baseline,
            sf.convergence,
        )
    )


def _conflicting_analyze_flags(sf: AnalyzeStageFlags, *, primary: str) -> list[str]:
    conflicts = [primary]
    if primary != "--compare" and sf.compare:
        conflicts.append("--compare")
    if primary != "--parallel-authors" and sf.parallel_authors:
        conflicts.append("--parallel-authors")
    if sf.changepoint:
        conflicts.append("--changepoint")
    if sf.timeseries:
        conflicts.append("--timeseries")
    if sf.drift:
        conflicts.append("--drift")
    if sf.ai_baseline:
        conflicts.append("--ai-baseline")
    if sf.convergence:
        conflicts.append("--convergence")
    return conflicts


def _compare_only_or_parallel_early_exit(
    request: AnalyzeRequest,
    *,
    ctx: AnalyzeContext,
    sf: AnalyzeStageFlags,
) -> bool:
    if sf.compare and (sf.parallel_authors or _serial_stage_flags_set(sf)):
        cflags = ", ".join(_conflicting_analyze_flags(sf, primary="--compare"))
        raise fail(
            request.typer_context,
            "analyze",
            "invalid_stage_flags",
            (
                "--compare (compare-only) cannot be combined with other analyze stages. "
                f"Conflicting flags: {cflags}."
            ),
            exit_code=ExitCode.USAGE_ERROR,
            suggestion=(
                "Use `forensics analyze compare-only`, or omit --compare for a full pipeline."
            ),
        )
    if sf.compare and not (
        sf.parallel_authors
        or sf.changepoint
        or sf.timeseries
        or sf.drift
        or sf.ai_baseline
        or sf.convergence
    ):
        _run_compare_only_flow(ctx)
        return True
    if sf.parallel_authors and (sf.compare or _serial_stage_flags_set(sf)):
        pflags = ", ".join(_conflicting_analyze_flags(sf, primary="--parallel-authors"))
        raise fail(
            request.typer_context,
            "analyze",
            "invalid_stage_flags",
            (
                "--parallel-authors cannot be combined with other analyze stages. "
                f"Conflicting flags: {pflags}."
            ),
            exit_code=ExitCode.USAGE_ERROR,
        )
    if sf.parallel_authors:
        _run_analyze_stage_embedding_guarded(
            request,
            cmd="analyze.parallel_refresh",
            runner=lambda: _run_parallel_author_refresh_stage(ctx),
        )
        return True
    return False


def _run_serial_analyze_stages(
    request: AnalyzeRequest,
    *,
    ctx: AnalyzeContext,
    analysis_dir: Path,
    preregistration: VerificationResult,
    sf: AnalyzeStageFlags,
) -> None:
    do_changepoint, do_timeseries, do_drift, do_full_analysis = _resolve_mode_flags(
        changepoint=sf.changepoint,
        timeseries=sf.timeseries,
        drift=sf.drift,
        convergence=sf.convergence,
        compare=sf.compare,
        ai_baseline=sf.ai_baseline,
    )

    pipeline_ctx = PipelineContext.resolve()
    rid = pipeline_ctx.record_audit("forensics analyze", optional=False, log=logger)
    assert rid is not None
    meta = {
        "run_id": rid,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "config_hash": pipeline_ctx.config_hash,
        "changepoint": do_changepoint,
        "timeseries": do_timeseries,
        "drift": do_drift,
        "convergence_full": do_full_analysis,
        "last_processed_author": request.author,
        "authors_in_run": ([request.author] if request.author else []),
        "preregistration_status": preregistration.status,
        "preregistration_message": preregistration.message,
        **request.analysis_mode.run_metadata_subset(),
    }
    write_run_metadata(analysis_dir, rid=rid, meta=meta)

    if do_changepoint:
        _run_changepoint_stage(ctx)
    if do_timeseries:
        _run_timeseries_stage(ctx)
    if do_drift:
        _run_analyze_stage_embedding_guarded(
            request,
            cmd="analyze.drift",
            runner=lambda: _run_drift_stage(ctx),
        )
    if do_full_analysis:
        _run_analyze_stage_embedding_guarded(
            request,
            cmd="analyze.full",
            runner=lambda: _run_full_analysis_stage(ctx),
        )
    if sf.ai_baseline:
        bp = request.baseline_params
        _run_ai_baseline_stage(
            ctx,
            skip_generation=bp.skip_generation,
            articles_per_cell=bp.articles_per_cell,
            baseline_model=bp.baseline_model,
            typer_context=request.typer_context,
        )
        _verify_requested_ai_baseline_vectors(ctx, typer_context=request.typer_context)
    logger.info(
        "analyze: completed (changepoint=%s, timeseries=%s, drift=%s, "
        "full_analysis=%s, ai_baseline=%s, author=%s)",
        do_changepoint,
        do_timeseries,
        do_drift,
        do_full_analysis,
        sf.ai_baseline,
        request.author or "all",
    )


def dispatch_analysis_stages(
    request: AnalyzeRequest,
    *,
    ctx: AnalyzeContext,
    analysis_dir: Path,
    preregistration: VerificationResult,
) -> None:
    sf = request.stage_flags
    if _compare_only_or_parallel_early_exit(request, ctx=ctx, sf=sf):
        return
    _run_serial_analyze_stages(
        request,
        ctx=ctx,
        analysis_dir=analysis_dir,
        preregistration=preregistration,
        sf=sf,
    )
