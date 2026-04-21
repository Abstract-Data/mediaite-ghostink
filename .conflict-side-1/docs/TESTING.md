# Testing Strategy

## Goals

- Keep pipeline behavior deterministic.
- Validate CLI surface and stage orchestration.
- Catch regressions in output artifacts under `data/`.
- Property-test edge cases in feature extraction and data validation.
- Benchmark performance of compute-heavy stages.

## Test Layout

- `tests/unit/` — stage logic, model validation, utility functions
- `tests/integration/` — CLI command coverage, pipeline wiring, storage round-trips
- `tests/evals/` — capability/regression eval scenarios
- `tests/fixtures/` — sample data files (CSV, JSON, Parquet) for reproducible tests

## Standard Commands

```bash
# Run all tests
uv run pytest tests/ -v

# Run by category
uv run pytest tests/unit -v
uv run pytest tests/integration -v
uv run pytest tests/evals/ -v

# Run specific test
uv run pytest -k "test_feature_extraction" -v

# With coverage
uv run pytest tests/ -v --cov=src --cov-report=term-missing

# Property-based testing with statistics
uv run pytest tests/ -v --hypothesis-show-statistics

# Stop on first failure (fast feedback)
uv run pytest tests/unit -x
```

## Quality Gates

- Lint must pass: `uv run ruff check .`
- Format check must pass: `uv run ruff format --check .`
- Test suite must pass before merging.
- Coverage target: 80% (enforced in `pyproject.toml` via `fail_under = 80`).

## Coverage Omission Policy

Coverage omissions in `pyproject.toml` must follow these rules:

1. **Per-file justification.** Every omitted path must be a specific file (not a wildcard like `scraper/*`). Each omission must have an inline comment explaining why it's excluded (e.g., `# stub — Phase 4, not yet implemented`).
2. **Implemented modules must never be omitted.** Once a module has real logic (not just `pass`), it must be covered by the test suite. Removing it from coverage hides real test gaps.
3. **Review omissions when stubs are implemented.** When you implement a stub module, remove its coverage omission in the same PR. Do not leave stale exclusions.
4. **Separate profiles for reporting.** If you need to distinguish "coverage of implemented code" from "coverage of entire project," use separate coverage profiles or report configurations — not blanket omissions that hide the true state.

Example of correct omissions:

```toml
[tool.coverage.run]
source = ["forensics"]
branch = true
omit = [
    "*/forensics/features/lexical.py",       # stub — Phase 4
    "*/forensics/features/structural.py",     # stub — Phase 4
    "*/forensics/features/content.py",        # stub — Phase 4
    "*/forensics/features/productivity.py",   # stub — Phase 4
    "*/forensics/features/readability.py",    # stub — Phase 4
    "*/forensics/features/embeddings.py",     # stub — Phase 4
    "*/forensics/features/pipeline.py",       # stub — Phase 4
    "*/forensics/analysis/changepoint.py",    # stub — Phase 5
    "*/forensics/analysis/timeseries.py",     # stub — Phase 5
    "*/forensics/analysis/drift.py",          # stub — Phase 6
    "*/forensics/analysis/convergence.py",    # stub — Phase 6
    "*/forensics/analysis/comparison.py",     # stub — Phase 6
    "*/forensics/analysis/statistics.py",     # stub — Phase 6
    "*/forensics/storage/parquet.py",         # stub — Phase 7
    "*/forensics/storage/duckdb_queries.py",  # stub — Phase 7
    "*/forensics/pipeline.py",               # stub — orchestration not yet wired
]
```

## TDD Workflow

For every new feature or bugfix:

1. **Red** — Write a failing test that describes the expected behavior.
2. **Green** — Write the minimum code to make the test pass.
3. **Refactor** — Clean up while keeping tests green.
4. **Validate** — Run full suite (`uv run pytest tests/ -v`) before committing.

For pipeline stages, write the stage contract test first (input type → output type → expected shape), then implement the stage.

## Property-Based Testing

