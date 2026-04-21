# Phase 10: AI Baseline Generation Protocol & Chain of Custody

Version: 0.3.0
Status: pending
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 4 (feature extraction — needed for LDA topic clusters), Phase 3 (scraped corpus)

## Objective

Implement a rigorous, documented, reproducible protocol for generating the AI baseline corpus used in embedding drift comparison (Phase 6) and probability feature calibration (Phase 9). Also formalize chain-of-custody measures for the entire corpus.

Without this protocol, the embedding drift analysis lacks a defensible reference point. If someone asks "how did you generate your AI reference corpus?" the answer must be specific, reproducible, and documented.

## 1. AI Baseline Generation Script (scripts/generate_baseline.py)

### Design Principles

- **Topic-stratified:** Generate AI articles on the SAME topic distributions as the target author's corpus (prevents topic confound).
- **Multi-model:** Use multiple LLMs to avoid biasing the baseline toward one model's style.
- **Multi-temperature:** Generate at both low and high temperature to bound the AI detection range.
- **Multi-prompting:** Test both raw generation and style-mimicry to cover realistic usage scenarios.
- **Fully documented:** Every generated article includes its generation metadata (model, temperature, prompt template, timestamp).

### LLM Selection

Use three architecturally diverse local models via Ollama. The goal is not to replicate the exact model a writer may have used, but to capture the *statistical signatures common to all autoregressive LLM output* — low perplexity, uniform burstiness, predictable token distributions. These properties emerge from the generation process itself, not any specific model, making local open-weight models valid baselines.

Model diversity matters more than model size. Three different architectures trained on different data give a robust AI baseline centroid:

```python
BASELINE_MODELS = [
    {
        "name": "llama3.1:8b",
        "provider": "ollama",
        "family": "llama",
        "size_gb": 4.7,
        "notes": "Meta Llama 3.1 8B — strong general-purpose, most popular open model",
    },
    {
        "name": "mistral:7b",
        "provider": "ollama",
        "family": "mistral",
        "size_gb": 4.1,
        "notes": "Mistral 7B v0.3 — different training mix, strong writing quality",
    },
    {
        "name": "gemma2:9b",
        "provider": "ollama",
        "family": "gemma",
        "size_gb": 5.4,
        "notes": "Google Gemma 2 9B — distinct architecture (sliding window attention)",
    },
]
```

**Hardware requirement:** M1 Mac with 32GB unified memory comfortably runs any single 7-9B model with ~5GB VRAM usage, leaving ample room for the rest of the pipeline. Models are loaded one at a time during generation.

**Ollama setup prerequisite:**

```bash
# Install Ollama (if not already installed)
brew install ollama

# Pull required models (~14GB total download)
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull gemma2:9b

# Verify
ollama list
```

### PydanticAI Agent Architecture (src/forensics/baseline/agent.py)

The baseline generation is implemented as a PydanticAI agent. This gives us typed dependencies and results, automatic output validation against Pydantic models, `ModelRetry` for self-correcting generation (word count misses, off-topic output), and the `pydantic-evals` framework for quality gating.

#### Dependencies

```python
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class BaselineDeps:
    """Typed dependencies injected into every agent run."""

    author_slug: str
    topic_keywords: list[str]
    target_word_count: int
    prompt_template: str  # "raw_generation" or "style_mimicry"
    temperature: float
    output_dir: Path
    http_client: httpx.AsyncClient  # shared client for Ollama health checks
```

#### Result Type

```python
from pydantic import BaseModel, Field, field_validator


class GeneratedArticle(BaseModel):
    """Structured output — the agent MUST return this shape or retry."""

    headline: str = Field(description="Article headline")
    text: str = Field(description="Full article body text")
    actual_word_count: int = Field(description="Word count of generated text")

    @field_validator("actual_word_count")
    @classmethod
    def word_count_reasonable(cls, v: int) -> int:
        if v < 50:
            raise ValueError("Generated article is too short (< 50 words)")
        return v
```

