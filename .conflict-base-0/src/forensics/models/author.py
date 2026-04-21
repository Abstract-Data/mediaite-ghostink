"""Author records for discovery and configured analysis."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AuthorManifest(BaseModel):
    """Row from WordPress REST discovery, stored in data/authors_manifest.jsonl."""

    wp_id: int
    name: str
    slug: str
    total_posts: int
    discovered_at: datetime


class Author(BaseModel):
    """Author configured for analysis runs."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    slug: str
    outlet: str
    role: Literal["target", "control"]
    baseline_start: date
    baseline_end: date
    archive_url: str
