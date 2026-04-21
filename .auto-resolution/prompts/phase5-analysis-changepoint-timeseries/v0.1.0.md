# Phase 5: Analysis — Change-Point Detection & Time-Series Analysis

Version: 0.1.0
Status: pending
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 4 (feature vectors in Parquet, embeddings in numpy)

## Objective

Implement Pipeline A (Statistical Stylometry) analysis: change-point detection across all feature time series and time-series decomposition. After this phase, `uv run forensics analyze --changepoint` identifies when each author's writing features shifted and quantifies the magnitude of each shift.

## 1. Change-Point Detection (src/forensics/analysis/changepoint.py)

### PELT (Pruned Exact Linear Time)

Using the `ruptures` library:

```python
import ruptures as rpt

def detect_pelt(signal: np.ndarray, pen: float = 3.0) -> list[int]:
    """Run PELT change-point detection on a 1D signal.

    Args:
        signal: 1D array of feature values over time
        pen: Penalty value (controls sensitivity — higher = fewer breakpoints)

    Returns:
        List of breakpoint indices
    """
    algo = rpt.Pelt(model="rbf", min_size=5).fit(signal)
    breakpoints = algo.predict(pen=pen)
    return breakpoints[:-1]  # ruptures includes the signal length as final element
```

Run PELT independently on each numeric feature time series for each author. Features to process: `ttr`, `mattr`, `hapax_ratio`, `yules_k`, `simpsons_d`, `ai_marker_frequency`, `sent_length_mean`, `sent_length_std`, `sent_length_skewness`, `subordinate_clause_depth`, `conjunction_freq`, `passive_voice_ratio`, `paragraph_length_variance`, `flesch_kincaid`, `coleman_liau`, `gunning_fog`, `bigram_entropy`, `trigram_entropy`, `self_similarity_30d`, `self_similarity_90d`, `formula_opening_score`, `first_person_ratio`, `hedging_frequency`.

### Bayesian Online Change Point Detection (BOCPD)

Implement from scratch using scipy (not available in ruptures):

```python
from scipy.stats import norm
from scipy.special import logsumexp

def detect_bocpd(
    signal: np.ndarray,
    hazard_rate: float = 1/250,
    threshold: float = 0.5,
) -> list[tuple[int, float]]:
    """Bayesian Online Change Point Detection.

    Returns list of (index, probability) for detected change points
    where probability exceeds threshold.
    """
    # Implement the Adams & MacKay (2007) algorithm:
    # 1. Initialize run length distribution
    # 2. For each observation:
    #    a. Compute growth probabilities (run continues)
    #    b. Compute changepoint probability (new run starts)
    #    c. Update sufficient statistics
    #    d. Normalize run length distribution
    # 3. Extract change points where P(run_length=0) > threshold
    ...
```

Key implementation details:
- Use a Gaussian observation model with conjugate Normal-Inverse-Gamma prior
- `hazard_rate` = 1/expected_run_length (1/250 for ~250 articles between changes)
- Return probability distributions, not just point estimates
- Better suited for detecting gradual shifts than PELT

### Building ChangePoint Models

For each detected breakpoint from either method:

1. Map the breakpoint index back to a timestamp using the article dates
2. Compute Cohen's d effect size: `d = (mean_after - mean_before) / pooled_std`
3. Determine direction: "increase" or "decrease" based on sign of mean shift
4. Compute confidence as: PELT uses the penalty-adjusted cost reduction; BOCPD uses the posterior probability
5. Create a `ChangePoint` model instance

### Cross-Feature Convergence (preliminary)

After running both methods on all features:

```python
def find_convergence_windows(
    change_points: list[ChangePoint],
    window_days: int = 90,
    min_features: float = 0.6,
) -> list[ConvergenceWindow]:
    """Identify time windows where 60%+ of features agree on a change point."""
```

- Bin all detected change points into 90-day windows
- For each window, count how many distinct features detected a change point
- If `features_converging / total_features >= min_features`, flag as a convergence window
- This is the explainability layer — it says WHAT changed and WHEN

## 2. Time-Series Analysis (src/forensics/analysis/timeseries.py)

### Rolling Window Statistics

```python
def compute_rolling_stats(
    timestamps: list[datetime],
    values: list[float],
    windows: list[int] = [30, 90],
) -> dict[int, dict]:
    """Compute rolling mean, std, and 95% confidence bands for each window size."""
```

Use Polars for efficient rolling computations:
```python
df = pl.DataFrame({"timestamp": timestamps, "value": values})
df = df.sort("timestamp")
for w in windows:
    df = df.with_columns([
        pl.col("value").rolling_mean(window_size=w).alias(f"rolling_{w}d_mean"),
        pl.col("value").rolling_std(window_size=w).alias(f"rolling_{w}d_std"),
    ])
```

### STL Decomposition

```python
from scipy.signal import detrend
import numpy as np

def stl_decompose(
    timestamps: list[datetime],
    values: list[float],
    period: int = 30,
) -> dict:
    """Separate trend from seasonal patterns.

    Returns dict with 'trend', 'seasonal', 'residual' arrays.
    """
```

Use `statsmodels.tsa.seasonal.STL` if available, otherwise implement a simple decomposition:
- Trend: rolling mean with period-length window
- Seasonal: average residual per position in cycle
- Residual: original - trend - seasonal

This separates genuine drift from seasonal patterns (election cycles, summer slowdowns, beat-driven variation).

