# Phase 4: Feature Extraction — All Four Families + Embeddings

Version: 0.3.0
Status: draft
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 3 (scraped articles with clean text in SQLite)

## Objective

Implement the complete feature extraction pipeline: four feature families (lexical, structural, content, productivity), readability scores, sentence-transformer embeddings, and POS / dependency-shape signals from §1b. Each qualifying article produces a `FeatureVector` row (Parquet per author) and an optional `.npy` embedding plus `EmbeddingRecord` lines in a manifest. After this phase, `uv run forensics extract` runs end-to-end and writes under `data/features/` and `data/embeddings/`.

## Codebase alignment (read before coding)

- **Storage:** Use `Repository` from `forensics.storage.repository` (instance methods, `db_path` on the object). Add a dedicated query method if needed, for example `list_articles_for_extraction(...)`, rather than duplicating SQL across the pipeline.
- **Models:** `Article` (`forensics.models.article`), `FeatureVector` and `EmbeddingRecord` (`forensics.models.features`). Extend these Pydantic models in place when new scalar or dict fields are required — do not introduce a parallel schema.
- **Config:** `ForensicsSettings` and nested `AnalysisConfig` (`forensics.config.settings`). Embedding defaults already live on `AnalysisConfig`: `embedding_model` (`sentence-transformers/all-MiniLM-L6-v2`), `embedding_model_version` (`v2.0`).
- **Stubs to replace:** `src/forensics/features/*.py` (except `__init__.py`) and `src/forensics/features/pipeline.py` are `pass` placeholders; `src/forensics/storage/parquet.py` is a stub. Implement inside this layout.
- **CLI:** `build_parser()` already registers `extract`, but `main()` still logs *Phase not yet implemented* for non-`scrape` commands. Wire `args.command == "extract"` to the pipeline entrypoint and return proper exit codes.

## Article selection (inclusion / exclusion)

Process only articles that pass all checks:

| Rule | Action |
|------|--------|
| `clean_text` is empty or whitespace-only | skip |
| `clean_text` starts with `[REDIRECT:` (Phase 3 off-domain marker) | skip |
| `is_duplicate` is true | skip |
| `word_count` under 50 (after cleaning) | skip |

Group remaining rows by `author_id`, sort by `published_date` ascending for productivity and rolling-window features. Use `published_date` as the article timestamp in `FeatureVector.timestamp` unless the project ADR specifies otherwise.

## Pydantic schema extensions

`FeatureVector` (in `models/features.py`) currently lists lexical, structural, readability, content, and productivity fields. **Add** the following so §1b outputs are first-class:

- `pos_bigram_top30: dict[str, float]` — normalized frequencies, keys like `DET_NOUN`
- `clause_initial_entropy: float`
- `clause_initial_top10: dict[str, float]`
- `dep_depth_mean: float`, `dep_depth_std: float`, `dep_depth_max: float`

`EmbeddingRecord` must carry **`model_version: str`** alongside `model_name` so manifest rows and `AnalysisConfig.embedding_model_version` can be reconciled for re-embed decisions.

**Parquet shape:** Prefer keeping `dict[str, float]` columns as Polars `Struct` or `Object`/JSON-serializable maps consistent with `FeatureVector.model_dump()`. If flattening is chosen for downstream tools, use a single explicit naming convention (document in code comments only; no new ADR unless behavior changes analysis).

## Pre-requisites

```bash
uv sync
uv run python -m spacy download en_core_web_md
```

Heavy ML deps (`sentence-transformers`, `scikit-learn`, `scipy`, `polars`, `textstat`, `spacy`) should already be declared in `pyproject.toml` from project bootstrap; if any import fails, add the missing package via `uv add` rather than ad-hoc pip.

## 1. Family 1: Lexical Fingerprint (`src/forensics/features/lexical.py`)

### `extract_lexical_features(text: str, doc: spacy.Doc) -> dict`

Implement each feature:

**Type-Token Ratio (TTR)**

- `ttr = len(unique_words) / len(total_words)`
- Use lowercased, alphabetic-only tokens

**Moving Average TTR (MATTR)**

- Compute TTR over sliding window of 50 words
- Average all window TTRs
- More robust to article length variation than raw TTR

**Hapax Legomena Ratio**

- `hapax_ratio = words_appearing_once / total_unique_words`
- Human writers tend to have higher hapax ratios

