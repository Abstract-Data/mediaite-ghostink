"""Shared analysis entry-point helpers."""

from __future__ import annotations

from forensics.config.settings import ForensicsSettings
from forensics.models.author import Author
from forensics.storage.repository import Repository


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
