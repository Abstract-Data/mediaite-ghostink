"""CLI-layer entry points for Phase 10 AI baseline generation.

Previously lived in :mod:`forensics.analysis.drift` but violates the
``scrape -> extract -> analyze -> report`` stage boundary because it
drives ``baseline.orchestrator`` rather than performing drift analysis.
Relocated here so ``drift`` no longer needs a module-level ``asyncio``
import (see RF-DEAD-002).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from forensics.config.settings import ForensicsSettings


def run_ai_baseline_command(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    project_root: Path | None = None,
    author_slug: str | None = None,
    skip_generation: bool = False,
    articles_per_cell: int | None = None,
    model_filter: str | None = None,
    dry_run: bool = False,
) -> None:
    """Generate or re-embed AI baseline corpora via local Ollama models.

    Delegates to ``forensics.baseline.orchestrator``. The Phase 10 v0.3.0
    spec replaces the old OpenAI path with three locally-run Ollama models
    (Llama 3.1 8B, Mistral 7B, Gemma 2 9B) so baselines are reproducible
    by model digest with no external API keys required.
    """
    from forensics.baseline.orchestrator import (
        reembed_existing_baseline,
        run_generation_matrix,
    )

    slugs = [author_slug] if author_slug else [a.slug for a in settings.authors]

    if skip_generation:
        for slug in slugs:
            reembed_existing_baseline(slug, settings, project_root=project_root)
        return

    async def _run() -> None:
        for slug in slugs:
            await run_generation_matrix(
                slug,
                settings,
                db_path=db_path,
                project_root=project_root,
                articles_per_cell=articles_per_cell,
                model_filter=model_filter,
                dry_run=dry_run,
            )

    asyncio.run(_run())


__all__ = ["run_ai_baseline_command"]
