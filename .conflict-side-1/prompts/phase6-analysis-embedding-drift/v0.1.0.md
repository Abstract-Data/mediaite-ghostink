# Phase 6: Analysis — Embedding Drift & AI Baseline Comparison

Version: 0.1.0
Status: pending
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 4 (embeddings in numpy), Phase 5 (change-point infrastructure)

## Objective

Implement Pipeline B (Embedding Drift Analysis): track how each author's voice moves through embedding space over time and measure convergence toward AI-generated baselines. This is the holistic layer that captures subtle patterns individual features might miss. After this phase, `uv run forensics analyze --drift` produces drift scores, centroid trajectories, and AI convergence metrics.

## 1. Monthly Centroid Tracking (src/forensics/analysis/drift.py)

### compute_monthly_centroids(author_id: str, embeddings_dir: Path, db_path: Path) -> dict

For each author:
1. Load all embeddings from `data/embeddings/{author_slug}/`
2. Join with article dates from SQLite
3. Group by calendar month
4. Compute centroid (mean vector) for each month

```python
import numpy as np

def compute_monthly_centroids(
    article_embeddings: list[tuple[datetime, np.ndarray]],
) -> list[tuple[str, np.ndarray]]:
    """Compute mean embedding vector per month.

    Args:
        article_embeddings: list of (published_date, embedding_vector) tuples

    Returns:
        list of (year_month_str, centroid_vector) tuples, sorted chronologically
    """
    from collections import defaultdict
    monthly = defaultdict(list)
    for dt, emb in article_embeddings:
        key = dt.strftime("%Y-%m")
        monthly[key].append(emb)

    centroids = []
    for month in sorted(monthly.keys()):
        vectors = np.stack(monthly[month])
        centroid = vectors.mean(axis=0)
        centroids.append((month, centroid))
    return centroids
```

### track_centroid_velocity(centroids: list[tuple[str, np.ndarray]]) -> list[float]

Compute the cosine distance between consecutive monthly centroids — this is the "velocity" of voice drift:

```python
from scipy.spatial.distance import cosine

velocities = []
for i in range(1, len(centroids)):
    dist = cosine(centroids[i-1][1], centroids[i][1])
    velocities.append(dist)
```

A sudden increase in velocity = the author's voice changed rapidly that month.

## 2. Cosine Similarity Decay Curve (src/forensics/analysis/drift.py)

### compute_baseline_similarity_curve(article_embeddings, baseline_count: int = 20) -> list[tuple[datetime, float]]

1. Take the first `baseline_count` articles as the "original voice" baseline
2. Compute the baseline centroid from those embeddings
3. For every article, compute cosine similarity to the baseline centroid
4. Return as a time series: (date, similarity_score)

This produces a decay curve — if the author's voice drifts over time, similarity to their original baseline decreases. A stable author maintains ~constant similarity.

## 3. Intra-Period Variance (src/forensics/analysis/drift.py)

### compute_intra_period_variance(article_embeddings, period: str = "month") -> list[tuple[str, float]]

For each month (or other period):
1. Collect all embeddings in that period
2. Compute mean pairwise cosine distance within the period
3. Return as time series

Hypothesis: AI assistance reduces within-period variance because AI-assisted articles are more uniform in style. A decreasing variance trend over time is a signal.

## 4. AI Baseline Comparison Protocol (src/forensics/analysis/drift.py)

### AI Baseline Generation

This is a one-time step, implemented as a separate command. Follows the protocol from Section 15 of the spec:

```python
async def generate_ai_baseline(
    db_path: Path,
    author_slug: str,
    config: AnalysisConfig,
    llm_model: str = "gpt-4o",
    articles_per_topic: int = 3,
    num_topics: int = 20,
) -> Path:
    """Generate synthetic AI-written articles for baseline comparison.

    1. Extract top 20 topics from target author's corpus via LDA
    2. For each topic, generate 3 articles via LLM
    3. Store in data/ai_baseline/ with full provenance
    4. Embed with same model as real articles
    5. Return path to ai_baseline directory
    """
```

**Topic extraction:**
- Use scikit-learn's LDA on the target author's TF-IDF matrix
- Extract top 20 topics, each represented by top 10 keywords
- Construct human-readable topic summaries

**Prompt construction:**
```
Write a {word_count}-word news article about {topic_summary} in the style of a professional journalist.
```
- No author-specific style instructions — we want generic AI output
- `word_count` = median word count from the author's corpus

**Storage:**
Each synthetic article stored as JSON in `data/ai_baseline/`:
```json
{
    "id": "...",
    "topic_id": 5,
    "topic_keywords": ["politics", "senate", "vote", ...],
    "prompt": "Write a 650-word news article about...",
    "model": "gpt-4o",
    "model_version": "2025-01-01",
    "generated_at": "...",
    "text": "...",
    "generation_params": {"temperature": 0.7, "max_tokens": 1500}
}
```

