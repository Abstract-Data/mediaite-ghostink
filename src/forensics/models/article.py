"""Article entities."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Article(BaseModel):
    """Single article metadata and optional body text.

    The model is ``frozen=True`` (P1-ARCH-001): callers should construct a new
    ``Article`` via :meth:`with_updates` rather than mutating fields in place.
    This rules out a whole class of concurrent-write bugs in the scraper.

    ``metadata`` is defensively deep-copied on both construction and
    :meth:`with_updates` so that Pydantic's shallow ``frozen=True`` does not
    leak a shared ``dict`` reference between instances.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    author_id: str
    url: HttpUrl
    title: str
    published_date: datetime
    raw_html_path: str = ""
    clean_text: str = ""
    word_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""
    modified_date: datetime | None = None
    modifier_user_id: int | None = None
    scraped_at: datetime | None = None
    is_duplicate: bool = False

    @field_validator("metadata", mode="before")
    @classmethod
    def _copy_metadata(cls, value: Any) -> Any:
        """Deep-copy ``metadata`` at construction to break caller-held references."""
        if isinstance(value, dict):
            return copy.deepcopy(value)
        return value

    def with_updates(self, **changes: Any) -> Article:
        """Return a copy of this article with the provided fields replaced.

        ``metadata`` is deep-copied when either the current instance's dict or
        a replacement dict would otherwise be shared with the returned copy.
        """
        if "metadata" not in changes:
            changes["metadata"] = copy.deepcopy(self.metadata)
        return self.model_copy(update=changes)
