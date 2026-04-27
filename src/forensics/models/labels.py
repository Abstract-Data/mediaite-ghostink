"""Optional human labels for precision/recall audits (M-17)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ArticleLabel(BaseModel):
    """One row in ``data/labels/article_labels.jsonl`` (append-only).

    ``judgment`` is intentionally coarse — the pipeline does not require labels
    to run; when the JSONL is empty, reporting states that precision/recall
    are unknown.
    """

    article_id: str
    author_slug: str
    labeled_at: datetime
    judgment: Literal["human", "ai_assisted", "unclear", "excluded"]
    notes: str = ""  # free-text auditor rationale
