"""Ollama reachability + model availability checks."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def preflight_check(models: list[str], base_url: str) -> bool:
    """Return True iff Ollama is reachable and every required model is pulled."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
        except httpx.ConnectError:
            logger.error("Ollama is not running at %s. Start with: ollama serve", base_url)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error("Ollama preflight failed: %s", exc)
            return False

        payload = resp.json()

    available = {m.get("name") for m in payload.get("models", []) if m.get("name")}
    missing = [m for m in models if m not in available]
    if missing:
        logger.error(
            "Ollama is running but missing model(s): %s. Pull with `ollama pull <name>`.",
            missing,
        )
        return False

    logger.info("Preflight OK: %d model(s) available via Ollama", len(models))
    return True