#### Agent Definition

```python
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider


def make_baseline_agent(model_name: str, ollama_base_url: str = "http://localhost:11434") -> Agent:
    """Create a PydanticAI agent wired to a specific Ollama model.

    One agent instance per model in the generation matrix.
    """
    ollama_model = OpenAIChatModel(
        model_name=model_name,
        provider=OllamaProvider(base_url=f"{ollama_base_url}/v1"),
    )

    agent = Agent(
        ollama_model,
        deps_type=BaselineDeps,
        output_type=GeneratedArticle,
        system_prompt=(
            "You are a professional journalist writing for a political news website. "
            "Write the article exactly as requested. Return ONLY the article — "
            "no meta-commentary, no preamble."
        ),
        retries=2,  # allow 2 retries on validation failure
    )

    @agent.tool
    async def check_word_count(ctx: RunContext[BaselineDeps], text: str) -> str:
        """Check if generated text meets the target word count."""
        count = len(text.split())
        target = ctx.deps.target_word_count
        tolerance = int(target * 0.15)  # 15% tolerance
        if abs(count - target) > tolerance:
            raise ModelRetry(
                f"Word count {count} is outside tolerance of {target} ± {tolerance}. "
                f"Adjust the article length."
            )
        return f"Word count {count} is within tolerance of target {target}."

    return agent
```

#### Generation Orchestrator

```python
from datetime import datetime, timezone

async def generate_baseline_article(
    agent: Agent,
    deps: BaselineDeps,
    model_config: dict,
    article_index: int,
) -> dict:
    """Generate one baseline article and return the full metadata record."""

    # Build the prompt from template
    prompt = build_prompt(deps.prompt_template, deps)

    start = datetime.now(timezone.utc)
    result = await agent.run(prompt, deps=deps)
    elapsed_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

    return {
        "article_id": f"baseline_{sanitize_model_name(model_config['name'])}_{deps.prompt_template}_t{deps.temperature}_{article_index:03d}",
        "model": model_config["name"],
        "model_digest": get_model_digest(model_config["name"]),
        "provider": "ollama",
        "temperature": deps.temperature,
        "max_tokens": 1500,
        "prompt_template": deps.prompt_template,
        "prompt_text": prompt,
        "topic_keywords": deps.topic_keywords,
        "target_word_count": deps.target_word_count,
        "actual_word_count": result.output.actual_word_count,
        "headline": result.output.headline,
        "text": result.output.text,
        "generated_at": start.isoformat(),
        "generation_time_ms": elapsed_ms,
        "usage": {
            "input_tokens": result.usage().input_tokens,
            "output_tokens": result.usage().output_tokens,
            "requests": result.usage().requests,
        },
    }
```

#### Model Rotation Strategy

```python
async def run_generation_matrix(
    author_slug: str,
    config: BaselineConfig,
) -> list[dict]:
    """Run the full generation matrix: models × temps × modes × articles.

    Process all articles for one model before switching to the next
    to minimize Ollama model reloads (~10-15s per cold load).
    """
    all_articles = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        for model_config in config.models:
            agent = make_baseline_agent(model_config["name"], config.ollama_base_url)
            logger.info(f"Generating with {model_config['name']}...")

            for temperature in config.temperatures:
                for prompt_template in ["raw_generation", "style_mimicry"]:
                    for i in range(config.articles_per_cell):
                        deps = BaselineDeps(
                            author_slug=author_slug,
                            topic_keywords=sample_topic(author_slug),
                            target_word_count=sample_word_count(author_slug),
                            prompt_template=prompt_template,
                            temperature=temperature,
                            output_dir=config.output_dir / author_slug,
                            http_client=client,
                        )
                        article = await generate_baseline_article(
                            agent, deps, model_config, i + 1
                        )
                        all_articles.append(article)

            logger.info(f"Completed {model_config['name']}: {len(all_articles)} total")

    return all_articles
```

