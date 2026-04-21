"""Pydantic-evals dataset and evaluators for baseline quality gating."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, IsInstance


class BaselineInput(BaseModel):
    topic_keywords: list[str]
    target_word_count: int
    prompt_template: str
    temperature: float


class BaselineOutput(BaseModel):
    headline: str
    text: str
    actual_word_count: int


class WordCountAccuracy(Evaluator[BaselineInput, BaselineOutput]):
    tolerance: float = 0.15

    def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
        target = ctx.inputs.target_word_count
        actual = ctx.output.actual_word_count
        if abs(actual - target) <= target * self.tolerance:
            return 1.0
        return 0.0


class TopicRelevance(Evaluator[BaselineInput, BaselineOutput]):
    def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
        text_lower = ctx.output.text.lower()
        hits = sum(1 for kw in ctx.inputs.topic_keywords if kw.lower() in text_lower)
        return min(1.0, hits / max(1, len(ctx.inputs.topic_keywords)))


class RepetitionDetector(Evaluator[BaselineInput, BaselineOutput]):
    max_repeated_ratio: float = 0.3

    def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
        sentences = ctx.output.text.split(". ")
        if len(sentences) < 3:
            return 1.0
        unique = len(set(sentences))
        ratio = 1.0 - (unique / len(sentences))
        return 0.0 if ratio > self.max_repeated_ratio else 1.0


class PerplexityRangeCheck(Evaluator[BaselineInput, BaselineOutput]):
    min_ppl: float = 10.0
    max_ppl: float = 120.0

    def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
        try:
            from forensics.features.probability import compute_perplexity, load_reference_model

            model, tokenizer = load_reference_model()
            dev = next(model.parameters()).device
            metrics = compute_perplexity(
                ctx.output.text,
                model,
                tokenizer,
                max_length=1024,
                stride=512,
                device=dev,
            )
            ppl = float(metrics["mean_perplexity"])
            if self.min_ppl <= ppl <= self.max_ppl:
                return 1.0
            return 0.0
        except Exception:
            return 1.0


baseline_eval_dataset: Dataset[BaselineInput, BaselineOutput, None] = Dataset(
    name="baseline_quality",
    cases=[
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
    ],
    evaluators=[
        IsInstance(type_name="BaselineOutput"),
        WordCountAccuracy(),
        TopicRelevance(),
        RepetitionDetector(),
        PerplexityRangeCheck(),
    ],
)
