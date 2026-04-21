"""Utility helpers for the baseline generation pipeline."""

from __future__ import annotations

import hashlib
import json
import logging

logger = logging.getLogger(__name__)


def sanitize_model_tag(name: str) -> str:
    """Filesystem-safe form of an Ollama model tag: llama3.1:8b -> llama3.1-8b."""
    return name.replace(":", "-").replace("/", "-")


def get_model_digest(model_name: str, *, ollama_base_url: str = "http://localhost:11434") -> str:
    """Fetch the SHA digest from the Ollama ``/api/tags`` endpoint.

    Returns ``"unknown"`` if the Ollama server is unreachable or the model isn't
    pulled — we still want to record the attempt in the generation manifest.
    """
    import httpx

    try:
        resp = httpx.get(f"{ollama_base_url}/api/tags", timeout=10.0)
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Ollama digest lookup failed for %s: %s", model_name, exc)
        return "unknown"
    for entry in payload.get("models", []):
        if entry.get("name") == model_name or entry.get("model") == model_name:
            digest = entry.get("digest")
            if digest:
                return str(digest)
    return "unknown"


def hash_prompt_text(text: str) -> str:
    """Short SHA-256 of a prompt template, for manifest identity."""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def dump_manifest(payload: dict) -> str:
    """JSON-serialize a manifest with stable key ordering."""
    return json.dumps(payload, indent=2, sort_keys=True, default=str)
