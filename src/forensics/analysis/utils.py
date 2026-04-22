"""Shared analysis entry-point helpers."""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from forensics.config.settings import ForensicsSettings
from forensics.models.author import Author
from forensics.storage.parquet import load_feature_frame_sorted
from forensics.storage.repository import Repository

logger = logging.getLogger(__name__)


def intervals_overlap(a0, a1, b0, b1) -> bool:
    """Return True if closed intervals ``[a0, a1]`` and ``[b0, b1]`` intersect."""
    return a0 <= b1 and b0 <= a1


def load_feature_frame_for_author(
    features_dir: Path,
    slug: str,
    author_id: str,
) -> pl.DataFrame | None:
    """Load sorted features for one author from ``{slug}.parquet`` if present."""
    path = features_dir / f"{slug}.parquet"
    if not path.is_file():
        return None
    dfc = load_feature_frame_sorted(path).filter(pl.col("author_id") == author_id)
    if dfc.is_empty():
        logger.warning(
            "No feature rows for author_id=%s in %s (slug=%s); loading full parquet "
            "as fallback — downstream code must filter by author_id.",
            author_id,
            path.name,
            slug,
        )
        dfc = load_feature_frame_sorted(path)
    return dfc


def resolve_author_rows(
    repo: Repository,
    settings: ForensicsSettings,
    *,
    author_slug: str | None,
) -> list[Author]:
    """Resolve configured authors to DB rows, optionally filtered by ``author_slug``."""
    if author_slug:
        au = repo.get_author_by_slug(author_slug)
        if au is None:
            msg = f"Unknown author slug: {author_slug}"
            raise ValueError(msg)
        return [au]
    rows: list[Author] = []
    for a in settings.authors:
        au = repo.get_author_by_slug(a.slug)
        if au is not None:
            rows.append(au)
    return rows
