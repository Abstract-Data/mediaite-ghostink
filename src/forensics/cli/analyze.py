"""Analyze CLI: default callback plus nested commands (e.g. ``section-profile``)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from forensics.cli._decorators import examples_epilog, forensics_examples, with_examples
from forensics.cli._envelope import status
from forensics.cli._errors import fail
from forensics.cli._exit import ExitCode
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
    AnalyzeMaxWorkersOption,
    AnalyzeParallelAuthorsFlag,
    AnalyzeResidualizeSectionsFlag,
    AnalyzeSkipGenerationFlag,
    AnalyzeTimeseriesFlag,
    AnalyzeVerifyCorpusFlag,
)
from forensics.cli.state import get_cli_state
from forensics.config import DEFAULT_DB_RELATIVE, get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.paths import AnalysisArtifactPaths
from forensics.pipeline_context import PipelineContext
from forensics.preregistration import verify_preregistration
from forensics.storage.json_io import write_json_artifact
from forensics.storage.repository import Repository
from forensics.survey.shared_byline import is_shared_byline as _is_shared_byline_heuristic

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True, slots=True)
class AnalyzeContext:
    """Shared paths/settings/slug for analyze stage runners."""

    db_path: Path
    settings: ForensicsSettings
    paths: AnalysisArtifactPaths
    author_slug: str | None
    max_workers: int | None = None
    compare_pair: tuple[str, str] | None = None
    exploratory: bool = False
    allow_pre_phase16_embeddings: bool = False

    @classmethod
    def build(
        cls,
        db_path: Path,
        settings: ForensicsSettings,
        *,
        root: Path,
        author: str | None,
        max_workers: int | None = None,
        compare_pair: tuple[str, str] | None = None,
        exploratory: bool = False,
        allow_pre_phase16_embeddings: bool = False,
    ) -> AnalyzeContext:
        return cls(
            db_path=db_path,
            settings=settings,
            paths=AnalysisArtifactPaths.from_project(root, db_path),
            author_slug=author,
            max_workers=max_workers,
            compare_pair=compare_pair,
            exploratory=exploratory,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
        )

    @property
    def root(self) -> Path:
        return self.paths.project_root


@dataclass(frozen=True, slots=True)
class AnalyzeRequest:
    """Parameters for :func:`run_analyze` (CLI default callback and programmatic callers)."""

    changepoint: bool = False
    timeseries: bool = False
    drift: bool = False
    convergence: bool = False
    compare: bool = False
    ai_baseline: bool = False
    skip_generation: bool = False
    verify_corpus: bool = False
    baseline_model: str | None = None
    articles_per_cell: int | None = None
    author: str | None = None
    exploratory: bool = False
    include_advertorial: bool = False
    residualize_sections: bool = False
    include_shared_bylines: bool = False
    max_workers: int | None = None
    compare_pair: tuple[str, str] | None = None
    parallel_authors: bool = False
    allow_pre_phase16_embeddings: bool = False
    typer_context: typer.Context | None = None


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


def _write_run_metadata(
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
    _write_run_metadata(analysis_dir, rid=rid, meta=meta)
    run_compare_only(
        ctx.settings,
        paths=ctx.paths,
        author_slug=ctx.author_slug,
        compare_pair=ctx.compare_pair,
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
        exploratory=ctx.exploratory,
        allow_pre_phase16_embeddings=ctx.allow_pre_phase16_embeddings,
    )


def _run_full_analysis_stage(ctx: AnalyzeContext) -> None:
    from forensics.analysis.orchestrator import run_full_analysis

    run_full_analysis(
        ctx.paths,
        ctx.settings,
        author_slug=ctx.author_slug,
        max_workers=ctx.max_workers,
        compare_pair=ctx.compare_pair,
        exploratory=ctx.exploratory,
        allow_pre_phase16_embeddings=ctx.allow_pre_phase16_embeddings,
    )


def _run_parallel_author_refresh_stage(ctx: AnalyzeContext) -> None:
    from forensics.analysis.orchestrator import run_parallel_author_refresh

    results = run_parallel_author_refresh(
        ctx.paths,
        ctx.settings,
        author_slug=ctx.author_slug,
        max_workers=ctx.max_workers,
        exploratory=ctx.exploratory,
        allow_pre_phase16_embeddings=ctx.allow_pre_phase16_embeddings,
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


def run_analyze(request: AnalyzeRequest) -> None:  # noqa: C901
    """Run analyze stages (callable from Typer and from ``forensics all``)."""
    changepoint = request.changepoint
    timeseries = request.timeseries
    drift = request.drift
    convergence = request.convergence
    compare = request.compare
    ai_baseline = request.ai_baseline
    skip_generation = request.skip_generation
    verify_corpus = request.verify_corpus
    baseline_model = request.baseline_model
    articles_per_cell = request.articles_per_cell
    author = request.author
    exploratory = request.exploratory
    include_advertorial = request.include_advertorial
    residualize_sections = request.residualize_sections
    include_shared_bylines = request.include_shared_bylines
    max_workers = request.max_workers
    compare_pair = request.compare_pair
    parallel_authors = request.parallel_authors
    allow_pre_phase16_embeddings = request.allow_pre_phase16_embeddings
    typer_context = request.typer_context

    settings = _apply_per_run_overrides(
        get_settings(),
        include_advertorial=include_advertorial,
        residualize_sections=residualize_sections,
    )
    root = get_project_root()
    db_path = root / DEFAULT_DB_RELATIVE
    if author is not None:
        _enforce_shared_byline_gate(
            db_path,
            settings,
            author_slug=author,
            include_shared_bylines=include_shared_bylines,
        )
    ctx = AnalyzeContext.build(
        db_path,
        settings,
        root=root,
        author=author,
        max_workers=max_workers,
        compare_pair=compare_pair,
        exploratory=exploratory,
        allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
    )
    analysis_dir = ctx.paths.analysis_dir

    if verify_corpus:
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

    preregistration = verify_preregistration(settings)
    if preregistration.status != "ok" and not exploratory:
        meta = {
            "run_timestamp": datetime.now(UTC).isoformat(),
            "last_processed_author": author,
            "authors_in_run": ([author] if author else []),
            "preregistration_status": preregistration.status,
            "preregistration_message": preregistration.message,
            "exploratory": False,
            "allow_pre_phase16_embeddings": allow_pre_phase16_embeddings,
        }
        _write_run_metadata(analysis_dir, rid="preregistration-blocked", meta=meta)
        raise fail(
            typer_context,
            "analyze",
            "preregistration_not_locked",
            preregistration.message,
            exit_code=ExitCode.CONFLICT,
            suggestion=(
                "run: forensics --yes lock-preregistration (or pass --exploratory to bypass)"
            ),
        )

    if compare and not (
        parallel_authors or changepoint or timeseries or drift or ai_baseline or convergence
    ):
        _run_compare_only_flow(ctx)
        return

    if parallel_authors:
        _run_parallel_author_refresh_stage(ctx)
        return

    do_changepoint, do_timeseries, do_drift, do_full_analysis = _resolve_mode_flags(
        changepoint=changepoint,
        timeseries=timeseries,
        drift=drift,
        convergence=convergence,
        compare=compare,
        ai_baseline=ai_baseline,
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
        "last_processed_author": author,
        "authors_in_run": ([author] if author else []),
        "preregistration_status": preregistration.status,
        "preregistration_message": preregistration.message,
        "exploratory": exploratory,
        "allow_pre_phase16_embeddings": allow_pre_phase16_embeddings,
    }
    _write_run_metadata(analysis_dir, rid=rid, meta=meta)

    if do_changepoint:
        _run_changepoint_stage(ctx)
    if do_timeseries:
        _run_timeseries_stage(ctx)
    if do_drift:
        _run_drift_stage(ctx)
    if do_full_analysis:
        _run_full_analysis_stage(ctx)
    if ai_baseline:
        _run_ai_baseline_stage(
            ctx,
            skip_generation=skip_generation,
            articles_per_cell=articles_per_cell,
            baseline_model=baseline_model,
            typer_context=typer_context,
        )
        _verify_requested_ai_baseline_vectors(ctx, typer_context=typer_context)
    logger.info(
        "analyze: completed (changepoint=%s, timeseries=%s, drift=%s, "
        "full_analysis=%s, ai_baseline=%s, author=%s)",
        do_changepoint,
        do_timeseries,
        do_drift,
        do_full_analysis,
        ai_baseline,
        author or "all",
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
    verify_corpus: AnalyzeVerifyCorpusFlag = False,
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
    parsed_pair = _parse_compare_pair(compare_pair)
    run_analyze(
        AnalyzeRequest(
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
            exploratory=exploratory,
            include_advertorial=include_advertorial,
            residualize_sections=residualize_sections,
            include_shared_bylines=include_shared_bylines,
            max_workers=max_workers,
            compare_pair=parsed_pair,
            parallel_authors=parallel_authors,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
            typer_context=ctx,
        )
    )


_SP_EPILOG, _sp_ex = forensics_examples("forensics analyze section-profile")


@analyze_app.command(name="section-profile", epilog=_SP_EPILOG)
@_sp_ex
def section_profile_cmd(
    ctx: typer.Context,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            metavar="PATH",
            help=(
                "Override the human-readable report path. JSON/CSV side artifacts "
                "still land in data/analysis/."
            ),
        ),
    ] = None,
    features_dir: Annotated[
        Path | None,
        typer.Option(
            "--features-dir",
            metavar="PATH",
            help="Override the features parquet directory (default: data/features).",
        ),
    ] = None,
) -> None:
    """Phase 15 J3: newsroom-wide section descriptive report and J5 gate verdict."""
    from forensics.analysis.section_profile import GATE_OMNIBUS_ALPHA, run_section_profile

    settings = get_settings()
    root = get_project_root()
    db_path = root / DEFAULT_DB_RELATIVE
    paths = AnalysisArtifactPaths.from_project(root, db_path)
    feat_dir = features_dir if features_dir is not None else paths.features_dir
    analysis_dir = paths.analysis_dir

    result = run_section_profile(
        settings,
        features_dir=feat_dir,
        analysis_dir=analysis_dir,
        report_path=output,
    )
    fmt = get_cli_state(ctx).output_format
    status(f"section-profile: retained {len(result.sections)} sections", output_format=fmt)
    status(
        f"  significant families (p<{GATE_OMNIBUS_ALPHA}): "
        f"{len(result.significant_families)} "
        f"({', '.join(result.significant_families) or 'none'})",
        output_format=fmt,
    )
    status(
        f"  max off-diagonal cosine distance: {result.max_off_diagonal_distance:.4f}",
        output_format=fmt,
    )
    status(f"  J5 gate verdict: {result.gate_verdict}", output_format=fmt)
    if result.artifacts is not None:
        status(f"  report: {result.artifacts.report_md}", output_format=fmt)


_SC_EPILOG, _sc_ex = forensics_examples(
    "forensics analyze section-contrast --author colby-hall",
)


@analyze_app.command(name="section-contrast", epilog=_SC_EPILOG)
@_sc_ex
def section_contrast_cmd(
    ctx: typer.Context,
    author: Annotated[
        str | None,
        typer.Option(
            "--author",
            metavar="SLUG",
            help=(
                "Limit to one author slug. Default: every configured author "
                "with a feature parquet under data/features/."
            ),
        ),
    ] = None,
    features_dir: Annotated[
        Path | None,
        typer.Option(
            "--features-dir",
            metavar="PATH",
            help="Override the features parquet directory (default: data/features).",
        ),
    ] = None,
) -> None:
    """Phase 15 J6: per-author section-contrast tests (Welch + MW + per-family BH)."""
    from forensics.analysis.section_contrast import compute_and_write_section_contrast
    from forensics.paths import load_feature_frame_for_author, resolve_author_rows
    from forensics.storage.repository import Repository

    settings = get_settings()
    root = get_project_root()
    db_path = root / DEFAULT_DB_RELATIVE
    paths = AnalysisArtifactPaths.from_project(root, db_path)
    feat_dir = features_dir if features_dir is not None else paths.features_dir
    analysis_dir = paths.analysis_dir

    with Repository(db_path) as repo:
        author_rows = resolve_author_rows(repo, settings, author_slug=author)

    fmt = get_cli_state(ctx).output_format
    if not author_rows:
        status(
            "section-contrast: no authors resolved (check --author / config.toml)",
            output_format=fmt,
        )
        raise fail(
            ctx,
            "analyze.section_contrast",
            "no_authors",
            "No authors resolved (check --author / config.toml).",
            exit_code=ExitCode.USAGE_ERROR,
        )

    written = 0
    for author_row in author_rows:
        df = load_feature_frame_for_author(feat_dir, author_row.slug, author_row.id)
        if df is None or df.is_empty():
            status(
                f"section-contrast: skipped {author_row.slug} (no feature rows)",
                output_format=fmt,
            )
            continue
        result, path = compute_and_write_section_contrast(
            df,
            author_id=author_row.id,
            author_slug=author_row.slug,
            analysis_dir=analysis_dir,
            alpha=settings.analysis.hypothesis.significance_threshold,
            bh_method=settings.analysis.hypothesis.multiple_comparison_method,
        )
        written += 1
        if result.disposition == "insufficient_section_volume":
            status(
                f"section-contrast: {author_row.slug} → insufficient_section_volume → {path}",
                output_format=fmt,
            )
        else:
            status(
                f"section-contrast: {author_row.slug} → {len(result.pairs)} pair(s) → {path}",
                output_format=fmt,
            )
    status(f"section-contrast: wrote {written} artifact(s)", output_format=fmt)