**Yule's K**

- Statistical vocabulary richness measure
- Formula: `K = 10^4 * (M2 - N) / N^2` where `M2 = sum(i^2 * freq_spectrum[i])`, `N` = total words

**Simpson's D**

- `D = sum(n_i * (n_i - 1)) / (N * (N - 1))` where `n_i` = frequency of each word type

**AI Marker Phrase Frequency**

- Count occurrences of LLM-typical phrases per total sentences
- Curated dictionary (load from config, extensible):

  ```
  "it's important to note", "it's worth noting", "delve", "in today's * landscape",
  "navigate", "underscores", "arguably", "at its core", "a testament to",
  "in an era of", "serves as a", "plays a crucial role", "it should be noted",
  "represents a significant", "offers a unique", "is a game-changer"
  ```

- Use case-insensitive matching; support simple wildcards with regex

**Function Word Distribution**

- Frequency vector of top 50 English function words (the, a, is, of, and, to, in, that, it, for, was, on, are, with, as, at, be, this, have, from, by, not, but, what, all, were, when, we, there, can, an, your, which, their, if, do, will, each, about, how, up, out, them, then, she, many, some, so, these, would)
- Return as `dict[str, float]` of relative frequencies

## 1b. POS Bigram & Phrase-Pattern Features (`src/forensics/features/pos_patterns.py`)

Recent stylometry research identifies POS bigrams and phrase patterns as among the most effective complements to function-word unigrams. spaCy is already required.

### `extract_pos_pattern_features(doc: spacy.Doc) -> dict`

**POS Bigram Frequency Vector**

- Extract consecutive POS tag pairs: `[(token.pos_, next_token.pos_) for ...]`
- Normalize by total bigram count
- Return the top 30 as `dict[str, float]` (e.g. `DET_NOUN`)

**Clause-Initial Phrase Patterns**

- For each sentence, pattern of first 3 tokens by POS (e.g. `DET_ADJ_NOUN`)
- Return entropy of the distribution as `clause_initial_entropy`
- Return top 10 patterns as `clause_initial_top10: dict[str, float]`

**Dependency-Tree Depth Distribution**

- Per sentence, max depth of the dependency parse tree
- Return `dep_depth_mean`, `dep_depth_std`, `dep_depth_max`

### Tests (`tests/test_features.py`)

- `test_pos_bigram_extraction`, `test_pos_bigram_normalization`, `test_clause_initial_entropy`, `test_dep_depth_known_sentence`

## 2. Family 2: Sentence & Structure (`src/forensics/features/structural.py`)

### `extract_structural_features(text: str, doc: spacy.Doc) -> dict`

**Sentence length statistics** — `doc.sents`; mean, median, std, skewness (`scipy.stats.skew`)

**Subordinate clause depth** — mean max dependency depth per sentence (coordinate with §1b depth metrics: structural may reuse a shared helper to avoid duplicate tree walks)

**Conjunction frequency** — CCONJ + SCONJ counts / total tokens

**Passive voice ratio** — `nsubjpass` or `auxpass` → `passive_sentences / total_sentences`

**Sentences per paragraph** — split on double newlines; mean sentences per paragraph

**Paragraph length variance** — std dev of paragraph word counts

**Punctuation profile** — per 1000 chars for `;` `—` `!` `(` `)` `:` `...` `"`

## 3. Family 3: Content & Repetitiveness (`src/forensics/features/content.py`)

### `extract_content_features(text: str, doc: spacy.Doc, recent_texts_30d: list[str], recent_texts_90d: list[str]) -> dict`

**Bigram/Trigram Entropy** — Shannon `H = -sum(p * log2(p))`

**Self-Similarity (30d, 90d)** — `TfidfVectorizer` + `cosine_similarity`; 0.0 if no peers in window

**Topic Diversity Score** — LDA `k=10` over rolling author window; entropy of current article topic mix

**Opening/Closing Formula Score** — template / regex or small embedding similarity; 0–1 higher = more formulaic

**First-Person Pronoun Ratio** — I, me, my, mine, we, us, our, ours / word count

**Hedging Frequency** — listed hedges / sentence count

## 4. Family 4: Productivity Signals (`src/forensics/features/productivity.py`)

### `extract_productivity_features(article_date: datetime, author_articles: list[tuple[datetime, int]]) -> dict`

Chronologically sorted `(published_date, word_count)` for the author.

