"""Shared datatypes for baseline generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, field_validator


@dataclass
class BaselineDeps:
    """Typed dependencies injected into every agent run."""

    author_slug: str
    topic_keywords: list[str]
    target_word_count: int
    prompt_template: str  # "raw_generation" or "style_mimicry"
    temperature: float
    output_dir: Path
    http_client: httpx.AsyncClient


class GeneratedArticle(BaseModel):
    """Structured output — the agent MUST return this shape or retry."""

    headline: str = Field(description="Article headline")
    text: str = Field(description="Full article body text")
    actual_word_count: int = Field(description="Word count of generated text")

    @field_validator("actual_word_count")
    @classmethod
    def word_count_reasonable(cls, v: int) -> int:
        if v < 50:
            msg = "Generated article is too short (< 50 words)"
            raise ValueError(msg)
        return v
