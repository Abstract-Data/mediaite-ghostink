#!/usr/bin/env python3
"""CLI entry for baseline quality evals (implementation in ``forensics.baseline.eval_quality``)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

import httpx
from pydantic_ai.models.test import TestModel

from forensics.baseline.agent import make_baseline_agent
from forensics.baseline.eval_quality import BaselineInput, BaselineOutput, baseline_eval_dataset
from forensics.baseline.models import BaselineDeps, GeneratedArticle
from forensics.baseline.prompts import build_prompt
from forensics.config import get_project_root, get_settings

logger = logging.getLogger("baseline_quality")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run baseline quality evals against Ollama")
    p.add_argument("--model", metavar="NAME", help="Single Ollama model tag")
    p.add_argument("--all-models", action="store_true", help="Run across default three models")
    p.add_argument("--output", type=Path, help="Write JSON report to this path")
    p.add_argument(
        "--use-test-model", action="store_true", help="Use PydanticAI TestModel (no Ollama)"
    )
    return p.parse_args()


async def generate_for_eval(
    inputs: BaselineInput,
    *,
    eval_model_name: str,
    ollama_base_url: str,
    use_test_model: bool,
) -> BaselineOutput:
    agent = make_baseline_agent(eval_model_name, ollama_base_url)

    async def _run_once() -> BaselineOutput:
        async with httpx.AsyncClient(timeout=120.0) as client:
            deps = BaselineDeps(
                author_slug="eval-author",
                topic_keywords=inputs.topic_keywords,
                target_word_count=inputs.target_word_count,
                prompt_template=inputs.prompt_template,
                temperature=inputs.temperature,
                output_dir=Path("/tmp/eval"),
                http_client=client,
            )
            style_ctx = {
                "suggested_angle": "developments in Washington",
                "outlet_name": "political news site",
                "topic_area": "national politics",
                "author_avg_sentence_length": "18",
                "author_tone_description": "analytical",
                "author_structure_notes": "lede, body, close",
            }
            prompt = build_prompt(inputs.prompt_template, deps, style_context=style_ctx)
            result = await agent.run(prompt, deps=deps)
            ga = result.output
            assert isinstance(ga, GeneratedArticle)
            return BaselineOutput(
                headline=ga.headline,
                text=ga.text,
                actual_word_count=ga.actual_word_count,
            )

    if use_test_model:
        with agent.override(model=TestModel()):
            return await _run_once()
    return await _run_once()


async def _async_main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    settings = get_settings()
    base = settings.baseline.ollama_base_url.rstrip("/")

    models = (
        [str(args.model)]
        if args.model
        else (list(settings.baseline.models) if args.all_models else [settings.baseline.models[0]])
    )

    reports: list[dict] = []
    for mname in models:
        m_local = str(mname)

        async def task(inp: BaselineInput, _m: str = m_local) -> BaselineOutput:
            return await generate_for_eval(
                inp,
                eval_model_name=_m,
                ollama_base_url=base,
                use_test_model=bool(args.use_test_model),
            )

        report = baseline_eval_dataset.evaluate_sync(task)
        reports.append({"model": mname, "summary": str(report)})
        report.print(include_input=True, include_output=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
        cust = get_project_root() / "data" / "ai_baseline" / "eval_reports"
        cust.mkdir(parents=True, exist_ok=True)
        alt = cust / args.output.name
        alt.write_text(json.dumps(reports, indent=2), encoding="utf-8")

    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