### Chow Test (Structural Break)

```python
from scipy.stats import f as f_dist

def chow_test(
    values: list[float],
    breakpoint_idx: int,
) -> tuple[float, float]:
    """Formal structural break test at a candidate change point.

    Returns (F-statistic, p-value).
    """
    # Split data at breakpoint
    # Fit linear model to each segment and to pooled data
    # F = ((RSS_pooled - RSS_1 - RSS_2) / k) / ((RSS_1 + RSS_2) / (n - 2k))
    # where k = number of parameters (2 for intercept + slope)
```

Run at each candidate change point identified by PELT/BOCPD to get formal p-values.

### CUSUM Test

```python
def cusum_test(
    values: list[float],
    threshold: float = 4.0,
) -> list[tuple[int, float]]:
    """Cumulative sum test for detecting persistent shifts.

    Returns list of (index, cusum_value) where threshold is exceeded.
    Distinguishes persistent shifts from temporary fluctuations.
    """
    mean = np.mean(values)
    cusum_pos = np.zeros(len(values))
    cusum_neg = np.zeros(len(values))
    for i in range(1, len(values)):
        cusum_pos[i] = max(0, cusum_pos[i-1] + values[i] - mean - threshold/2)
        cusum_neg[i] = max(0, cusum_neg[i-1] - values[i] + mean - threshold/2)
    ...
```

## 3. Burst Detection (deferred from Phase 4)

```python
def detect_bursts(
    timestamps: list[datetime],
    s: float = 2.0,
) -> list[tuple[datetime, datetime, int]]:
    """Kleinberg's burst detection on publication timestamps.

    Returns list of (start, end, burst_level) tuples.
    """
```

Implement Kleinberg's (2003) automaton-based burst detection algorithm, or use a simplified version:
- Model inter-arrival times as exponential distributions
- Detect periods where arrival rate significantly exceeds baseline
- Return burst windows with intensity levels

## 4. DuckDB Analytical Queries (src/forensics/storage/duckdb_queries.py)

Implement key analytical queries that span SQLite + Parquet:

```python
import duckdb

def get_rolling_feature_comparison(
    db_path: Path,
    features_dir: Path,
    feature_name: str,
    window: int = 90,
) -> pl.DataFrame:
    """Cross-author rolling feature comparison."""
    con = duckdb.connect()
    con.execute(f"ATTACH '{db_path}' AS articles_db (TYPE sqlite)")
    result = con.execute(f"""
        SELECT
            a.name AS author,
            a.role,
            f.timestamp,
            AVG(f.{feature_name}) OVER (
                PARTITION BY f.author_id
                ORDER BY f.timestamp
                ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW
            ) AS rolling_avg
        FROM read_parquet('{features_dir}/*.parquet') f
        JOIN articles_db.authors a ON f.author_id = a.id
        ORDER BY f.timestamp
    """).pl()
    con.close()
    return result

def get_monthly_feature_stats(
    features_dir: Path,
    feature_name: str,
) -> pl.DataFrame:
    """Monthly aggregation with mean and std for any feature."""
    ...

def get_ai_marker_spike_detection(features_dir: Path) -> pl.DataFrame:
    """Detect months with abnormal AI marker frequency."""
    ...
```

## 5. CLI Integration

Update `analyze` command:

```
uv run forensics analyze                      # full analysis pipeline
uv run forensics analyze --changepoint        # change-point detection only
uv run forensics analyze --timeseries         # time-series decomposition only
uv run forensics analyze --author {slug}      # analyze single author
```

## 6. Output Storage

Analysis results are stored as:
- `data/analysis/{author_slug}_changepoints.json` — serialized ChangePoint list
- `data/analysis/{author_slug}_convergence.json` — ConvergenceWindow list
- `data/analysis/{author_slug}_timeseries.parquet` — rolling stats, STL components
- `data/analysis/run_metadata.json` — AnalysisResult metadata (run_id, timestamp, config_hash)

## 7. Tests (tests/test_analysis.py)

- **test_pelt_synthetic**: Create synthetic signal with known breakpoint (e.g., mean shift at index 100) -> PELT detects it within +-5 indices
- **test_bocpd_gradual_shift**: Synthetic signal with gradual mean shift -> BOCPD assigns high probability to change region
- **test_pelt_no_change**: Stationary signal -> no breakpoints detected
- **test_cohens_d_calculation**: Known pre/post distributions -> correct effect size
- **test_convergence_window**: 5 features with change points within 30 days of each other -> flagged as convergence
- **test_chow_test_significant**: Signal with clear break -> p-value < 0.05
- **test_chow_test_null**: Stationary signal -> p-value > 0.05
- **test_cusum_persistent_shift**: Step function signal -> CUSUM detects the shift
- **test_rolling_stats_output_shape**: Verify rolling computations produce correct number of rows
- **test_stl_decomposition**: Synthetic seasonal + trend signal -> components separate correctly

## Validation

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_analysis.py -v

# Smoke test:
uv run forensics analyze --changepoint --author {slug}
cat data/analysis/{slug}_changepoints.json | python -m json.tool | head -20
```

## Handoff

After this phase, Pipeline A is complete. Every configured author has change-point detections across ~23 features, convergence windows, time-series decompositions, and formal statistical tests. Phase 6 adds Pipeline B (embedding drift) and AI baseline comparison.
