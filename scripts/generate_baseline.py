"""Phase 10 — AI baseline generation (PydanticAI agent over local Ollama).

Usage:
    uv run python scripts/generate_baseline.py --preflight
    uv run python scripts/generate_baseline.py --author <slug> --dry-run
    uv run python scripts/generate_baseline.py --author <slug> --articles-per-cell 5
    uv run python scripts/generate_baseline.py --all
    uv run python scripts/generate_baseline.py --author <slug> --model llama3.1:8b
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from forensics.baseline.orchestrator import run_generation_matrix
from forensics.baseline.preflight import preflight_check
from forensics.config import get_project_root, get_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 10 — generate AI baseline articles via local Ollama"
    )
    parser.add_argument(
        "--author",
        metavar="SLUG",
        help="Limit to one configured author slug",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run for every configured author",
    )
    parser.add_argument(
        "--model",
        metavar="NAME",
        help="Restrict to a single Ollama model tag (e.g. llama3.1:8b)",
    )
    parser.add_argument(
        "--articles-per-cell",
        type=int,
        metavar="N",
        help="Override the number of articles per (model, temp, mode) cell",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generation plan without calling Ollama",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Check Ollama reachability and model availability, then exit",
    )
    return parser


async def _amain(args: argparse.Namespace) -> int:
    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"

    if args.preflight:
        ok = await preflight_check(settings.baseline.models, settings.baseline.ollama_base_url)
        return 0 if ok else 1

    if not args.all and not args.author:
        print(
            "error: specify --author SLUG or --all",
            file=sys.stderr,
        )
        return 2

    slugs = [a.slug for a in settings.authors] if args.all else [args.author]

    for slug in slugs:
        await run_generation_matrix(
            slug,
            settings,
            db_path=db_path,
            project_root=root,
            articles_per_cell=args.articles_per_cell,
            model_filter=args.model,
            dry_run=args.dry_run,
        )
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parser().parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