**Timeout handling:** Ollama on M1 generates ~30-50 tokens/sec for 7-9B models. A 1500-token article takes ~30-50 seconds. The 120s timeout provides margin for cold model loads.

**Model loading:** Ollama keeps the most recently used model in memory. When switching between models, expect a ~10-15 second cold load. The generation script processes all articles for one model before switching to the next to minimize reloads.

### Topic Stratification

Use the LDA topic clusters from Phase 4's `content.py` to stratify generation:

```python
def get_topic_distribution(author_slug: str, features_dir: Path) -> list[dict]:
    """Extract LDA topic clusters and representative keywords for an author.

    Returns:
        [
            {"topic_id": 0, "keywords": ["trump", "election", "poll"], "weight": 0.35},
            {"topic_id": 1, "keywords": ["media", "fox", "cnn"], "weight": 0.25},
            ...
        ]
    """
```

Generate baseline articles proportional to the author's topic distribution. If the author writes 35% politics, 25% media criticism, etc., the baseline should match.

### Generation Matrix

For each target author, generate articles across this matrix:

| Dimension | Values |
|-----------|--------|
| Model | Llama 3.1 8B, Mistral 7B, Gemma 2 9B (via Ollama) |
| Temperature | 0.0 (most AI-like), 0.8 (more human-like) |
| Prompting mode | Raw generation, Style mimicry |
| Topics | Proportional to author's LDA distribution |

Target: 30 articles per cell = 30 × 3 models × 2 temps × 2 modes = **360 baseline articles per author**.

### Prompt Templates

Store in `prompts/baseline_templates/`:

**Raw generation (`raw_generation.txt`):**
```
Write a {word_count}-word news article about the following topic for a political news website.

Topic: {topic_keywords}
Angle: {suggested_angle}

Write in a professional journalistic style. Include quotes from relevant sources where appropriate.
```

**Style mimicry (`style_mimicry.txt`):**
```
Write a {word_count}-word article in the style of a {outlet_name} columnist who typically covers {topic_area}. The article should discuss {topic_keywords}.

Style characteristics to emulate:
- Average sentence length: {author_avg_sentence_length} words
- Tone: {author_tone_description}
- Typical article structure: {author_structure_notes}

Do not include the author's name or any identifying information.
```

The style mimicry prompt uses aggregate statistics from the author's baseline period features (pre-2020) — never the author's actual text. This tests the upper bound of what mimicry can achieve without direct text copying.

### Word count matching

Sample target word counts from the actual distribution of the author's articles:

```python
def sample_word_counts(author_articles: pl.DataFrame, n: int) -> list[int]:
    """Sample word counts from the author's article length distribution."""
    return (
        author_articles
        .select("word_count")
        .sample(n=n, with_replacement=True, seed=42)
        .to_series()
        .to_list()
    )
```

### Generation script CLI

```bash
# Generate baseline for a specific author
uv run python scripts/generate_baseline.py --author colby-hall --articles-per-cell 30

# Generate for all configured authors
uv run python scripts/generate_baseline.py --all

# Dry run (show what would be generated, no Ollama calls)
uv run python scripts/generate_baseline.py --author colby-hall --dry-run

# Generate only with specific model
uv run python scripts/generate_baseline.py --author colby-hall --model llama3.1:8b

# Check Ollama connectivity and model availability before generation
uv run python scripts/generate_baseline.py --preflight
```

### Preflight check

Before generation, verify Ollama is running and all models are pulled:

```python
async def preflight_check(models: list[str]) -> bool:
    """Verify Ollama is reachable and all required models are available."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Check Ollama is running
        try:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
        except httpx.ConnectError:
            logger.error("Ollama is not running. Start with: ollama serve")
            return False

        available = {m["name"] for m in resp.json().get("models", [])}
        missing = [m for m in models if m not in available]
        if missing:
            logger.error(f"Missing models: {missing}. Pull with: ollama pull <model>")
            return False

        logger.info(f"Preflight OK: {len(models)} models available via Ollama")
        return True
```

