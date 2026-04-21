# Phase 4: Feature Extraction — All Four Families + Embeddings

Version: 0.2.0
Status: pending
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 3 (scraped articles with clean text in SQLite)

## Objective

Implement the complete feature extraction pipeline: four feature families (lexical, structural, content, productivity), readability scores, and sentence transformer embeddings. Each article produces a `FeatureVector` stored in Parquet and an embedding stored as numpy. After this phase, `uv run forensics extract` processes all articles and writes to `data/features/` and `data/embeddings/`.

## Pre-requisites

Ensure spaCy model is available:
```bash
uv run python -m spacy download en_core_web_md
```

## 1. Family 1: Lexical Fingerprint (src/forensics/features/lexical.py)

### extract_lexical_features(text: str, doc: spacy.Doc) -> dict

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
- Formula: `K = 10^4 * (M2 - N) / N^2` where M2 = sum(i^2 * freq_spectrum[i]), N = total words

**Simpson's D**
- `D = sum(n_i * (n_i - 1)) / (N * (N - 1))` where n_i = frequency of each word type

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
- Return as dict[str, float] of relative frequencies

## 1b. POS Bigram & Phrase-Pattern Features (src/forensics/features/pos_patterns.py)

Recent stylometry research identifies POS bigrams and phrase patterns as among the most effective features for AI detection, complementing function word unigrams (already in lexical.py). Since spaCy is already in the stack, this is low-lift.

### extract_pos_pattern_features(doc: spacy.Doc) -> dict

**POS Bigram Frequency Vector**
- Extract consecutive POS tag pairs from the spaCy doc: `[(token.pos_, next_token.pos_) for ...]`
- Compute frequency distribution over all observed POS bigrams
- Normalize by total bigram count
- Return the top 30 most common POS bigrams as `dict[str, float]` (e.g., `{"DET_NOUN": 0.12, "NOUN_VERB": 0.08, ...}`)
- These capture syntactic rhythm independent of vocabulary — AI text tends to produce more uniform POS distributions

**Clause-Initial Phrase Patterns**
- For each sentence, extract the syntactic pattern of the first 3 tokens by POS tag (e.g., `"DET_ADJ_NOUN"`, `"ADV_VERB_DET"`)
- Compute frequency distribution of these opening patterns
- Return entropy of the distribution as `clause_initial_entropy` (higher = more diverse openings, more human-like)
- Return the top 10 most frequent patterns as `clause_initial_top10: dict[str, float]`

**Dependency-Tree Depth Distribution**
- For each sentence, compute the maximum depth of the dependency parse tree
- Return: `dep_depth_mean`, `dep_depth_std`, `dep_depth_max`
- AI-generated text tends toward shallower, more uniform dependency trees

### Tests to add (tests/test_features.py)

- **test_pos_bigram_extraction**: Known sentence -> expected POS bigrams present
- **test_pos_bigram_normalization**: Frequencies sum to ~1.0
- **test_clause_initial_entropy**: Repetitive openings -> low entropy; diverse openings -> high entropy
- **test_dep_depth_known_sentence**: "The cat sat on the mat" -> known dependency depth

## 2. Family 2: Sentence & Structure (src/forensics/features/structural.py)

### extract_structural_features(text: str, doc: spacy.Doc) -> dict

**Sentence length statistics**
- Use spaCy sentence segmentation (`doc.sents`)
- Compute: mean, median, std, skewness of sentence word counts
- Use `scipy.stats.skew` for skewness

**Subordinate clause depth**
- For each sentence, compute max depth of the dependency tree
- Report mean max depth across all sentences

**Conjunction frequency**
- Count coordinating conjunctions (POS=CCONJ) and subordinating conjunctions (POS=SCONJ)
- Normalize by total token count

**Passive voice ratio**
- Detect passive constructions via dependency labels: look for `nsubjpass` or `auxpass` dependency relations
- `passive_ratio = passive_sentences / total_sentences`

