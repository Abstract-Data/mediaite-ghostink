"""Baseline generation matrix configuration and model catalog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASELINE_MODELS: list[dict[str, Any]] = [
    {
        "name": "llama3.1:8b",
        "provider": "ollama",
        "family": "llama",
        "size_gb": 4.7,
        "notes": "Meta Llama 3.1 8B — strong general-purpose, most popular open model",
    },
    {
        "name": "mistral:7b",
        "provider": "ollama",
        "family": "mistral",
        "size_gb": 4.1,
        "notes": "Mistral 7B v0.3 — different training mix, strong writing quality",
    },
    {
        "name": "gemma2:9b",
        "provider": "ollama",
        "family": "gemma",
        "size_gb": 5.4,
        "notes": "Google Gemma 2 9B — distinct architecture (sliding window attention)",
    },
]


def sanitize_model_name(model_name: str) -> str:
    """Filesystem-safe model tag (Ollama colons → hyphens)."""
    return model_name.replace(":", "-").replace("/", "-")


@dataclass
class BaselineGenerationConfig:
    """Resolved generation matrix for one run."""

    ollama_base_url: str
    models: list[dict[str, Any]]
    temperatures: list[float]
    articles_per_cell: int
    max_tokens: int
    request_timeout: float
    output_dir: Path
    log_generations: bool = True
