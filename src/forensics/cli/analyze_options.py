"""Typer ``Annotated`` option aliases for ``forensics analyze`` (default callback)."""

from __future__ import annotations

from typing import Annotated

import typer

AnalyzeChangepointFlag = Annotated[
    bool,
    typer.Option("--changepoint", help="Run change-point detection (PELT/BOCPD)"),
]
AnalyzeTimeseriesFlag = Annotated[
    bool,
    typer.Option("--timeseries", help="Run rolling statistics + STL decomposition"),
]
AnalyzeDriftFlag = Annotated[
    bool,
    typer.Option("--drift", help="Run embedding drift analysis (Phase 6)"),
]
AnalyzeConvergenceFlag = Annotated[
    bool,
    typer.Option(
        "--convergence",
        help="Cross-validate pipelines and run hypothesis tests (Phase 7)",
    ),
]
AnalyzeCompareFlag = Annotated[
    bool,
    typer.Option("--compare", help="Control author comparison only (Phase 7)"),
]
AnalyzeAiBaselineFlag = Annotated[
    bool,
    typer.Option("--ai-baseline", help="Generate or refresh synthetic AI baseline articles"),
]
AnalyzeSkipGenerationFlag = Annotated[
    bool,
    typer.Option(
        "--skip-generation",
        help="With --ai-baseline: re-embed existing JSON articles only",
    ),
]
AnalyzeVerifyCorpusFlag = Annotated[
    bool,
    typer.Option(
        "--verify-corpus",
        help="Verify corpus hash against data/analysis/corpus_custody.json",
    ),
]
AnalyzeBaselineModelOption = Annotated[
    str | None,
    typer.Option(
        "--baseline-model",
        metavar="MODEL",
        help="With --ai-baseline: restrict to one configured Ollama model",
    ),
]
AnalyzeArticlesPerCellOption = Annotated[
    int | None,
    typer.Option(
        "--articles-per-cell",
        metavar="N",
        help="With --ai-baseline: override articles_per_cell (default from config)",
    ),
]
AnalyzeAuthorOption = Annotated[
    str | None,
    typer.Option("--author", metavar="SLUG", help="Limit to one author slug"),
]
AnalyzeExploratoryFlag = Annotated[
    bool,
    typer.Option(
        "--exploratory",
        help=(
            "Allow analysis without a matching pre-registration lock and record exploratory mode."
        ),
    ),
]
AnalyzeIncludeAdvertorialFlag = Annotated[
    bool,
    typer.Option(
        "--include-advertorial",
        help=(
            "Re-include advertorial / syndicated sections (sponsored, "
            "partner-content, crosspost) in feature extraction and survey "
            "qualification for this run; default OFF (Phase 15 J2)."
        ),
    ),
]
AnalyzeResidualizeSectionsFlag = Annotated[
    bool,
    typer.Option(
        "--residualize-sections",
        help=(
            "Toggle J5 section-residualized changepoints for this run "
            "(flips analysis.section_residualize_features). Default OFF "
            "matches the persisted config (Phase 15 J7)."
        ),
    ),
]
AnalyzeIncludeSharedBylinesFlag = Annotated[
    bool,
    typer.Option(
        "--include-shared-bylines",
        help=(
            "Re-enable analysis of shared-byline accounts (e.g. "
            "mediaite-staff, mediaite). Default OFF — matches the Phase "
            "15 D survey gate, which disqualifies group bylines because "
            "single-author stylometry on aggregate accounts is "
            "meaningless. Mirrors ``forensics survey "
            "--include-shared-bylines``."
        ),
    ),
]
AnalyzeMaxWorkersOption = Annotated[
    int | None,
    typer.Option(
        "--max-workers",
        metavar="N",
        help=(
            "Override analysis.max_workers for this run only. N=1 forces "
            "the legacy serial dispatch; N>1 fans the per-author loop out "
            "across a ProcessPoolExecutor (Phase 15 G1)."
        ),
    ),
]
AnalyzeParallelAuthorsFlag = Annotated[
    bool,
    typer.Option(
        "--parallel-authors",
        help=(
            "Refresh configured author analysis artifacts via isolated per-author "
            "directories, then promote validated outputs and rebuild shared artifacts once."
        ),
    ),
]
AnalyzeComparePairOption = Annotated[
    str | None,
    typer.Option(
        "--compare-pair",
        metavar="TARGET,CONTROL",
        help=(
            "Run a one-off target↔control comparison for the named slugs, "
            "bypassing the configured author roles. Example: "
            "'--compare-pair isaac-schorr,john-doe'."
        ),
    ),
]
AnalyzeAllowPrePhase16EmbeddingsFlag = Annotated[
    bool,
    typer.Option(
        "--allow-pre-phase16-embeddings",
        help=(
            "With --exploratory: load embedding batches whose manifest "
            "model_revision does not match analysis.embedding_model_revision, "
            "logging a WARNING instead of failing. Default OFF — confirmatory "
            "runs always require a matching revision."
        ),
    ),
]
