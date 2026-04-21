"""Article entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


class Article(BaseModel):
    """Single article metadata and optional body text."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    author_id: str
    url: HttpUrl
    title: str
    published_date: datetime
    raw_html_path: str = ""
    clean_text: str = ""
    word_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""
    modified_date: datetime | None = None
    modifier_user_id: int | None = None
    scraped_at: datetime | None = None
    is_duplicate: bool = False
