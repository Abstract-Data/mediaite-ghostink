"""Phase 10 — AI baseline generation via local Ollama models (PydanticAI).

Heavy optional dependencies live in submodules (``agent``, ``orchestrator``,
``prompts``, …). Only lightweight helpers are re-exported here; import other
symbols from ``forensics.baseline.<module>`` directly.
"""

from __future__ import annotations

from forensics.baseline.utils import get_model_digest, sanitize_model_tag

__all__ = ["get_model_digest", "sanitize_model_tag"]
