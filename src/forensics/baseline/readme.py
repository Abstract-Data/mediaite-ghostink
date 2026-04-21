"""Auto-generated protocol documentation for ``data/ai_baseline/README.md``."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_baseline_readme(manifest: dict[str, Any], output_path: Path) -> None:
    """Write human-readable baseline protocol documentation (chain of custody)."""
    lines: list[str] = [
        "# AI baseline corpus — generation protocol",
        "",
        "This file is auto-generated. Do not edit by hand; re-run baseline generation.",
        "",
        "## Summary",
        "",
        f"- **Generated at:** {manifest.get('completed_at', 'unknown')}",
        f"- **Authors:** {', '.join(manifest.get('authors', []))}",
        f"- **Articles written:** {manifest.get('article_count', 0)}",
        "",
        "## Models (Ollama)",
        "",
    ]
    for m in manifest.get("models", []):
        lines.append(
            f"- `{m.get('name')}` — digest `{m.get('digest', 'n/a')}` — {m.get('notes', '')}"
        )
    lines += [
        "",
        "## Matrix",
        "",
        f"- **Temperatures:** {manifest.get('temperatures', [])}",
        f"- **Prompt templates:** {manifest.get('prompt_templates', [])}",
        f"- **Articles per cell:** {manifest.get('articles_per_cell', '')}",
        f"- **Max tokens:** {manifest.get('max_tokens', '')}",
        "",
        "## Topic stratification",
        "",
        (
            "Topics are sampled proportional to LDA mixture weights fit on each author's "
            "eligible corpus."
        ),
        "",
        "## Prompt templates (verbatim)",
        "",
        "### raw_generation",
        "```text",
        str(manifest.get("raw_template", "")).strip(),
        "```",
        "",
        "### style_mimicry",
        "```text",
        str(manifest.get("mimicry_template", "")).strip(),
        "```",
        "",
        "## Known limitations",
        "",
        "- Local Ollama weights may change if a model is re-pulled without pinning by digest.",
        "- Style mimicry uses aggregate statistics only (no verbatim author text).",
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
