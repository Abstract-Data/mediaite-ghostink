# Pre-Registration Snapshot (Seed)

This file is overwritten when you execute `notebooks/00_power_analysis.ipynb`, which
freezes hypotheses, thresholds, and primary vs exploratory feature classifications.

Until that notebook is run, treat this document as a placeholder that satisfies the
repository layout expected by the Quarto methodology appendix.

**Forensic question:** Were hypotheses, methods, and thresholds defined before viewing outcomes?

**Statistical thresholds (default):**

- Multiple comparisons: Benjamini–Hochberg, α = 0.05
- Minimum effect size for emphasis: Cohen's d ≥ 0.5
- Convergence heuristic: ≥ 3 independent features within a 90-day window for STRONG narrative support

**Expected directional hypotheses (confirmatory families):**

- Lexical richness: AI-like text tends toward lower type–token ratio and lower hapax ratio.
- Marker language: Higher frequency of templated / assistant-like phrases where measured.
- Embeddings: Drift toward a pre-specified AI baseline centroid when that baseline exists.

**Exploratory analyses:** Any feature not listed as confirmatory in notebook 00 is exploratory
and is reported separately from `FindingStrength` classification inputs.

Re-run notebook 00 after any change to `config.toml` or analysis defaults so this file
remains aligned with the executed configuration.
