"""PydanticAI agent for Ollama-backed baseline article generation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from forensics.baseline.generation import BaselineGenerationConfig, sanitize_model_name
from forensics.baseline.io import article_json_path, write_article_json
from forensics.baseline.models import BaselineDeps, GeneratedArticle
from forensics.baseline.ollama_client import get_model_digest
from forensics.baseline.prompts import build_prompt

logger = logging.getLogger(__name__)


def make_baseline_agent(
    model_name: str,
    ollama_base_url: str = "http://localhost:11434",
    *,
    max_retries: int = 2,
) -> Agent[BaselineDeps, GeneratedArticle]:
    """Create a PydanticAI agent wired to a specific Ollama model (OpenAI-compatible API)."""
    base = ollama_base_url.rstrip("/")
    ollama_model = OpenAIChatModel(
        model_name=model_name,
        provider=OllamaProvider(base_url=f"{base}/v1"),
    )

    agent: Agent[BaselineDeps, GeneratedArticle] = Agent(
        ollama_model,
        deps_type=BaselineDeps,
        output_type=GeneratedArticle,
        system_prompt=(
            "You are a professional journalist writing for a political news website. "
            "Write the article exactly as requested. Return structured output with "
            "headline, full article body in text, and actual_word_count equal to the "
            "number of words in text (whitespace-separated tokens)."
        ),
        retries=max_retries,
    )

    @agent.output_validator
    async def _enforce_length(
        ctx: RunContext[BaselineDeps],
        output: GeneratedArticle,
    ) -> GeneratedArticle:
        words = len(output.text.split())
        if words < 50:
            raise ModelRetry("Article body is shorter than 50 words; expand with reporting detail.")
        target = ctx.deps.target_word_count
        tolerance = max(1, int(target * 0.15))
        if abs(words - target) > tolerance:
            raise ModelRetry(
                f"Word count {words} is outside tolerance of {target} ± {tolerance}. "
                "Revise length while preserving meaning."
            )
        if output.actual_word_count != words:
            return GeneratedArticle(
                headline=output.headline,
                text=output.text,
                actual_word_count=words,
            )
        return output

    return agent


async def generate_baseline_article(
    agent: Agent[BaselineDeps, GeneratedArticle],
    deps: BaselineDeps,
    model_config: dict[str, Any],
    article_index: int,
    *,
    prompt: str,
    digest_map: dict[str, str],
    max_tokens: int,
    request_timeout: float,
) -> dict[str, Any]:
    """Generate one baseline article and return the full metadata record."""
    model_name = str(model_config["name"])
    start = datetime.now(UTC)
    ms = ModelSettings(
        temperature=deps.temperature,
        max_tokens=max_tokens,
        timeout=request_timeout,
    )
    result = await agent.run(prompt, deps=deps, model_settings=ms)
    elapsed_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
    usage = result.usage()

    return {
        "article_id": (
            f"baseline_{sanitize_model_name(model_name)}_{deps.prompt_template}_"
            f"t{deps.temperature}_{article_index:03d}"
        ),
        "model": model_name,
        "model_digest": get_model_digest(model_name, digest_map),
        "provider": "ollama",
        "temperature": deps.temperature,
        "max_tokens": max_tokens,
        "prompt_template": deps.prompt_template,
        "prompt_text": prompt,
        "topic_keywords": deps.topic_keywords,
        "target_word_count": deps.target_word_count,
        "actual_word_count": result.output.actual_word_count,
        "headline": result.output.headline,
        "text": result.output.text,
        "generated_at": start.isoformat(),
        "generation_time_ms": elapsed_ms,
        "eval_count": None,
        "eval_tokens_per_sec": None,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "requests": usage.requests,
        },
    }


async def run_generation_matrix(
    author_slug: str,
    config: BaselineGenerationConfig,
    *,
    topic_distribution: list[dict],
    style_context: dict[str, str],
    word_count_frame: Any,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Run models × temperatures × prompt templates × N articles per cell."""
    import numpy as np

    from forensics.baseline.ollama_client import fetch_model_digests
    from forensics.baseline.topics import sample_topic_keywords
    from forensics.baseline.word_sampling import sample_word_counts

    all_articles: list[dict[str, Any]] = []
    if dry_run:
        rng = np.random.default_rng(42)
        for model_cfg in config.models:
            for temperature in config.temperatures:
                for prompt_template in ("raw_generation", "style_mimicry"):
                    for i in range(config.articles_per_cell):
                        kws, angle = sample_topic_keywords(topic_distribution, rng)
                        wc = int(
                            sample_word_counts(word_count_frame, 1, seed=42 + i)[0],
                        )
                        all_articles.append(
                            {
                                "dry_run": True,
                                "author_slug": author_slug,
                                "model": model_cfg["name"],
                                "temperature": temperature,
                                "prompt_template": prompt_template,
                                "index": i + 1,
                                "topic_keywords": kws,
                                "target_word_count": wc,
                                "suggested_angle": angle,
                            },
                        )
        return all_articles

    digest_map = await fetch_model_digests(
        config.ollama_base_url,
        timeout=min(30.0, config.request_timeout),
    )
    rng = np.random.default_rng(42)

    import httpx

    async with httpx.AsyncClient(timeout=config.request_timeout) as client:
        for model_cfg in config.models:
            model_name = str(model_cfg["name"])
            agent = make_baseline_agent(model_name, config.ollama_base_url)
            logger.info("Generating with %s...", model_name)
            digest_map = await fetch_model_digests(
                config.ollama_base_url,
                timeout=min(30.0, config.request_timeout),
            )

            for temperature in config.temperatures:
                for prompt_template in ("raw_generation", "style_mimicry"):
                    for i in range(config.articles_per_cell):
                        kws, angle = sample_topic_keywords(topic_distribution, rng)
                        wclist = sample_word_counts(
                            word_count_frame,
                            1,
                            seed=42 + i + hash(prompt_template) % 10000,
                        )
                        target_wc = int(wclist[0])
                        deps = BaselineDeps(
                            author_slug=author_slug,
                            topic_keywords=kws,
                            target_word_count=target_wc,
                            prompt_template=prompt_template,
                            temperature=float(temperature),
                            output_dir=config.output_dir / author_slug,
                            http_client=client,
                        )
                        ctx = {**style_context, "suggested_angle": angle}
                        prompt = build_prompt(prompt_template, deps, style_context=ctx)
                        if config.log_generations:
                            logger.info(
                                "baseline gen author=%s model=%s temp=%s mode=%s i=%d",
                                author_slug,
                                model_name,
                                temperature,
                                prompt_template,
                                i + 1,
                            )
                        rec = await generate_baseline_article(
                            agent,
                            deps,
                            model_cfg,
                            i + 1,
                            prompt=prompt,
                            digest_map=digest_map,
                            max_tokens=config.max_tokens,
                            request_timeout=config.request_timeout,
                        )
                        path = article_json_path(
                            author_slug,
                            config.output_dir,
                            model_name,
                            prompt_template,
                            float(temperature),
                            i + 1,
                        )
                        write_article_json(path, rec)
                        all_articles.append(rec)
            logger.info("Completed %s: %d articles total so far", model_name, len(all_articles))

    return all_articles
