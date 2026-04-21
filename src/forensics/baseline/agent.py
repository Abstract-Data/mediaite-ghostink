"""PydanticAI agent wiring for Phase 10 baseline generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


@dataclass
class BaselineDeps:
    """Typed dependencies injected into every agent run."""

    author_slug: str
    topic_keywords: list[str]
    target_word_count: int
    prompt_template: str
    temperature: float
    output_dir: Path


class GeneratedArticle(BaseModel):
    """Structured output contract. Fields match what we persist to disk."""

    headline: str = Field(description="Article headline")
    text: str = Field(description="Full article body text")
    actual_word_count: int = Field(
        default=0,
        description="Word count of generated text (auto-filled if zero)",
    )

    @field_validator("actual_word_count")
    @classmethod
    def _nonneg(cls, v: int) -> int:
        return max(0, v)

    def with_auto_word_count(self) -> GeneratedArticle:
        if self.actual_word_count and self.actual_word_count > 0:
            return self
        return self.model_copy(update={"actual_word_count": len(self.text.split())})


def make_baseline_agent(model_name: str, ollama_base_url: str) -> Any:
    """Instantiate a PydanticAI Agent bound to a specific Ollama model.

    Import is lazy so the `baseline` optional-extra stays optional.
    """
    try:
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
    except ImportError as exc:  # pragma: no cover - CLI error path
        raise ImportError(
            "Baseline generation requires pydantic-ai. Install with: uv sync --extra baseline"
        ) from exc

    ollama_model = OpenAIChatModel(
        model_name=model_name,
        provider=OpenAIProvider(
            base_url=f"{ollama_base_url.rstrip('/')}/v1",
            api_key="ollama-local",
        ),
    )
    return Agent(
        ollama_model,
        deps_type=BaselineDeps,
        output_type=GeneratedArticle,
        system_prompt=(
            "You are a professional journalist writing for a political news "
            "website. Write the article exactly as requested. Return a "
            "structured object with headline, text, and actual_word_count — "
            "no meta-commentary, no preamble."
        ),
        retries=2,
    )