**Days since last article** — gap from previous; first article → `0.0`

**Rolling 7-day / 30-day article counts** — include current article’s date in the window definition consistently (document in docstring)

Burst detection (Kleinberg) stays deferred to Phase 5.

## 5. Readability Scores (`src/forensics/features/readability.py`)

### `extract_readability_features(text: str) -> dict`

Use `textstat`: `flesch_kincaid_grade`, `coleman_liau_index`, `gunning_fog`, `smog_index` (map to `FeatureVector` field names).

## 6. Embeddings (`src/forensics/features/embeddings.py`)

### `compute_embedding(text: str, model_name: str) -> np.ndarray`

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(model_name)
embedding = model.encode(text, show_progress_bar=False)
```

- Default model string: read from `settings.analysis.embedding_model`
- Cache model at module level
- Long texts: rely on library truncation or explicit truncation consistent with model card

### Storage

- `data/embeddings/{author_slug}/{article_id}.npy`
- Append `EmbeddingRecord` rows to `data/embeddings/manifest.jsonl` (include `model_version`)

### Model versioning

Compare on-disk manifest / last run vs `embedding_model` + `embedding_model_version`. On mismatch: log warning, move prior tree to `data/embeddings/archive/{timestamp}/`, re-embed.

## 7. Pipeline Orchestrator (`src/forensics/features/pipeline.py`)

### `extract_all_features(db_path: Path, settings: ForensicsSettings, *, author_slug: str | None = None, skip_embeddings: bool = False) -> int`

1. Load spaCy once: `nlp = spacy.load("en_core_web_md")`
2. Load sentence transformer once unless `skip_embeddings`
3. `repo = Repository(db_path)` — fetch candidates via one SQL path (see Article selection)
4. Filter `--author` by matching author slug from `settings.authors` → `author_id` if provided
5. Per article: `doc = nlp(clean_text)` → lexical → structural → pos_patterns → content → productivity → readability → optional embedding → build `FeatureVector`
6. Write Parquet per author: `data/features/{author_slug}.parquet`
7. Return count of successfully processed articles

**Per-article isolation:** try/except per article; log warning with id; continue.

**NaN:** use `float("nan")` for undefined scalars; dicts may be empty.

**Progress:** every 50 articles log `Extracting features: {n}/{total} ({author_name})`.

## 8. Parquet & manifest helpers (`src/forensics/storage/parquet.py`)

### `write_features(features: list[FeatureVector], output_path: Path) -> None`

Polars from `model_dump()` rows; `df.write_parquet(output_path)`.

### `read_features(path: Path) -> pl.DataFrame`

### `write_embeddings_manifest(records: list[EmbeddingRecord], path: Path) -> None`

JSONL append or atomic rewrite — pick one strategy and use it consistently for reruns.

## 9. CLI integration (`src/forensics/cli.py`)

Extend the `extract` parser:

```text
uv run forensics extract
uv run forensics extract --author {slug}
uv run forensics extract --skip-embeddings
```

Implement parsing and dispatch in `main()` / a small `_run_extract` synchronous wrapper (the pipeline itself may stay synchronous; no need for `asyncio` unless you later parallelize CPU work).

## 10. Tests (`tests/test_features.py`)

Replace stub-only tests with real cases:

- **Lexical:** `test_ttr_calculation`, `test_mattr_window`, `test_hapax_ratio`, `test_ai_marker_detection`
- **Structural:** `test_sentence_stats`, `test_passive_voice_detection`, `test_punctuation_profile`
- **Content:** `test_bigram_entropy`, `test_self_similarity`
- **Readability:** `test_readability_scores`
- **Embeddings:** `test_embedding_shape` (384 for MiniLM)
- **Pipeline:** `test_feature_pipeline_isolation`, `test_nan_handling`
- **POS:** tests listed in §1b

## Validation

```bash
uv sync
uv run python -m spacy download en_core_web_md
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_features.py -v

# Smoke (requires Phase 3 SQLite data):
uv run forensics extract --author {some-author-slug}
ls -la data/features/
ls -la data/embeddings/
```

## Handoff

Parquet under `data/features/` holds one row per processed article with lexical, structural, POS-shape, readability, content, and productivity fields; embeddings sit under `data/embeddings/` with a versioned manifest. Downstream Phase 5 prompts may assume these paths and column names on `FeatureVector`.