Use Hypothesis for testing functions with many edge cases, especially in feature extraction and data validation.

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=10000))
def test_ttr_is_bounded(text: str):
    """Type-token ratio must always be between 0 and 1."""
    words = text.split()
    if len(words) > 0:
        ttr = len(set(words)) / len(words)
        assert 0.0 <= ttr <= 1.0

@given(st.lists(st.floats(allow_nan=False, allow_infinity=False), min_size=2))
def test_cosine_similarity_bounded(values: list[float]):
    """Cosine similarity must be in [-1, 1]."""
    # Test your cosine similarity implementation here
    pass
```

Good candidates for property-based tests in this project:
- Feature extraction functions (TTR, Yule's K, MATTR — all have mathematical bounds)
- Pydantic model validation (ensure invalid inputs always raise ValidationError)
- Simhash deduplication (Hamming distance properties)
- Change-point detection output shapes (number of changepoints ≤ number of observations)

### Hypothesis Requirements

Hypothesis is a declared dev dependency. It must be actively used, not just listed. The following modules **require** property-based tests:

1. **Parsing utilities** (`scraper/parser.py`) — HTML parsing should handle arbitrary input without crashing. Test with `st.text()` inputs containing malformed HTML, empty strings, and edge-case Unicode.
2. **Hashing utilities** (`utils/hashing.py`) — Simhash fingerprints must be deterministic and the Hamming distance function must satisfy triangle inequality. Test with `st.binary()` and `st.text()`.
3. **Feature extraction** (Phase 4, when implemented) — All feature functions with mathematical bounds (TTR ∈ [0,1], Yule's K ≥ 0, sentence lengths ≥ 0) must have property tests asserting those bounds.
4. **Pydantic model validation** — Models accepting external input must reject invalid data consistently. Test with `st.from_type()` or custom strategies.

When implementing a new module, check whether property-based tests are appropriate before writing only example-based tests. If the function has invariants (bounded outputs, deterministic behavior, algebraic properties), write a `@given` test.

## Performance Benchmarks

For compute-heavy stages, add benchmark tests with `pytest-benchmark` or simple timing assertions:

```python
import time

def test_feature_extraction_performance(large_corpus):
    """Feature extraction should process 1000 articles in under 60 seconds."""
    start = time.perf_counter()
    results = extract_features(large_corpus)
    elapsed = time.perf_counter() - start
    assert elapsed < 60.0, f"Feature extraction took {elapsed:.1f}s (limit: 60s)"
    assert len(results) == len(large_corpus)
```

Benchmark targets:
- Feature extraction: < 60s for 1000 articles
- Embedding generation: < 120s for 1000 articles (GPU) / < 600s (CPU)
- Change-point detection: < 30s for 10-year author timeline
- Full pipeline (all stages): < 30 minutes for a single author

## Test Authoring Guidance

- Keep tests deterministic (no network dependency by default).
- Use temporary directories (`tmp_path`) for file-write assertions.
- Validate both return payloads and filesystem side-effects.
- Add regression tests for any behavior change before/alongside implementation.
- Use `@pytest.mark.slow` for tests that exceed 5 seconds.
- Use `@pytest.mark.integration` for tests requiring external resources.
- Mock external APIs (WordPress REST API, sentence-transformers) in unit tests.

## Fixture Strategy

```python
@pytest.fixture
def sample_articles() -> list[dict]:
    """Minimal article set for unit testing."""
    return [
        {"url": "https://example.com/1", "author_id": 1, "text": "...", "word_count": 500},
        {"url": "https://example.com/2", "author_id": 1, "text": "...", "word_count": 300},
    ]

@pytest.fixture
def feature_vectors(sample_articles) -> pl.DataFrame:
    """Pre-computed feature vectors for analysis tests."""
    return pl.DataFrame({
        "article_id": [1, 2],
        "ttr": [0.65, 0.72],
        "yules_k": [120.5, 135.2],
        "mean_sentence_length": [18.3, 22.1],
    })
```
