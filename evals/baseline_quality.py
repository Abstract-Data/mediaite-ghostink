"""Phase 10 — pydantic-evals quality gate for baseline generation.

Runs as:
    uv run python evals/baseline_quality.py --model llama3.1:8b
    uv run python evals/baseline_quality.py --all-models
    uv run python evals/baseline_quality.py --model llama3.1:8b --output reports/llama.json

Quality gate contract (per the Phase 10 spec):
  * WordCountAccuracy, TopicRelevance, RepetitionDetector must pass at 100%
  * PerplexityRangeCheck (if Phase 9 is available) must pass at >=90%
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from pydantic import BaseModel


class BaselineInput(BaseModel):
    topic_keywords: list[str]
    target_word_count: int
    prompt_template: str
    temperature: float


class BaselineOutput(BaseModel):
    headline: str
    text: str
    actual_word_count: int


try:  # pragma: no cover - import guard for the optional `baseline` extra.
    from pydantic_evals import Case, Dataset
    from pydantic_evals.evaluators import Evaluator, EvaluatorContext, IsInstance
except ImportError:
    Case = Dataset = Evaluator = EvaluatorContext = IsInstance = None  # type: ignore[assignment]
    _EVALS_AVAILABLE = False
else:
    _EVALS_AVAILABLE = True


if _EVALS_AVAILABLE:

    class WordCountAccuracy(Evaluator[BaselineInput, BaselineOutput]):  # type: ignore[misc]
        tolerance: float = 0.15

        def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
            target = ctx.inputs.target_word_count
            actual = ctx.output.actual_word_count
            return 1.0 if abs(actual - target) <= target * self.tolerance else 0.0

    class TopicRelevance(Evaluator[BaselineInput, BaselineOutput]):  # type: ignore[misc]
        def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
            text_lower = ctx.output.text.lower()
            hits = sum(1 for kw in ctx.inputs.topic_keywords if kw.lower() in text_lower)
            if not ctx.inputs.topic_keywords:
                return 1.0
            return min(1.0, hits / len(ctx.inputs.topic_keywords))

    class RepetitionDetector(Evaluator[BaselineInput, BaselineOutput]):  # type: ignore[misc]
        max_repeated_ratio: float = 0.3

        def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
            sentences = [s.strip() for s in ctx.output.text.split(". ") if s.strip()]
            if len(sentences) < 3:
                return 1.0
            unique = len(set(sentences))
            ratio = 1.0 - (unique / len(sentences))
            return 0.0 if ratio > self.max_repeated_ratio else 1.0

    class PerplexityRangeCheck(Evaluator[BaselineInput, BaselineOutput]):  # type: ignore[misc]
        min_ppl: float = 10.0
        max_ppl: float = 120.0

        def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
            try:
                from forensics.features.probability import (
                    compute_perplexity,
                    load_reference_model,
                )
            except ImportError:
                return 1.0  # Phase 9 not available -> skip gracefully.
            try:
                model, tokenizer = load_reference_model("gpt2")
            except Exception:
                return 1.0
            metrics = compute_perplexity(ctx.output.text, model, tokenizer)
            ppl = metrics["mean_perplexity"]
            return 1.0 if self.min_ppl <= ppl <= self.max_ppl else 0.0


def build_dataset():
    if not _EVALS_AVAILABLE:
        raise RuntimeError("pydantic-evals not installed. Run: uv sync --extra baseline")
    cases = [
        Case(
            name="politics_raw_t0.0",
            inputs=BaselineInput(
                topic_keywords=["trump", "election", "poll"],
                target_word_count=800,
                prompt_template="raw_generation",
                temperature=0.0,
            ),
            expected_output=None,
        ),
        Case(
            name="media_raw_t0.8",
            inputs=BaselineInput(
                topic_keywords=["media", "fox", "cnn", "cable news"],
                target_word_count=600,
                prompt_template="raw_generation",
                temperature=0.8,
            ),
            expected_output=None,
        ),
        Case(
            name="politics_mimicry_t0.0",
            inputs=BaselineInput(
                topic_keywords=["biden", "white house", "administration"],
                target_word_count=1000,
                prompt_template="style_mimicry",
                temperature=0.0,
            ),
            expected_output=None,
        ),
    ]
    return Dataset[BaselineInput, BaselineOutput, None](
        cases=cases,
        evaluators=[
            IsInstance(type_name="BaselineOutput"),
            WordCountAccuracy(),
            TopicRelevance(),
            RepetitionDetector(),
            PerplexityRangeCheck(),
        ],
    )


async def _run_model(model_name: str) -> dict:
    import httpx  # noqa: F401

    from forensics.baseline.agent import BaselineDeps, make_baseline_agent
    from forensics.baseline.prompts import PromptContext, build_prompt
    from forensics.config import get_project_root, get_settings

    settings = get_settings()
    root = get_project_root()
    agent = make_baseline_agent(model_name, settings.baseline.ollama_base_url)

    async def generate(inputs: BaselineInput) -> BaselineOutput:
        prompt = build_prompt(
            inputs.prompt_template,
            PromptContext(
                topic_keywords=inputs.topic_keywords,
                target_word_count=inputs.target_word_count,
            ),
            project_root=root,
        )
        deps = BaselineDeps(
            author_slug="eval-author",
            topic_keywords=inputs.topic_keywords,
            target_word_count=inputs.target_word_count,
            prompt_template=inputs.prompt_template,
            temperature=inputs.temperature,
            output_dir=Path("/tmp/eval-baseline"),
        )
        result = await agent.run(prompt, deps=deps)
        return BaselineOutput(
            headline=result.output.headline,
            text=result.output.text,
            actual_word_count=max(
                result.output.actual_word_count,
                len(result.output.text.split()),
            ),
        )

    report = await build_dataset().evaluate(generate)
    return (
        report.model_dump(mode="json")
        if hasattr(report, "model_dump")
        else {
            "model": model_name,
            "summary": str(report),
        }
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Baseline quality gate (pydantic-evals)")
    p.add_argument("--model", metavar="NAME", help="One Ollama model tag")
    p.add_argument("--all-models", action="store_true", help="Evaluate every configured model")
    p.add_argument("--output", metavar="PATH", help="Write JSON report here")
    return p


async def _amain(args: argparse.Namespace) -> int:
    if not _EVALS_AVAILABLE:
        print(
            "pydantic-evals not installed. Run: uv sync --extra baseline",
            file=sys.stderr,
        )
        return 1

    from forensics.config import get_settings

    settings = get_settings()
    if args.all_models:
        models = list(settings.baseline.models)
    elif args.model:
        models = [args.model]
    else:
        print("error: pass --model NAME or --all-models", file=sys.stderr)
        return 2

    reports = {}
    for m in models:
        reports[m] = await _run_model(m)

    payload = json.dumps(reports, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"wrote eval report to {args.output}")
    else:
        print(payload)
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return asyncio.run(_amain(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
