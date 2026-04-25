"""Full Phase 10 generation matrix: models × temperatures × modes × articles."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from forensics.baseline.agent import BaselineDeps, GeneratedArticle, make_baseline_agent
from forensics.baseline.prompts import PromptContext, build_prompt
from forensics.baseline.topics import cycle_keywords, sample_topic_keywords, sample_word_counts
from forensics.baseline.utils import (
    dump_manifest,
    get_model_digest,
    hash_prompt_text,
    sanitize_model_tag,
)
from forensics.config import get_project_root
from forensics.config.settings import ForensicsSettings
from forensics.features import embeddings as embed_mod
from forensics.storage.json_io import write_text_atomic
from forensics.storage.parquet import save_numpy_atomic

logger = logging.getLogger(__name__)

PROMPT_MODES = ("raw_generation", "style_mimicry")


def _cell_dir(
    base: Path,
    author_slug: str,
    model: str,
    mode: str,
    temperature: float,
) -> Path:
    return base / author_slug / sanitize_model_tag(model) / f"{mode.split('_')[0]}_t{temperature}"


def _embed_article(payload: dict, model_name: str, model_revision: str, emb_dir: Path) -> None:
    # Parent dir mkdir handled inside save_numpy_atomic (RF-DRY-004).
    vec = embed_mod.compute_embedding(payload.get("text", ""), model_name, model_revision)
    save_numpy_atomic(emb_dir / f"{payload['article_id']}.npy", vec)


def _article_record(
    *,
    article_id: str,
    model_name: str,
    model_digest: str,
    deps: BaselineDeps,
    output: GeneratedArticle,
    prompt_text: str,
    elapsed_ms: int,
    max_tokens: int,
) -> dict[str, Any]:
    return {
        "article_id": article_id,
        "model": model_name,
        "model_digest": model_digest,
        "provider": "ollama",
        "temperature": deps.temperature,
        "max_tokens": max_tokens,
        "prompt_template": deps.prompt_template,
        "prompt_text_hash": hash_prompt_text(prompt_text),
        "topic_keywords": deps.topic_keywords,
        "target_word_count": deps.target_word_count,
        "actual_word_count": output.actual_word_count,
        "headline": output.headline,
        "text": output.text,
        "generated_at": datetime.now(UTC).isoformat(),
        "generation_time_ms": elapsed_ms,
    }


async def run_generation_matrix(
    author_slug: str,
    settings: ForensicsSettings,
    *,
    db_path: Path,
    project_root: Path | None = None,
    articles_per_cell: int | None = None,
    model_filter: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate the full model × temperature × mode × n matrix for one author.

    Returns the generation manifest dict. Writes:
      * data/ai_baseline/{slug}/{model}/{mode}_{temp}/{article_id}.json
      * data/ai_baseline/{slug}/{model}/{mode}_{temp}/embeddings/{article_id}.npy
      * data/ai_baseline/{slug}/generation_manifest.json
    """
    cfg = settings.baseline
    n_per_cell = articles_per_cell or cfg.articles_per_cell
    root = project_root or get_project_root()
    # ``base`` + per-author + per-cell dirs are created lazily by write helpers
    # the first time they write into that path (RF-DRY-004).
    base = root / "data" / "ai_baseline"

    topics = sample_topic_keywords(db_path, author_slug)
    n_total = n_per_cell * 2  # two modes share the word-count pool
    word_counts_pool = sample_word_counts(db_path, author_slug, n_total)
    keyword_pool = cycle_keywords(topics, n_total)

    target_models = [m for m in cfg.models if (not model_filter or m == model_filter)]
    if not target_models:
        raise ValueError(f"No models matched filter {model_filter!r}; configured: {cfg.models}")

    manifest = {
        "author_slug": author_slug,
        "started_at": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
        "ollama_base_url": cfg.ollama_base_url,
        "articles_per_cell": n_per_cell,
        "models": [],
    }

    if dry_run:
        planned = []
        for model_name in target_models:
            for temperature in cfg.temperatures:
                for mode in PROMPT_MODES:
                    planned.append(
                        {
                            "model": model_name,
                            "temperature": temperature,
                            "mode": mode,
                            "cell_articles": n_per_cell,
                        }
                    )
        manifest["planned_cells"] = planned
        manifest_path = base / author_slug / "generation_manifest.json"
        write_text_atomic(manifest_path, dump_manifest(manifest))
        logger.info(
            "baseline: dry-run plan written to %s (%d cells)",
            manifest_path,
            len(planned),
        )
        return manifest

    for model_name in target_models:
        digest = get_model_digest(model_name, ollama_base_url=cfg.ollama_base_url)
        model_entry = {"name": model_name, "digest": digest, "cells": []}
        agent = make_baseline_agent(model_name, cfg.ollama_base_url)
        logger.info("baseline: generating with model=%s digest=%s", model_name, digest)

        for temperature in cfg.temperatures:
            for mode in PROMPT_MODES:
                cell_dir = _cell_dir(base, author_slug, model_name, mode, temperature)
                # cell_dir + emb_dir are created inside the write helpers on first use.
                emb_dir = cell_dir / "embeddings"
                articles: list[dict[str, Any]] = []

                for i in range(n_per_cell):
                    kw = keyword_pool[i % len(keyword_pool)]
                    word_count = word_counts_pool[i % len(word_counts_pool)]
                    deps = BaselineDeps(
                        author_slug=author_slug,
                        topic_keywords=kw,
                        target_word_count=word_count,
                        prompt_template=mode,
                        temperature=temperature,
                        output_dir=cell_dir,
                    )
                    prompt_text = build_prompt(
                        mode,
                        PromptContext(
                            topic_keywords=kw,
                            target_word_count=word_count,
                        ),
                        project_root=root,
                    )
                    start = datetime.now(UTC)
                    result = await agent.run(prompt_text, deps=deps)
                    elapsed_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
                    output = result.output.with_auto_word_count()
                    article_id = (
                        f"baseline_{sanitize_model_tag(model_name)}_{mode.split('_')[0]}"
                        f"_t{temperature}_{i + 1:03d}"
                    )
                    record = _article_record(
                        article_id=article_id,
                        model_name=model_name,
                        model_digest=digest,
                        deps=deps,
                        output=output,
                        prompt_text=prompt_text,
                        elapsed_ms=elapsed_ms,
                        max_tokens=cfg.max_tokens,
                    )
                    write_text_atomic(
                        cell_dir / f"{article_id}.json",
                        json.dumps(record, indent=2),
                    )
                    _embed_article(
                        record,
                        settings.analysis.embedding_model,
                        settings.analysis.embedding_model_revision,
                        emb_dir,
                    )
                    articles.append(record)

                logger.info(
                    "baseline: completed cell model=%s t=%s mode=%s n=%d",
                    model_name,
                    temperature,
                    mode,
                    len(articles),
                )
                model_entry["cells"].append(
                    {
                        "temperature": temperature,
                        "mode": mode,
                        "count": len(articles),
                    }
                )
        manifest["models"].append(model_entry)

    manifest["completed_at"] = datetime.now(UTC).isoformat()
    manifest_path = base / author_slug / "generation_manifest.json"
    write_text_atomic(manifest_path, dump_manifest(manifest))
    logger.info("baseline: wrote manifest %s", manifest_path)
    return manifest


def reembed_existing_baseline(
    author_slug: str,
    settings: ForensicsSettings,
    *,
    project_root: Path | None = None,
) -> int:
    """Re-run embeddings against existing JSON articles (``--skip-generation`` flow)."""
    root = project_root or get_project_root()
    base = root / "data" / "ai_baseline" / author_slug
    if not base.is_dir():
        raise ValueError(f"No existing baseline at {base}")
    model_name = settings.analysis.embedding_model
    model_revision = settings.analysis.embedding_model_revision
    n = 0
    for json_path in base.rglob("*.json"):
        if json_path.name == "generation_manifest.json":
            continue
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if "text" not in payload or "article_id" not in payload:
            continue
        emb_dir = json_path.parent / "embeddings"
        _embed_article(payload, model_name, model_revision, emb_dir)
        n += 1
    logger.info("baseline: re-embedded %d articles for %s", n, author_slug)
    return n
