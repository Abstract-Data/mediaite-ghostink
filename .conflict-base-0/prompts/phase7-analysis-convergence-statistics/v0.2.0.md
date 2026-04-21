# Phase 7: Analysis — Convergence Scoring, Statistical Rigor & Control Comparison

Version: 0.2.0
Status: pending
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 5 (change-points), Phase 6 (drift scores), Phase 9 (probability features, optional)

## Objective

Cross-validate Pipeline A and Pipeline B findings, run formal hypothesis tests with multiple comparison correction, compare target authors against controls, and produce the final `AnalysisResult` for each author. This is the evidential synthesis layer. After this phase, `uv run forensics analyze` produces a complete, statistically defensible analysis.

## 1. Cross-Pipeline Convergence Scoring (src/forensics/analysis/convergence.py)

### compute_convergence_scores(change_points: list[ChangePoint], drift_scores: DriftScores, window_days: int = 90) -> list[ConvergenceWindow]

The key insight: when both Pipeline A (stylometric features) and Pipeline B (embedding drift) independently identify changes in the same time window, the combined evidence is much stronger than either alone.

```python
def compute_convergence_scores(
    change_points: list[ChangePoint],
    centroid_velocities: list[tuple[str, float]],
    baseline_similarity_curve: list[tuple[datetime, float]],
    window_days: int = 90,
    min_feature_ratio: float = 0.6,
) -> list[ConvergenceWindow]:
    """Quantify agreement between Pipeline A and Pipeline B.

    For each 90-day window:
    1. Count how many stylometric features detected a change point (Pipeline A)
    2. Check if embedding drift accelerated in the same window (Pipeline B)
    3. Score the convergence

    Args:
        change_points: All detected change points from Pipeline A
        centroid_velocities: Monthly centroid movement speeds from Pipeline B
        baseline_similarity_curve: Similarity decay from Pipeline B
        window_days: Width of comparison windows
        min_feature_ratio: Minimum fraction of features that must agree

    Returns:
        List of ConvergenceWindow objects for windows with significant agreement
    """
```

### Pipeline A Score Calculation

