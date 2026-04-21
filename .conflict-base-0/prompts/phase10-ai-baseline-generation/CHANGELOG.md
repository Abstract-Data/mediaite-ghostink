# Changelog

## [0.3.0] - 2026-04-20
### Changed
- Replaced raw httpx Ollama API integration with PydanticAI agent architecture.
- Generation now uses `Agent` with `deps_type=BaselineDeps` and `output_type=GeneratedArticle`.
- Word count enforcement via `ModelRetry` tool instead of post-hoc validation.
- Article metadata now includes PydanticAI usage tracking (input_tokens, output_tokens, requests).

### Added
- PydanticAI agent definition with `OllamaProvider` (v1.0.5 API).
- `GeneratedArticle` structured output type with Pydantic validation.
- `BaselineDeps` typed dependency dataclass.
- `check_word_count` agent tool with 15% tolerance and `ModelRetry`.
- `make_baseline_agent()` factory function — one agent per model.
- `run_generation_matrix()` orchestrator with model rotation strategy.
- Section 5: `pydantic-evals` quality gate (`evals/baseline_quality.py`).
- Four custom evaluators: `WordCountAccuracy`, `TopicRelevance`, `RepetitionDetector`, `PerplexityRangeCheck`.
- Eval gating policy — all models must pass before baseline is committed.
- Agent tests using `TestModel` (no Ollama required).
- Eval infrastructure tests (dataset schema, evaluator correctness).
- Optional dependencies: `pydantic-ai[ollama]>=1.0`, `pydantic-evals>=1.0`.

## [0.2.0] - 2026-04-20
### Changed
- Replaced commercial API models (GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro) with local Ollama models (Llama 3.1 8B, Mistral 7B, Gemma 2 9B).
- Switched API integration from OpenAI/Anthropic/Google SDKs to Ollama REST API at localhost:11434.
- Updated article JSON format: replaced `api_response_id` with `model_digest`, `eval_count`, `eval_tokens_per_sec`.
- Updated config.toml with `[baseline]` section for Ollama settings.

### Added
- Ollama API integration with async httpx client.
- Preflight check command (`--preflight`) to verify Ollama connectivity and model availability.
- Model digest (SHA256) pinning for chain-of-custody reproducibility.
- Hardware guidance for M1 Mac with 32GB unified memory.
- Three new tests: preflight check, model digest capture, dry run validation.

## [0.1.0] - 2026-04-20
### Added
- Initial prompt — multi-model, multi-temperature, topic-stratified AI baseline generation protocol with chain-of-custody measures.
