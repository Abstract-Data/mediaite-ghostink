"""Ollama connectivity and model digest pinning."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def preflight_check(
    models: list[str],
    *,
    ollama_base_url: str = "http://localhost:11434",
    timeout: float = 10.0,
) -> bool:
    """Verify Ollama is reachable and all required models are available."""
    base = ollama_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(f"{base}/api/tags")
            resp.raise_for_status()
        except httpx.ConnectError:
            logger.error("Ollama is not running. Start with: ollama serve")
            return False
        except httpx.HTTPError as exc:
            logger.error("Ollama HTTP error: %s", exc)
            return False

        data = resp.json()
        available = {str(m.get("name", "")) for m in data.get("models", []) if m.get("name")}
        missing = [m for m in models if m not in available]
        if missing:
            logger.error("Missing models: %s. Pull with: ollama pull <model>", missing)
            return False
        logger.info("Preflight OK: %d models available via Ollama", len(models))
        return True


async def fetch_model_digests(
    ollama_base_url: str = "http://localhost:11434",
    *,
    timeout: float = 10.0,
) -> dict[str, str]:
    """Map model name → digest string from ``/api/tags`` (may be empty if unknown)."""
    base = ollama_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{base}/api/tags")
        resp.raise_for_status()
        data = resp.json()
    out: dict[str, str] = {}
    for m in data.get("models", []) or []:
        name = str(m.get("name", ""))
        if not name:
            continue
        digest = m.get("digest")
        if digest:
            out[name] = str(digest)
        else:
            out[name] = ""
    return out


def get_model_digest(model_name: str, digest_map: dict[str, str]) -> str:
    """Return pinned digest or placeholder when Ollama omits it."""
    d = digest_map.get(model_name, "")
    if d:
        return d if d.startswith("sha256:") else f"sha256:{d}"
    return "sha256:unknown"