**Sentences per paragraph**
- Split text on double newlines to get paragraphs
- Compute mean sentences per paragraph

**Paragraph length variance**
- Standard deviation of paragraph word counts

**Punctuation profile**
- For each of: `;` `—` `!` `(` `)` `:` `...` `"`
- Compute frequency per 1000 characters
- Return as dict[str, float]

## 3. Family 3: Content & Repetitiveness (src/forensics/features/content.py)

### extract_content_features(text: str, doc: spacy.Doc, recent_texts_30d: list[str], recent_texts_90d: list[str]) -> dict

**Bigram/Trigram Entropy**
- Compute Shannon entropy over bigram and trigram frequency distributions
- `H = -sum(p * log2(p))` for each n-gram probability
- Lower entropy = more formulaic/repetitive

**Self-Similarity (30d, 90d)**
- Compute TF-IDF vectors for the current article and recent articles (30-day and 90-day windows)
- Self-similarity = mean cosine similarity between current article and recent articles
- Use `sklearn.feature_extraction.text.TfidfVectorizer` and `sklearn.metrics.pairwise.cosine_similarity`
- If no recent articles in window, return 0.0

**Topic Diversity Score**
- Over a rolling window of the author's recent articles, fit LDA with k=10 topics
- Compute entropy of the topic distribution for the current article
- Higher entropy = more diverse topics = less templated

**Opening/Closing Formula Score**
- Extract first sentence and last sentence of each article
- Compare against templates (e.g., "In a recent...", "As [outlet] reported...", "Time will tell...")
- Use cosine similarity against a small set of template embeddings, or simple regex pattern matching
- Return a 0-1 score where higher = more formulaic

**First-Person Pronoun Ratio**
- Count I, me, my, mine, we, us, our, ours
- Normalize by total word count

**Hedging Frequency**
- Count hedging phrases: "perhaps", "might", "could be argued", "it seems", "appears to", "likely", "possibly", "it is possible", "one could argue", "to some extent"
- Normalize by total sentences

## 4. Family 4: Productivity Signals (src/forensics/features/productivity.py)

### extract_productivity_features(article_date: datetime, author_articles: list[tuple[datetime, int]]) -> dict

Takes the current article date and a chronologically sorted list of (published_date, word_count) tuples for all of the author's articles.

**Days since last article**
- Gap between current article and the previous one
- First article gets 0.0

**Rolling 7-day article count**
- Number of articles by this author in the 7 days preceding (and including) this article

**Rolling 30-day article count**
- Same for 30-day window

