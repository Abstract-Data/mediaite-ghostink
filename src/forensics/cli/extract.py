"""Extract subcommand — feature extraction pipeline."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from forensics.config import get_project_root, get_settings

logger = logging.getLogger(__name__)


def run_extract(
    *,
    author: str | None,
    skip_embeddings: bool,
    skip_probability: bool,
    probability: bool,
    no_binoculars: bool,
    device: str | None,
) -> int:
    """Core extract stage; returns process exit code."""
    from forensics.features.pipeline import extract_all_features
    from forensics.features.probability_pipeline import extract_probability_features

    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"

    if probability:
        n = extract_probability_features(
            db_path,
            settings,
            author_slug=author,
            no_binoculars=no_binoculars,
            device_override=device,
            project_root=root,
        )
        logger.info("extract --probability: scored %d article(s)", n)
        return 0

    n = extract_all_features(
        db_path,
        settings,
        author_slug=author,
        skip_embeddings=skip_embeddings,
        skip_probability=skip_probability,
        probability_no_binoculars=no_binoculars,
        project_root=root,
    )
    logger.info("extract: processed %d article(s)", n)
    return 0


def extract(
    author: Annotated[
        str | None,
        typer.Option("--author", metavar="SLUG", help="Limit to one author slug"),
    ] = None,
    skip_embeddings: Annotated[
        bool,
        typer.Option("--skip-embeddings", help="Skip sentence-transformer embeddings"),
    ] = False,
    skip_probability: Annotated[
        bool,
        typer.Option("--skip-probability", help="Skip GPT-2 / probability after stylometrics"),
    ] = False,
    probability: Annotated[
        bool,
        typer.Option("--probability", help="Probability / perplexity scoring only"),
    ] = False,
    no_binoculars: Annotated[
        bool,
        typer.Option("--no-binoculars", help="With --probability: skip Falcon Binoculars"),
    ] = False,
    device: Annotated[
        str | None,
        typer.Option("--device", metavar="NAME", help="Torch device, e.g. cpu or cuda"),
    ] = None,
) -> None:
    """Run feature extraction pipeline."""
    try:
        rc = run_extract(
            author=author,
            skip_embeddings=skip_embeddings,
            skip_probability=skip_probability,
            probability=probability,
            no_binoculars=no_binoculars,
            device=device,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        raise typer.Exit(code=1) from exc
    raise typer.Exit(code=rc)
