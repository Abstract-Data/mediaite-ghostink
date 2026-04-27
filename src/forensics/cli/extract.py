"""Extract subcommand — feature extraction pipeline."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from forensics.cli._decorators import with_examples
from forensics.cli._errors import fail
from forensics.cli._exit import ExitCode
from forensics.cli.state import get_cli_state
from forensics.config import get_project_root, get_settings
from forensics.pipeline_context import PipelineContext

logger = logging.getLogger(__name__)


@with_examples("forensics extract --author colby-hall")
def extract(
    ctx: typer.Context,
    author: Annotated[
        str | None,
        typer.Option("--author", metavar="SLUG", help="Limit to one author slug"),
    ] = None,
    skip_embeddings: Annotated[
        bool,
        typer.Option("--skip-embeddings", help="Skip sentence-transformer embeddings"),
    ] = False,
    probability: Annotated[
        bool,
        typer.Option(
            "--probability",
            help="Extract probability features (perplexity, burstiness, Binoculars)",
        ),
    ] = False,
    no_binoculars: Annotated[
        bool,
        typer.Option("--no-binoculars", help="With --probability: skip Binoculars scoring"),
    ] = False,
    device: Annotated[
        str | None,
        typer.Option("--device", help="Compute device for --probability: cpu or cuda"),
    ] = None,
) -> None:
    """Run feature extraction pipeline."""
    from forensics.features.pipeline import extract_all_features

    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"
    PipelineContext.resolve().record_audit("forensics extract", optional=True, log=logger)

    show = get_cli_state(ctx).show_progress
    try:
        n = extract_all_features(
            db_path,
            settings,
            author_slug=author,
            skip_embeddings=skip_embeddings,
            show_rich_progress=show,
        )
    except ValueError as exc:
        raise fail(
            ctx,
            "extract",
            "extract_failed",
            str(exc),
            exit_code=ExitCode.GENERAL_ERROR,
        ) from exc
    logger.info("extract: processed %d article(s)", n)

    if probability:
        try:
            from forensics.features.probability_pipeline import (
                extract_probability_features,
            )
        except ImportError as exc:
            logger.warning(
                "Probability features unavailable (%s). Install with: uv sync --extra probability",
                exc,
            )
            raise fail(
                ctx,
                "extract",
                "probability_extra_missing",
                str(exc),
                exit_code=ExitCode.GENERAL_ERROR,
                suggestion="Install with: uv sync --extra probability",
            ) from exc

        count = extract_probability_features(
            db_path,
            settings,
            author_slug=author,
            include_binoculars=not no_binoculars,
            device=device,
        )
        logger.info(
            "extract: scored %d article(s) for probability features (binoculars=%s, device=%s)",
            count,
            not no_binoculars,
            device or "auto",
        )