For each window:
- `features_converging` = list of feature names with change points in this window
- `convergence_ratio` = len(features_converging) / total_feature_count
- `pipeline_a_score` = weighted average of effect sizes (Cohen's d) across converging features, where features with higher confidence get more weight

### Pipeline B Score Calculation

For each window:
- Check if centroid velocity peaked in this window (velocity > 2 std above mean)
- Check if baseline similarity dropped significantly in this window
- Check if AI convergence increased (if AI baseline exists)
- `pipeline_b_score` = normalized composite of these three signals (0-1 scale)

### Combined Convergence

A `ConvergenceWindow` is only created when:
- `convergence_ratio >= min_feature_ratio` (60%+ of features agree), OR
- `pipeline_a_score > 0.5` AND `pipeline_b_score > 0.5` (both pipelines show strong signal even if fewer features agree)

## 2. Hypothesis Testing (src/forensics/analysis/statistics.py)

### Formal tests for each candidate change point:

```python
from scipy import stats

def run_hypothesis_tests(
    feature_values: list[float],
    breakpoint_idx: int,
    feature_name: str,
    author_id: str,
) -> list[HypothesisTest]:
    """Run multiple statistical tests at a candidate breakpoint."""
    pre = feature_values[:breakpoint_idx]
    post = feature_values[breakpoint_idx:]

    tests = []

    # 1. Welch's t-test (unequal variance)
    t_stat, p_value = stats.ttest_ind(pre, post, equal_var=False)
    d = cohens_d(pre, post)
    ci = bootstrap_ci(pre, post)
    tests.append(HypothesisTest(
        test_name=f"welch_t_{feature_name}",
        feature_name=feature_name,
        author_id=author_id,
        raw_p_value=p_value,
        corrected_p_value=p_value,  # corrected later
        effect_size_cohens_d=d,
        confidence_interval_95=ci,
        significant=False,  # set after correction
    ))

    # 2. Mann-Whitney U (non-parametric)
    u_stat, p_value = stats.mannwhitneyu(pre, post, alternative='two-sided')
    tests.append(HypothesisTest(
        test_name=f"mann_whitney_{feature_name}",
        ...
    ))

    # 3. Kolmogorov-Smirnov (distribution comparison)
    ks_stat, p_value = stats.ks_2samp(pre, post)
    tests.append(HypothesisTest(
        test_name=f"ks_test_{feature_name}",
        ...
    ))

    return tests
```

### Cohen's d

```python
def cohens_d(group1: list[float], group2: list[float]) -> float:
    """Compute Cohen's d effect size."""
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    return (np.mean(group2) - np.mean(group1)) / pooled_std if pooled_std > 0 else 0.0
```

Interpretation: |d| < 0.2 = negligible, 0.2-0.5 = small, 0.5-0.8 = medium, > 0.8 = large.

### Bootstrapped Confidence Intervals

```python
def bootstrap_ci(
    group1: list[float],
    group2: list[float],
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """95% bootstrapped CI for the difference in means."""
    diffs = []
    rng = np.random.default_rng(42)
    for _ in range(n_bootstrap):
        sample1 = rng.choice(group1, size=len(group1), replace=True)
        sample2 = rng.choice(group2, size=len(group2), replace=True)
        diffs.append(np.mean(sample2) - np.mean(sample1))
    return (np.percentile(diffs, 100 * alpha / 2),
            np.percentile(diffs, 100 * (1 - alpha / 2)))
```

### Multiple Comparison Correction

```python
def apply_correction(
    tests: list[HypothesisTest],
    method: str = "benjamini_hochberg",
    alpha: float = 0.05,
) -> list[HypothesisTest]:
    """Apply multiple comparison correction across all tests."""
    p_values = [t.raw_p_value for t in tests]

    if method == "bonferroni":
        corrected = [min(p * len(p_values), 1.0) for p in p_values]
    elif method == "benjamini_hochberg":
        # Benjamini-Hochberg procedure
        n = len(p_values)
        ranked = sorted(enumerate(p_values), key=lambda x: x[1])
        corrected = [0.0] * n
        for rank, (idx, p) in enumerate(ranked, 1):
            corrected[idx] = p * n / rank
        # Enforce monotonicity
        for i in range(n - 2, -1, -1):
            corrected[ranked[i][0]] = min(
                corrected[ranked[i][0]],
                corrected[ranked[i + 1][0]] if i + 1 < n else 1.0
            )
        corrected = [min(c, 1.0) for c in corrected]

    for test, cp in zip(tests, corrected):
        test.corrected_p_value = cp
        test.significant = cp < alpha

    return tests
```

## 3. Control Author Comparison (src/forensics/analysis/comparison.py)

### compare_target_to_controls(target_result: AnalysisResult, control_results: list[AnalysisResult]) -> dict

Run the identical analysis pipeline on N control authors. The key question: do controls show similar drift? If yes, the signal is likely editorial (outlet-wide). If no, it's author-specific.

```python
def compare_target_to_controls(
    target_id: str,
    control_ids: list[str],
    features_dir: Path,
    db_path: Path,
) -> dict:
    """Formal comparison between target and control authors.

    For each feature, for each time period:
    1. Two-sample t-test between target and control distributions
    2. Compute effect size (target drift vs. control drift)
    3. Check if control authors show similar change-point patterns

    Returns:
        {
            'feature_comparisons': {feature: {period: {t_stat, p_value, target_mean, control_mean}}},
            'control_change_points': {control_id: [ChangePoint, ...]},
            'control_drift_scores': {control_id: DriftScores},
            'editorial_vs_author_signal': float,  # 0 = all editorial, 1 = all author-specific
        }
    """
```

### Editorial vs. Author Signal

```python
def compute_signal_attribution(
    target_change_windows: list[ConvergenceWindow],
    control_change_windows: dict[str, list[ConvergenceWindow]],
) -> float:
    """Score whether detected changes are author-specific or outlet-wide.

    0.0 = all controls show same changes (editorial effect)
    1.0 = no controls show similar changes (author-specific)
    """
    # For each target convergence window:
    #   Count how many controls also have convergence in the same time range
    #   If 0 controls agree -> author-specific
    #   If all controls agree -> editorial effect
    # Return weighted average across all windows
```

## 3a. Effect Size Thresholds & Finding Classification

### Minimum Effect Size Filter

Add an `effect_size_threshold` parameter to `AnalysisConfig` (default: `0.5`, corresponding to Cohen's d medium effect). HypothesisTest results must pass BOTH the corrected p-value threshold AND the effect size threshold to be included as significant findings in the final report.

```python
# In AnalysisConfig (pydantic-settings)
effect_size_threshold: float = 0.5  # minimum |Cohen's d| for reportable findings
```

After applying multiple comparison correction, add a second filter:

```python
def filter_by_effect_size(
    tests: list[HypothesisTest],
    min_d: float = 0.5,
) -> list[HypothesisTest]:
    """Filter tests by both statistical significance and practical significance."""
    for test in tests:
        test.significant = (
            test.corrected_p_value < alpha
            and abs(test.effect_size_cohens_d) >= min_d
        )
    return tests
```

### FindingStrength Classification

Add a `FindingStrength` enum to `models/report.py` (or `models/__init__.py`) that translates raw statistical results into human-readable confidence levels:

```python
from enum import Enum

class FindingStrength(str, Enum):
    STRONG   = "strong"    # ≥3 independent features, p<0.01, |d|≥0.8, control authors negative
    MODERATE = "moderate"  # ≥2 features, p<0.05, |d|≥0.5
    WEAK     = "weak"      # single feature or borderline statistics
    NONE     = "none"      # no significant signal detected


def classify_finding_strength(
    convergence_window: ConvergenceWindow,
    hypothesis_tests: list[HypothesisTest],
    control_comparison: dict,
) -> FindingStrength:
    """Classify the overall strength of a finding for a convergence window.

    Criteria:
    - STRONG: ≥3 features with corrected p<0.01 AND |d|≥0.8 AND control authors
      do NOT show the same pattern (editorial_vs_author_signal > 0.7)
    - MODERATE: ≥2 features with corrected p<0.05 AND |d|≥0.5
    - WEAK: 1 feature significant, or multiple features with small effect sizes
    - NONE: no significant results after correction
    """
    significant_tests = [t for t in hypothesis_tests if t.significant]
    strong_tests = [
        t for t in significant_tests
        if t.corrected_p_value < 0.01 and abs(t.effect_size_cohens_d) >= 0.8
    ]

    controls_negative = control_comparison.get("editorial_vs_author_signal", 0) > 0.7

    if len(strong_tests) >= 3 and controls_negative:
        return FindingStrength.STRONG
    elif len(significant_tests) >= 2:
        return FindingStrength.MODERATE
    elif len(significant_tests) >= 1:
        return FindingStrength.WEAK
    else:
        return FindingStrength.NONE
```

### Pipeline C Integration (Probability Features)

If Phase 9 (probability features) has been completed, the convergence framework gains a third independent pipeline:

- **Pipeline A** — Stylometric change-point detection (existing)
- **Pipeline B** — Embedding drift analysis (existing)
- **Pipeline C** — Perplexity/burstiness trajectory analysis (new, from Phase 9)

The convergence scoring in Section 1 should be extended to incorporate Pipeline C when available:

```python
# In compute_convergence_scores, add:
if probability_features_available:
    # Check if perplexity dropped significantly in this window
    # Check if burstiness decreased (became more uniform)
    # Check if Binoculars score shifted
    pipeline_c_score = compute_probability_pipeline_score(window, prob_features)
    # Combined convergence now requires agreement across A+B+C for STRONG rating
```

When Pipeline C data is present, upgrade the FindingStrength criteria: STRONG requires convergence across all three pipelines, not just A+B.

### Tests to add

- **test_effect_size_filter**: Test with d=0.3 (below threshold) -> not significant even if p<0.05
- **test_finding_strength_strong**: 3 features, p<0.01, d>0.8, controls negative -> STRONG
- **test_finding_strength_moderate**: 2 features, p<0.05, d>0.5 -> MODERATE
- **test_finding_strength_weak**: 1 feature only -> WEAK
- **test_finding_strength_none**: No significant results -> NONE
- **test_pipeline_c_integration**: When probability features present, convergence includes them

## 4. Final AnalysisResult Assembly

```python
def assemble_analysis_result(
    author_id: str,
    change_points: list[ChangePoint],
    convergence_windows: list[ConvergenceWindow],
    drift_scores: DriftScores,
    hypothesis_tests: list[HypothesisTest],
    config: AnalysisConfig,
) -> AnalysisResult:
    """Assemble the complete analysis result for one author."""
    import hashlib, json

    config_hash = hashlib.sha256(
        json.dumps(config.model_dump(), sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    return AnalysisResult(
        author_id=author_id,
        run_id=str(uuid4()),
        run_timestamp=datetime.utcnow(),
        config_hash=config_hash,
        change_points=change_points,
        convergence_windows=convergence_windows,
        drift_scores=drift_scores,
        hypothesis_tests=hypothesis_tests,
    )
```

## 5. Full Analysis Orchestrator (src/forensics/analysis/__init__.py or pipeline integration)

```python
async def run_full_analysis(
    db_path: Path,
    features_dir: Path,
    embeddings_dir: Path,
    config: ForensicsSettings,
) -> dict[str, AnalysisResult]:
    """Run complete analysis for all configured authors.

    1. For each target author:
       a. Load features from Parquet
       b. Run change-point detection (Phase 5)
       c. Run embedding drift analysis (Phase 6)
       d. Run hypothesis tests
       e. Apply multiple comparison correction
    2. For each control author: same pipeline
    3. Cross-validate targets against controls
    4. Compute convergence scores
    5. Assemble AnalysisResult per author
    6. Store results
    """
```

## 6. CLI Integration

```
uv run forensics analyze                          # full analysis (all phases)
uv run forensics analyze --changepoint            # Phase 5 only
uv run forensics analyze --drift                  # Phase 6 only
uv run forensics analyze --convergence            # this phase: cross-validation + stats
uv run forensics analyze --compare                # control comparison only
uv run forensics analyze --author {slug}          # single author
```

## 7. Output Storage

- `data/analysis/{author_slug}_result.json` — full serialized AnalysisResult
- `data/analysis/{author_slug}_hypothesis_tests.json` — all test results with corrected p-values
- `data/analysis/comparison_report.json` — target vs. control comparison
- `data/analysis/run_metadata.json` — updated with final run info

Also log the `analysis_runs` table in SQLite with run metadata.

## 8. Tests (tests/test_analysis.py)

Add to existing test file:

- **test_convergence_scoring**: 4/5 features with change points in same window -> ConvergenceWindow created
- **test_convergence_below_threshold**: 2/5 features agree -> no ConvergenceWindow
- **test_welch_t_significant**: Known different distributions -> p < 0.05
- **test_welch_t_null**: Same distribution -> p > 0.05
- **test_cohens_d_large**: Large effect -> d > 0.8
- **test_cohens_d_negligible**: Same distribution -> d near 0
- **test_bootstrap_ci_contains_true_diff**: Known difference falls within CI
- **test_bonferroni_correction**: 100 tests at alpha=0.05 -> corrected threshold = 0.0005
- **test_benjamini_hochberg**: Known p-values -> correct rejection set
- **test_control_comparison_editorial**: Target + all controls drift -> editorial signal high
- **test_control_comparison_author_specific**: Target drifts, controls don't -> author signal high
- **test_analysis_result_serialization**: AnalysisResult round-trips through JSON
- **test_full_analysis_integration**: End-to-end with synthetic data

## Validation

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_analysis.py -v

# Full analysis run:
uv run forensics analyze
ls -la data/analysis/
cat data/analysis/{slug}_result.json | python -m json.tool | head -50
```

## Handoff

After this phase, the complete analysis is done. Every configured author has a full `AnalysisResult` with change points, convergence windows, drift scores, corrected hypothesis tests, and control comparison. Phase 8 generates the report.
