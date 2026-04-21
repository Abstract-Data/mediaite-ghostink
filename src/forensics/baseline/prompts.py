"""Prompt template loader for the AI baseline pipeline (Phase 10)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forensics.config import get_project_root

_TEMPLATES_DIR_NAME = "baseline_templates"


@dataclass(frozen=True)
class PromptContext:
    topic_keywords: list[str]
    target_word_count: int
    outlet_name: str = "Mediaite"
    topic_area: str = "politics"
    author_avg_sentence_length: int = 18
    author_tone_description: str = "sharp, conversational, media-critical"
    author_structure_notes: str = (
        "short lede summarizing the event, 2-3 quoted reactions, a punchy closer"
    )
    suggested_angle: str = "focus on the news value and cite at least one source"


def _templates_dir(project_root: Path | None = None) -> Path:
    root = project_root or get_project_root()
    return root / "prompts" / _TEMPLATES_DIR_NAME


def load_template(name: str, *, project_root: Path | None = None) -> str:
    """Read a prompt template by short name (``raw_generation``, ``style_mimicry``)."""
    path = _templates_dir(project_root) / f"{name}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def list_templates(project_root: Path | None = None) -> list[str]:
    dir_ = _templates_dir(project_root)
    if not dir_.is_dir():
        return []
    return sorted(p.stem for p in dir_.glob("*.txt"))


def build_prompt(
    template_name: str,
    ctx: PromptContext,
    *,
    project_root: Path | None = None,
) -> str:
    """Render ``{placeholder}`` tokens against a PromptContext."""
    raw = load_template(template_name, project_root=project_root)
    joined = ", ".join(ctx.topic_keywords)
    return raw.format(
        topic_keywords=joined,
        word_count=ctx.target_word_count,
        outlet_name=ctx.outlet_name,
        topic_area=ctx.topic_area,
        author_avg_sentence_length=ctx.author_avg_sentence_length,
        author_tone_description=ctx.author_tone_description,
        author_structure_notes=ctx.author_structure_notes,
        suggested_angle=ctx.suggested_angle,
    )