## 2. Baseline Storage (data/ai_baseline/)

### Directory structure

```
data/ai_baseline/
├── README.md                           # Protocol documentation (auto-generated)
├── generation_manifest.json            # Full generation metadata
├── {author_slug}/
│   ├── llama3.1-8b/
│   │   ├── raw_t0.0/
│   │   │   ├── article_001.json
│   │   │   ├── article_002.json
│   │   │   └── ...
│   │   ├── raw_t0.8/
│   │   │   └── ...
│   │   ├── mimicry_t0.0/
│   │   └── mimicry_t0.8/
│   ├── mistral-7b/
│   │   ├── raw_t0.0/
│   │   ├── raw_t0.8/
│   │   ├── mimicry_t0.0/
│   │   └── mimicry_t0.8/
│   └── gemma2-9b/
│       └── ...
└── config_snapshot.json                # Frozen copy of generation config
```

Note: Directory names sanitize the Ollama model tag (colons replaced with hyphens) for filesystem compatibility.

### Article JSON format

Each generated article is stored as:

```json
{
  "article_id": "baseline_llama3.1-8b_raw_t0.0_001",
  "model": "llama3.1:8b",
  "model_digest": "sha256:abc123...",
  "provider": "ollama",
  "temperature": 0.0,
  "max_tokens": 1500,
  "prompt_template": "raw_generation",
  "prompt_text": "Write a 800-word news article about...",
  "topic_keywords": ["trump", "election", "poll"],
  "target_word_count": 800,
  "actual_word_count": 823,
  "text": "...",
  "generated_at": "2026-04-20T14:30:00Z",
  "eval_count": 1023,
  "eval_tokens_per_sec": 42.5,
  "generation_time_ms": 24070
}
```

The `model_digest` comes from `ollama list` and pins the exact model weights used. The `eval_count` and `eval_tokens_per_sec` come from Ollama's response metadata and document generation performance.

### README.md auto-generation

After generation completes, auto-generate `data/ai_baseline/README.md`:

```python
def generate_baseline_readme(manifest: dict, output_path: Path) -> None:
    """Generate human-readable documentation of the baseline generation protocol."""
    # Include: models used, versions, temperatures, prompt templates (verbatim),
    # topic distributions, article counts per cell, generation dates,
    # total cost estimate, known limitations
```

This README is part of the chain of custody — it documents exactly how the baseline was created so it's reproducible. Include the Ollama model digests (SHA256 from `ollama list`) to pin exact weights used.

## 3. Chain of Custody Measures

### 3a. Corpus Hashing

At the start of each analysis run, compute a deterministic hash of the full input corpus:

```python
import hashlib

def compute_corpus_hash(db_path: Path) -> str:
    """Hash all content_hash values from the articles table.

    This proves the corpus was not modified between runs.
    """
    conn = sqlite3.connect(db_path)
    hashes = conn.execute(
        "SELECT content_hash FROM articles ORDER BY id"
    ).fetchall()
    combined = "|".join(h[0] for h in hashes if h[0])
    return hashlib.sha256(combined.encode()).hexdigest()
```

Store in `analysis_runs` table:

```sql
ALTER TABLE analysis_runs ADD COLUMN input_corpus_hash TEXT;
```

### 3b. Immutable Raw Archives

The `data/raw/*.tar.gz` archives created in Phase 3 are **write-once**. Add a validation step:

```python
def verify_raw_archive_integrity(data_dir: Path) -> bool:
    """Verify raw archives haven't been modified since creation.

    Check: mtime of each .tar.gz matches the scraped_at timestamp of
    the newest article in that archive's year.
    """
```

### 3c. Scrape Timestamp Audit

Every article record must have a `scraped_at` timestamp (added in Phase 3 update). Add a validation query:

```python
def audit_scrape_timestamps(db_path: Path) -> dict:
    """Report scrape timestamp coverage.

    Returns:
        {
            "total_articles": int,
            "articles_with_scraped_at": int,
            "earliest_scrape": str,
            "latest_scrape": str,
            "scrape_duration_days": int,
        }
    """
```

### 3d. config.toml additions

```toml
[baseline]
ollama_base_url = "http://localhost:11434"
models = ["llama3.1:8b", "mistral:7b", "gemma2:9b"]
temperatures = [0.0, 0.8]
articles_per_cell = 30
max_tokens = 1500
request_timeout = 120  # seconds, accounts for cold model loads

[chain_of_custody]
verify_corpus_hash = true
verify_raw_archives = true
log_all_generations = true  # log every Ollama generation call
```

## 4. Baseline Feature Extraction

After generating the baseline corpus, run the same feature extraction pipeline (Phase 4 + Phase 9) on the baseline articles:

```python
def extract_baseline_features(
    baseline_dir: Path,
    config: ForensicsSettings,
) -> dict[str, pl.DataFrame]:
    """Extract features from AI baseline articles, grouped by model+temp+mode.

    Returns:
        {"llama3.1-8b_raw_t0.0": DataFrame, "mistral-7b_raw_t0.8": DataFrame, ...}
    """
```

Store in `data/ai_baseline/features/{model}_{mode}_{temp}.parquet`.

These features are used in:
- Phase 6: embedding drift comparison (AI baseline centroid)
- Phase 7: convergence framework (Pipeline B AI convergence score)
- Phase 9: perplexity calibration (expected perplexity range for AI text)

## 5. Evals — Baseline Quality Gate (evals/baseline_quality.py)

Use `pydantic-evals` to validate that generated baseline articles actually exhibit expected AI statistical signatures. This is the quality gate — generated articles that look too human-like (high burstiness, high perplexity) or too degenerate (gibberish, repetition) are flagged before they enter the baseline corpus.

### Eval Dataset

```python
from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, IsInstance


class BaselineInput(BaseModel):
    """Input to the baseline generation function under evaluation."""
    topic_keywords: list[str]
    target_word_count: int
    prompt_template: str
    temperature: float


class BaselineOutput(BaseModel):
    """Output from baseline generation — matches GeneratedArticle."""
    headline: str
    text: str
    actual_word_count: int
```

### Custom Evaluators

```python
class WordCountAccuracy(Evaluator[BaselineInput, BaselineOutput]):
    """Check that actual word count is within 15% of target."""

    tolerance: float = 0.15

    def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
        target = ctx.inputs.target_word_count
        actual = ctx.output.actual_word_count
        if abs(actual - target) <= target * self.tolerance:
            return 1.0
        return 0.0


class TopicRelevance(Evaluator[BaselineInput, BaselineOutput]):
    """Check that at least one topic keyword appears in the generated text."""

    def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
        text_lower = ctx.output.text.lower()
        hits = sum(1 for kw in ctx.inputs.topic_keywords if kw.lower() in text_lower)
        return min(1.0, hits / max(1, len(ctx.inputs.topic_keywords)))


class RepetitionDetector(Evaluator[BaselineInput, BaselineOutput]):
    """Flag degenerate repetitive output (common failure mode at temperature 0.0)."""

    max_repeated_ratio: float = 0.3

    def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
        sentences = ctx.output.text.split(". ")
        if len(sentences) < 3:
            return 1.0
        unique = len(set(sentences))
        ratio = 1.0 - (unique / len(sentences))
        return 0.0 if ratio > self.max_repeated_ratio else 1.0


class PerplexityRangeCheck(Evaluator[BaselineInput, BaselineOutput]):
    """After Phase 9 is available: verify generated text falls in expected AI perplexity range.

    This evaluator is optional — it requires the Phase 9 probability module to be importable.
    When available, it scores the generated article with GPT-2 perplexity and checks that
    the mean perplexity falls within the expected range for AI-generated text (typically 15-80
    for GPT-2 as reference model).
    """

    min_ppl: float = 10.0   # below this is suspiciously degenerate
    max_ppl: float = 120.0  # above this doesn't look AI-generated

    def evaluate(self, ctx: EvaluatorContext[BaselineInput, BaselineOutput]) -> float:
        try:
            from forensics.features.probability import compute_perplexity, load_reference_model
            model, tokenizer = load_reference_model()
            metrics = compute_perplexity(ctx.output.text, model, tokenizer)
            ppl = metrics["mean_perplexity"]
            if self.min_ppl <= ppl <= self.max_ppl:
                return 1.0
            return 0.0
        except ImportError:
            # Phase 9 not yet implemented — skip gracefully
            return 1.0
```

