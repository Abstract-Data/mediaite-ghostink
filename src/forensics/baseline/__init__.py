"""Phase 10 — AI baseline generation via local Ollama models (PydanticAI).

Public surface:
    BaselineDeps, GeneratedArticle, make_baseline_agent   — agent.py
    build_prompt, load_template                             — prompts.py
    sanitize_model_tag, get_model_digest                    — utils.py
    preflight_check                                         — preflight.py
    run_generation_matrix, reembed_existing_baseline        — orchestrator.py
    extract_topic_distribution                              — topics.py
"""

from __future__ import annotations

from forensics.baseline.utils import get_model_digest, sanitize_model_tag

__all__ = ["get_model_digest", "sanitize_model_tag"]