Note: Burst detection (Kleinberg's algorithm) is deferred to the analysis phase (Phase 5) since it operates on the full time series, not per-article.

## 5. Readability Scores (src/forensics/features/readability.py)

### extract_readability_features(text: str) -> dict

Use the `textstat` library:
- `flesch_kincaid`: `textstat.flesch_kincaid_grade(text)`
- `coleman_liau`: `textstat.coleman_liau_index(text)`
- `gunning_fog`: `textstat.gunning_fog(text)`
- `smog`: `textstat.smog_index(text)`

## 6. Embeddings (src/forensics/features/embeddings.py)

### compute_embedding(text: str, model_name: str) -> np.ndarray

Use `sentence-transformers`:
```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer(model_name)  # cached after first load
embedding = model.encode(text, show_progress_bar=False)
```

- Default model: `all-MiniLM-L6-v2` (384-dim)
- Cache the loaded model at module level (load once, reuse)
- Truncate long articles to first 512 tokens (model max) — sentence-transformers handles this internally

### Storage

For each article:
- Save embedding as numpy array to `data/embeddings/{author_slug}/{article_id}.npy`
- Create an `EmbeddingRecord` with metadata (model_name, model_version, dim, path)
- Save embedding metadata to `data/embeddings/manifest.jsonl`

### Model versioning

Read `embedding_model` and `embedding_model_version` from `AnalysisConfig`. Before processing, check if existing embeddings were created with a different model version. If mismatch detected:
- Log a warning
- Archive old embeddings to `data/embeddings/archive/`
- Re-embed entire corpus

## 7. Pipeline Orchestrator (src/forensics/features/pipeline.py)

### extract_all_features(db_path: Path, config: ForensicsSettings) -> int

Main orchestration function:

1. Load spaCy model once: `nlp = spacy.load("en_core_web_md")`
2. Load sentence transformer once
3. Query all articles from SQLite (exclude duplicates, redirects, and <50 word articles)
4. Group articles by author, sort by date within each group
5. For each article:
   a. Run spaCy: `doc = nlp(clean_text)`
   b. Extract lexical features
   c. Extract structural features
   d. Extract content features (pass recent articles for self-similarity)
   e. Extract productivity features (pass author's article history)
   f. Extract readability features
   g. Compute embedding
   h. Assemble `FeatureVector` model
6. Write all feature vectors to Parquet: `data/features/{author_slug}.parquet`
7. Return count of processed articles

### Per-article isolation

If feature extraction fails for one article (e.g., spaCy parse error on malformed text), catch the exception, log a warning with the article ID and error, and skip that article. The pipeline must not halt on individual failures.

### NaN handling

Features that cannot be computed (e.g., TTR on an article with 0 words after cleaning) should be stored as `float('nan')`. Downstream analysis excludes NaN values rather than erroring.

### Progress logging

Log: "Extracting features: {n}/{total} articles ({author_name})" every 50 articles.

## 8. Parquet Storage (src/forensics/storage/parquet.py)

### write_features(features: list[FeatureVector], output_path: Path) -> None

Convert list of FeatureVector models to a Polars DataFrame and write to Parquet:

```python
import polars as pl

records = [f.model_dump() for f in features]
df = pl.DataFrame(records)
df.write_parquet(output_path)
```

### read_features(path: Path) -> pl.DataFrame

```python
return pl.read_parquet(path)
```

### write_embeddings_manifest(records: list[EmbeddingRecord], path: Path) -> None

Write to JSONL.

## 9. CLI Integration

Update `extract` command:

```
uv run forensics extract              # extract features + embeddings for all articles
uv run forensics extract --author {slug}  # extract for a single author
uv run forensics extract --skip-embeddings  # skip the embedding step (faster for testing)
```

## 10. Tests (tests/test_features.py)

Create test fixtures with known text samples:

- **test_ttr_calculation**: Known text -> expected TTR
- **test_mattr_window**: Text shorter than window size handled gracefully
- **test_hapax_ratio**: Text with known hapax count -> correct ratio
- **test_ai_marker_detection**: Text containing "it's important to note" and "delve" -> correct count
- **test_sentence_stats**: Known sentences -> correct mean/median/std
- **test_passive_voice_detection**: "The ball was thrown" -> detected; "He threw the ball" -> not detected
- **test_punctuation_profile**: Text with known punctuation -> correct frequencies
- **test_bigram_entropy**: Highly repetitive text -> low entropy; diverse text -> high entropy
- **test_self_similarity**: Identical texts -> similarity ~1.0; unrelated texts -> low similarity
- **test_readability_scores**: Verify textstat returns reasonable values for sample text
- **test_embedding_shape**: Verify embedding is 384-dim numpy array
- **test_feature_pipeline_isolation**: One malformed article doesn't crash pipeline
- **test_nan_handling**: Zero-word article produces NaN features, not errors

## Validation

```bash
uv sync
uv run python -m spacy download en_core_web_md
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_features.py -v

# Smoke test (requires Phase 3 data):
uv run forensics extract --author {some-author-slug}
ls -la data/features/
ls -la data/embeddings/
```

## Handoff

After this phase, `data/features/{author_slug}.parquet` contains ~30 features per article for every configured author, and `data/embeddings/` contains 384-dim vectors. The corpus is fully featurized and ready for Phase 5 (change-point detection and time-series analysis).
