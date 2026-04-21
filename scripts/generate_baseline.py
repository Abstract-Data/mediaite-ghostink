#!/usr/bin/env python3
"""Generate topic-stratified AI baseline corpus via local Ollama (Phase 10)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime

from forensics.baseline.agent import run_generation_matrix
from forensics.baseline.features import extract_baseline_features
from forensics.baseline.generation import BASELINE_MODELS, BaselineGenerationConfig
from forensics.baseline.readme import generate_baseline_readme
from forensics.baseline.style_context import author_style_context
from forensics.baseline.topics import get_topic_distribution
from forensics.config import get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.storage.repository import Repository, init_db

logger = logging.getLogger("generate_baseline")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate AI baseline corpus (Ollama + PydanticAI)")
    p.add_argument("--author", metavar="SLUG", help="Single configured author slug")
    p.add_argument("--all", action="store_true", help="Run for every configured author")
    p.add_argument("--articles-per-cell", type=int, default=None, help="Override matrix depth")
    p.add_argument("--dry-run", action="store_true", help="Plan matrix without calling Ollama")
    p.add_argument("--model", metavar="NAME", help="Restrict to one Ollama model tag")
    p.add_argument("--preflight", action="store_true", help="Check Ollama and exit")
    p.add_argument(
        "--extract-features",
        action="store_true",
        help="After generation, run baseline feature extraction to data/ai_baseline/features/",
    )
    return p.parse_args()


def _resolve_models(settings: ForensicsSettings, single: str | None) -> list[dict]:
    names = [single] if single else list(settings.baseline.models)
    return [m for m in BASELINE_MODELS if m["name"] in names] or [
        {"name": n, "provider": "ollama", "family": "", "size_gb": 0, "notes": ""} for n in names
    ]


async def _async_main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    root = get_project_root()
    settings = get_settings()
    db_path = settings.db_path
    init_db(db_path)

    from forensics.baseline.ollama_client import preflight_check

    models_use = _resolve_models(settings, args.model)
    model_names = [str(m["name"]) for m in models_use]

    if args.preflight:
        ok = await preflight_check(
            model_names,
            ollama_base_url=settings.baseline.ollama_base_url,
        )
        return 0 if ok else 1

    if not args.author and not args.all:
        logger.error("Specify --author SLUG or --all")
        return 1

    authors = [a.slug for a in settings.authors] if args.all else [args.author or ""]
    if not authors or (not args.all and not authors[0]):
        logger.error("No author selected")
        return 1

    out_root = root / "data" / "ai_baseline"
    out_root.mkdir(parents=True, exist_ok=True)

    apc = args.articles_per_cell or settings.baseline.articles_per_cell
    cfg_base = BaselineGenerationConfig(
        ollama_base_url=settings.baseline.ollama_base_url,
        models=models_use,
        temperatures=list(settings.baseline.temperatures),
        articles_per_cell=int(apc),
        max_tokens=int(settings.baseline.max_tokens),
        request_timeout=float(settings.baseline.request_timeout),
        output_dir=out_root,
        log_generations=settings.chain_of_custody.log_all_generations,
    )

    if not args.dry_run:
        if not await preflight_check(
            model_names,
            ollama_base_url=settings.baseline.ollama_base_url,
        ):
            return 1

    all_manifest_articles: list[dict] = []
    started = datetime.now(UTC).isoformat()

    repo = Repository(db_path)
    for slug in authors:
        author = repo.get_author_by_slug(slug)
        if author is None:
            logger.error("Unknown author slug: %s", slug)
            return 1
        topic_distribution = get_topic_distribution(slug, db_path)
        arts = repo.list_articles_for_extraction(author_id=author.id)
        import polars as pl

        wc_frame = pl.DataFrame({"word_count": [a.word_count for a in arts]})
        style = author_style_context(slug, db_path)
        articles = await run_generation_matrix(
            slug,
            cfg_base,
            topic_distribution=topic_distribution,
            style_context=style,
            word_count_frame=wc_frame,
            dry_run=bool(args.dry_run),
        )
        all_manifest_articles.extend(articles)

    completed = datetime.now(UTC).isoformat()
    from forensics.baseline.prompts import read_baseline_templates_for_manifest

    raw_t, mimic_t = read_baseline_templates_for_manifest()
    manifest = {
        "started_at": started,
        "completed_at": completed,
        "authors": authors,
        "models": [
            {"name": m["name"], "digest": "", "notes": m.get("notes", "")} for m in models_use
        ],
        "temperatures": list(settings.baseline.temperatures),
        "prompt_templates": ["raw_generation", "style_mimicry"],
        "articles_per_cell": int(apc),
        "max_tokens": int(settings.baseline.max_tokens),
        "article_count": len(all_manifest_articles),
        "dry_run": bool(args.dry_run),
        "raw_template": raw_t,
        "mimicry_template": mimic_t,
    }
    (out_root / "generation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    snap = {
        "baseline": settings.baseline.model_dump(),
        "chain_of_custody": settings.chain_of_custody.model_dump(),
    }
    (out_root / "config_snapshot.json").write_text(
        json.dumps(snap, indent=2, default=str),
        encoding="utf-8",
    )
    generate_baseline_readme(manifest, out_root / "README.md")

    if args.extract_features and not args.dry_run:
        extract_baseline_features(out_root, settings)
        logger.info("Wrote baseline feature parquet files under data/ai_baseline/features/")

    logger.info("Done. Articles (or dry-run rows): %d", len(all_manifest_articles))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