### Eval Dataset Definition

```python
baseline_eval_dataset = Dataset[BaselineInput, BaselineOutput, None](
    cases=[
        Case(
            name="politics_raw_t0.0",
            inputs=BaselineInput(
                topic_keywords=["trump", "election", "poll"],
                target_word_count=800,
                prompt_template="raw_generation",
                temperature=0.0,
            ),
            expected_output=None,  # no ground truth — evaluators check quality
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
```

### Running Evals

```bash
# Run evals against a specific Ollama model (requires Ollama running):
uv run python evals/baseline_quality.py --model llama3.1:8b

# Run evals across all three models (comparative quality check):
uv run python evals/baseline_quality.py --all-models

# Save eval report:
uv run python evals/baseline_quality.py --model llama3.1:8b --output evals/reports/llama3.1-8b.json
```

The eval harness wraps the PydanticAI agent's `run()` call in a transform function that the Dataset evaluates:

```python
async def generate_for_eval(inputs: BaselineInput) -> BaselineOutput:
    """Transform function bridging the eval dataset to the PydanticAI agent."""
    agent = make_baseline_agent(eval_model_name)
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
        result = await agent.run(build_prompt(inputs.prompt_template, deps), deps=deps)
        return BaselineOutput(
            headline=result.output.headline,
            text=result.output.text,
            actual_word_count=result.output.actual_word_count,
        )

# Run the eval
report = baseline_eval_dataset.evaluate_sync(generate_for_eval)
report.print(include_input=True, include_output=False)
```

### Eval Gating Policy

Before committing any batch of generated articles to the baseline corpus:

1. Run the eval suite across all three models
2. All cases must pass `WordCountAccuracy`, `TopicRelevance`, and `RepetitionDetector` at 100%
3. If `PerplexityRangeCheck` is available (Phase 9 complete), it must pass at ≥90%
4. If any model fails, investigate before including its output — the failure may indicate a model configuration issue or a poor prompt template

Store eval reports in `data/ai_baseline/eval_reports/` as part of chain of custody.

## 6. Tests (tests/test_baseline.py)

### Unit Tests (always run, no Ollama required)

- **test_topic_distribution_extraction**: Author with known articles -> correct topic proportions
- **test_word_count_sampling**: Sampled counts follow the source distribution
- **test_generation_manifest_schema**: Manifest JSON has all required fields
- **test_article_json_schema**: Generated article JSON validates against `GeneratedArticle` model
- **test_baseline_readme_generation**: README includes all protocol details
- **test_corpus_hash_deterministic**: Same corpus -> same hash
- **test_corpus_hash_changes**: Modified corpus -> different hash
- **test_scrape_timestamp_audit**: Articles without scraped_at are flagged
- **test_dry_run_no_ollama_calls**: Dry run produces plan without Ollama calls
- **test_preflight_check_missing_model**: Missing model returns helpful error message
- **test_model_digest_captured**: Generated articles include model SHA256 digest

### Agent Tests (use PydanticAI TestModel — no Ollama required)

