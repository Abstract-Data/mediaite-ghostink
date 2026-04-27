"""PydanticAI agent wiring for Phase 10 baseline generation."""

from __future__ import annotations

import json
import logging
import re
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


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _coerce_article_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize Ollama/OpenAI-compat tool-call blobs into GeneratedArticle fields."""
    if "headline" in data and "text" in data:
        return data
    params = data.get("parameters")
    if isinstance(params, dict) and "headline" in params and "text" in params:
        return params
    arguments = data.get("arguments")
    if isinstance(arguments, str):
        try:
            inner = json.loads(arguments)
        except json.JSONDecodeError:
            inner = None
        if isinstance(inner, dict):
            return _coerce_article_dict(inner)
    if isinstance(arguments, dict):
        return _coerce_article_dict(arguments)
    msg = f"Unrecognized baseline JSON shape (keys={list(data)!r})"
    raise ValueError(msg)


def _article_from_json_string(body: str) -> GeneratedArticle:
    """Build an article when the model returns one JSON string instead of an object."""
    cleaned = body.strip().strip('"')
    lines = [ln for ln in cleaned.splitlines() if ln.strip()]
    if not lines:
        msg = "JSON string body was empty"
        raise ValueError(msg)
    headline = lines[0].strip()
    if len(headline) > 200:
        headline = f"{headline[:197]}..."
    return GeneratedArticle(headline=headline, text=cleaned, actual_word_count=0)


def _article_from_loose_plaintext(blob: str) -> GeneratedArticle:
    """Last resort when the model ignores JSON and returns a plain article."""
    stripped = blob.strip().strip('"')
    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    if not lines:
        msg = "Plaintext article body was empty"
        raise ValueError(msg)
    headline = lines[0].strip()[:200]
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else stripped
    if not body:
        body = stripped
    return GeneratedArticle(headline=headline, text=body, actual_word_count=0)


def _first_dict_in_blob(blob: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(blob):
        if ch != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(blob, idx)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_generated_article_text(raw: str) -> GeneratedArticle:
    """Parse model plain-text output into :class:`GeneratedArticle`.

    Tolerates markdown fences, leading prose, tool-style wrappers, and trailing
    non-JSON text produced by some Ollama models.
    """
    text = _strip_json_fences(raw)
    blob = text.strip()
    if not blob:
        msg = "Model returned empty output"
        raise ValueError(msg)
    try:
        top_level = json.loads(blob)
    except json.JSONDecodeError:
        top_level = None
    else:
        if isinstance(top_level, str):
            return _article_from_json_string(top_level).with_auto_word_count()
        if isinstance(top_level, dict):
            coerced = _coerce_article_dict(top_level)
            return GeneratedArticle.model_validate(coerced)

    data = _first_dict_in_blob(blob)
    if data is None:
        try:
            return _article_from_loose_plaintext(blob).with_auto_word_count()
        except ValueError as exc:
            preview = blob[:240].replace("\n", "\\n")
            msg = f"Model output was not valid JSON (preview={preview!r})"
            raise ValueError(msg) from exc
    coerced = _coerce_article_dict(data)
    return GeneratedArticle.model_validate(coerced)


def make_baseline_agent(model_name: str, ollama_base_url: str) -> Any:
    """Instantiate a PydanticAI Agent bound to a specific Ollama model.

    Import is lazy so the `baseline` optional-extra stays optional.

    Local Llama-class checkpoints often emit JSON shaped like OpenAI ``tool_calls``
    (``name`` + ``parameters``) instead of a bare object. We take **plain text** output
    from the model and parse it ourselves via :func:`parse_generated_article_text`.
    """
    try:
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.output import TextOutput
        from pydantic_ai.providers.openai import OpenAIProvider
    except ImportError as exc:  # pragma: no cover - CLI error path
        raise ImportError(
            "Baseline generation requires pydantic-ai. Install with: uv sync --extra baseline"
        ) from exc

    # Ollama's OpenAI-compatible /v1 endpoint requires a non-empty api_key string
    # but does not validate it — "ollama-local" is a placeholder, not a secret.
    ollama_model = OpenAIChatModel(
        model_name=model_name,
        provider=OpenAIProvider(
            base_url=f"{ollama_base_url.rstrip('/')}/v1",
            api_key="ollama-local",
        ),
        settings={
            "parallel_tool_calls": False,
        },
    )
    return Agent(
        ollama_model,
        deps_type=BaselineDeps,
        output_type=TextOutput(parse_generated_article_text),
        system_prompt=(
            "You are a professional journalist writing for a political news "
            "website. Write the article exactly as requested in the user message.\n\n"
            "Reply with ONLY a single JSON object (no markdown fences) containing "
            'exactly these keys: "headline" (string), "text" (string), '
            '"actual_word_count" (integer; use 0 to let the pipeline count words).'
        ),
        retries=4,
    )
