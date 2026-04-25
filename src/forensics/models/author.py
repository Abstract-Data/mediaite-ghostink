"""Author records for discovery and configured analysis."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AuthorManifest(BaseModel):
    """Row from WordPress REST discovery, stored in data/authors_manifest.jsonl."""

    wp_id: int
    name: str
    slug: str
    total_posts: int
    discovered_at: datetime


class Author(BaseModel):
    """Author configured for analysis runs.

    The model is ``frozen=True`` (P1-ARCH-001): callers should construct a new
    ``Author`` via :meth:`with_updates` rather than mutating fields in place.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    slug: str
    outlet: str
    role: Literal["target", "control"]
    baseline_start: date
    baseline_end: date
    archive_url: str
    # Phase 15 D — newsroom-shared accounts (e.g. ``mediaite-staff``,
    # ``mediaite``) populated heuristically at ingest by
    # :func:`forensics.survey.shared_byline.is_shared_byline`. Survey
    # qualification skips these unless ``--include-shared-bylines`` is set.
    is_shared_byline: bool = False

    def with_updates(self, **changes: Any) -> Author:
        """Return a copy of this author with the provided fields replaced."""
        return self.model_copy(update=changes)