```python
import pytest
from pydantic_ai.models.test import TestModel

from forensics.baseline.agent import make_baseline_agent, BaselineDeps, GeneratedArticle


@pytest.fixture
def test_agent():
    """Override agent with TestModel for deterministic unit testing."""
    agent = make_baseline_agent("llama3.1:8b")
    with agent.override(model=TestModel()):
        yield agent


async def test_agent_returns_generated_article(test_agent):
    """Agent produces a GeneratedArticle result type."""
    deps = BaselineDeps(
        author_slug="test-author",
        topic_keywords=["politics", "election"],
        target_word_count=500,
        prompt_template="raw_generation",
        temperature=0.0,
        output_dir=Path("/tmp/test"),
        http_client=httpx.AsyncClient(),
    )
    result = await test_agent.run("Write an article about politics.", deps=deps)
    assert isinstance(result.output, GeneratedArticle)


async def test_agent_retry_on_short_output(test_agent):
    """Agent retries when word count validation fails."""
    # TestModel returns minimal text — validation should trigger retry
    deps = BaselineDeps(...)
    with pytest.raises(Exception):
        # After max retries, should raise rather than return invalid output
        await test_agent.run("Write a 1000-word article.", deps=deps)
```

### Eval Tests (validate eval infrastructure, no Ollama required)

- **test_eval_dataset_schema**: `baseline_eval_dataset` loads without errors
- **test_word_count_evaluator**: Known inputs → correct pass/fail
- **test_topic_relevance_evaluator**: Text with/without keywords → correct scores
- **test_repetition_detector**: Repetitive text → score 0.0; diverse text → score 1.0

Use `TestModel` from `pydantic_ai.models.test` for all agent tests. Use mocked Ollama responses (`respx` or `pytest-httpx`) only for preflight/connectivity tests.

## 7. Dependencies

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
baseline = [
    "pydantic-ai[ollama]>=1.0",
    "pydantic-evals>=1.0",
]
```

The `pydantic-ai[ollama]` extra installs `OllamaProvider`. The `pydantic-evals` package provides the eval framework. These are optional — the core pipeline (Phases 1-9) does not require them.

Install with: `uv sync --extra baseline`

## Validation

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_baseline.py -v

# Preflight — verify Ollama is running and models are pulled:
uv run python scripts/generate_baseline.py --preflight

# Dry run to inspect generation plan:
uv run python scripts/generate_baseline.py --author {slug} --dry-run

# Actual generation (requires Ollama running with models pulled):
uv run python scripts/generate_baseline.py --author {slug} --articles-per-cell 5  # small test run
ls -la data/ai_baseline/{slug}/
cat data/ai_baseline/README.md
cat data/ai_baseline/generation_manifest.json | python -m json.tool | head -30

# Run evals before committing baseline (requires Ollama running):
uv run python evals/baseline_quality.py --model llama3.1:8b
uv run python evals/baseline_quality.py --all-models

# Verify chain of custody:
uv run forensics analyze --verify-corpus
```

## Handoff

After this phase, the AI baseline corpus exists with full documentation of how it was generated. The baseline is topic-stratified, multi-model (3 architecturally diverse local Ollama models), multi-temperature, and reproducible. No paid API subscriptions are required — all generation runs locally on the M1 Mac. Chain-of-custody measures (corpus hashing, model digest pinning, scrape timestamps, immutable archives) are in place. Phase 6's embedding drift analysis and Phase 7's convergence framework can now use a defensible AI reference for comparison.

**Why local models produce valid baselines:** The forensic signal we're detecting is not "did this author use GPT-4 specifically?" but rather "did this author's text shift toward statistical properties common to all autoregressive LLM output?" Low perplexity, uniform burstiness, and predictable token distributions are properties of the generation process, not any specific model. A baseline generated by Llama, Mistral, and Gemma captures these shared statistical signatures just as effectively as one generated by commercial APIs — and with the added benefit of full reproducibility (exact weights are pinned by digest, no API versioning surprises).
