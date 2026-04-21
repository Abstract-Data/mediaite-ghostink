"""Load baseline prompt templates from ``prompts/baseline_templates/``."""

from __future__ import annotations

from pathlib import Path

from forensics.baseline.models import BaselineDeps
from forensics.config import get_project_root


def _templates_dir() -> Path:
    return get_project_root() / "prompts" / "baseline_templates"


def read_baseline_templates_for_manifest() -> tuple[str, str]:
    """Return raw + mimicry template bodies for documentation snapshots."""
    return _load_template("raw_generation.txt"), _load_template("style_mimicry.txt")


def _load_template(name: str) -> str:
    path = _templates_dir() / name
    if not path.is_file():
        msg = f"Missing baseline template: {path}"
        raise FileNotFoundError(msg)
    return path.read_text(encoding="utf-8")


def build_prompt(template_key: str, deps: BaselineDeps, *, style_context: dict[str, str]) -> str:
    """Fill ``raw_generation`` or ``style_mimicry`` template."""
    topic_kw = ", ".join(deps.topic_keywords)
    wc = deps.target_word_count
    if template_key == "raw_generation":
        text = _load_template("raw_generation.txt")
        return text.format(
            word_count=wc,
            topic_keywords=topic_kw,
            suggested_angle=style_context.get("suggested_angle", "current developments"),
        )
    if template_key == "style_mimicry":
        text = _load_template("style_mimicry.txt")
        return text.format(
            word_count=wc,
            topic_keywords=topic_kw,
            outlet_name=style_context.get("outlet_name", "political news"),
            topic_area=style_context.get("topic_area", "national politics and media"),
            author_avg_sentence_length=style_context.get("author_avg_sentence_length", "18"),
            author_tone_description=style_context.get(
                "author_tone_description",
                "analytical and direct",
            ),
            author_structure_notes=style_context.get(
                "author_structure_notes",
                "news-style lede, supporting context, closing takeaway",
            ),
        )
    msg = f"Unknown prompt template: {template_key!r}"
    raise ValueError(msg)
