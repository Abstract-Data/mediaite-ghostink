"""Extract subcommand — feature extraction pipeline."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from forensics.config import get_project_root, get_settings

logger = logging.getLogger(__name__)


def extract(
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

    try:
        n = extract_all_features(
            db_path,
            settings,
            author_slug=author,
            skip_embeddings=skip_embeddings,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=1) from exc
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
            raise typer.Exit(code=1) from exc

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
