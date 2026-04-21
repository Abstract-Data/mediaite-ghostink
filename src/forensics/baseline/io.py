"""Baseline corpus filesystem layout."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from forensics.baseline.generation import sanitize_model_name

logger = logging.getLogger(__name__)


def cell_dir_name(prompt_template: str, temperature: float) -> str:
    mode = "raw" if prompt_template == "raw_generation" else "mimicry"
    return f"{mode}_t{temperature}"


def article_json_path(
    author_slug: str,
    base: Path,
    model_name: str,
    prompt_template: str,
    temperature: float,
    index: int,
) -> Path:
    mdir = sanitize_model_name(model_name)
    cell = cell_dir_name(prompt_template, temperature)
    out = base / author_slug / mdir / cell
    out.mkdir(parents=True, exist_ok=True)
    return out / f"article_{index:03d}.json"


def write_article_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.debug("wrote baseline article %s", path)