**Note:** This step requires an OpenAI API key (or other LLM provider). Make it configurable and skippable — the rest of the drift analysis works without it; the AI convergence metric just won't be computed.

### AI Baseline Embedding & Comparison

```python
def compute_ai_convergence(
    author_monthly_centroids: list[tuple[str, np.ndarray]],
    ai_baseline_embeddings: list[np.ndarray],
) -> list[tuple[str, float]]:
    """Measure whether author's voice converges toward AI embedding region.

    Returns list of (month, similarity_to_ai_centroid) tuples.
    """
    ai_centroid = np.mean(np.stack(ai_baseline_embeddings), axis=0)
    convergence = []
    for month, centroid in author_monthly_centroids:
        sim = 1 - cosine(centroid, ai_centroid)
        convergence.append((month, sim))
    return convergence
```

Convergence toward the AI centroid over time = the author's recent work increasingly resembles AI output.

## 5. UMAP Visualization (src/forensics/analysis/drift.py)

### generate_umap_projection(centroids_by_author: dict[str, list[tuple[str, np.ndarray]]]) -> dict

```python
import umap

def generate_umap_projection(
    centroids_by_author: dict[str, list[tuple[str, np.ndarray]]],
    ai_centroid: np.ndarray | None = None,
) -> dict:
    """2D UMAP projection of monthly centroids, color-coded by time.

    Returns dict with:
        - 'projections': {author: [(month, x, y), ...]}
        - 'ai_projection': (x, y) if ai_centroid provided
    """
    # Collect all centroids into a single matrix
    all_vectors = []
    labels = []
    for author, centroids in centroids_by_author.items():
        for month, vec in centroids:
            all_vectors.append(vec)
            labels.append((author, month))
    if ai_centroid is not None:
        all_vectors.append(ai_centroid)
        labels.append(("AI_BASELINE", "synthetic"))

    reducer = umap.UMAP(n_components=2, random_state=42, metric='cosine')
    projected = reducer.fit_transform(np.stack(all_vectors))
    ...
```

Store the projection data for visualization in notebooks. Don't generate charts here — that's Phase 8 (report).

## 6. DriftScores Assembly

```python
def compute_drift_scores(
    author_id: str,
    baseline_similarity_curve: list[tuple[datetime, float]],
    ai_convergence: list[tuple[str, float]] | None,
    centroid_velocities: list[float],
    intra_variance_trend: list[tuple[str, float]],
) -> DriftScores:
    """Assemble all drift metrics into a single DriftScores model."""
    return DriftScores(
        author_id=author_id,
        baseline_centroid_similarity=baseline_similarity_curve[-1][1],  # most recent
        ai_baseline_similarity=ai_convergence[-1][1] if ai_convergence else 0.0,
        monthly_centroid_velocities=centroid_velocities,
        intra_period_variance_trend=[v for _, v in intra_variance_trend],
    )
```

## 7. CLI Integration

```
uv run forensics analyze --drift              # embedding drift analysis
uv run forensics analyze --drift --author {slug}
uv run forensics analyze --ai-baseline        # generate synthetic AI articles (requires API key)
uv run forensics analyze --ai-baseline --skip-generation  # use existing baseline, just re-embed
```

Add `--openai-key` flag or read from `OPENAI_API_KEY` environment variable for baseline generation.

## 8. Output Storage

- `data/analysis/{author_slug}_drift.json` — serialized DriftScores
- `data/analysis/{author_slug}_centroids.npz` — monthly centroid vectors (numpy compressed)
- `data/analysis/{author_slug}_baseline_curve.json` — similarity decay curve
- `data/analysis/{author_slug}_umap.json` — 2D projection coordinates
- `data/ai_baseline/` — synthetic articles + embeddings

## 9. Tests (tests/test_analysis.py)

Add to existing test file:

- **test_monthly_centroids**: 6 articles across 3 months -> 3 centroids with correct shapes
- **test_centroid_velocity_stationary**: Identical centroids -> velocity ~0
- **test_centroid_velocity_drift**: Linearly shifting centroids -> increasing velocity
- **test_baseline_similarity_stable**: Embeddings near baseline -> similarity ~1.0
- **test_baseline_similarity_drift**: Embeddings progressively further from baseline -> decreasing similarity
- **test_intra_variance_uniform**: Identical embeddings in a month -> variance 0
- **test_ai_convergence_signal**: Centroids moving toward AI centroid -> increasing similarity
- **test_ai_convergence_null**: Random centroids -> no convergence trend
- **test_umap_output_shape**: N centroids -> N rows of 2D coordinates
- **test_drift_scores_assembly**: Verify DriftScores model is correctly populated

## Validation

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_analysis.py -v

# Smoke test:
uv run forensics analyze --drift --author {slug}
cat data/analysis/{slug}_drift.json | python -m json.tool
```

## Handoff

After this phase, both Pipeline A (stylometric change-points) and Pipeline B (embedding drift) are complete. Phase 7 cross-validates the two pipelines, runs formal hypothesis testing with multiple comparison correction, and compares target authors against controls.
