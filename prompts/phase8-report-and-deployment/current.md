# Phase 8: Report Generation & Deployment

Version: 0.3.0
Status: implemented
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 7 (complete AnalysisResult with FindingStrength for all authors)

## Objective

Build the reporting pipeline: create the 10 Jupyter notebooks that form the forensic analysis narrative, configure Quarto book rendering, and set up Cloudflare Pages deployment. After this phase, `uv run forensics report` generates the full report and `make deploy` publishes it.

The key design principle is **narrative-first, code-second** — each notebook reads like a chapter in a legal brief with reproducible evidence attached, not a code dump with occasional comments. Quarto's multi-notebook book project stitches all notebooks into a single paginated HTML/PDF report with auto-numbered figures and a shared table of contents.

## 1. Notebook Layout Rules

### Mandatory Header Cell

Every notebook opens with a Markdown cell containing exactly this structure. This creates the forensic audit trail — reviewers can see exactly what data fed each analytical step:

```markdown
# [Notebook Title]

**Forensic question:** [One sentence stating what this notebook answers]

**Input artifacts:**
- `path/to/input1` — [description]
- `path/to/input2` — [description]

**Output artifacts:**
- `path/to/output1` — [description]

**Run metadata:** (auto-populated by first code cell)
- Config hash: `{config_hash}`
- Corpus hash: `{corpus_hash}`
- Timestamp: `{run_timestamp}`
- Software versions: `{python_version}`, `{key_package_versions}`
```

The first code cell after the header computes and displays the run metadata programmatically:

```python
#| echo: false
from forensics.config import settings
from forensics.utils.provenance import compute_config_hash, compute_corpus_hash
from datetime import datetime, timezone
import sys

config_hash = compute_config_hash(settings)
corpus_hash = compute_corpus_hash(settings.db_path)
run_timestamp = datetime.now(timezone.utc).isoformat()

from IPython.display import Markdown, display
display(Markdown(f"""
| Key | Value |
|-----|-------|
| Config hash | `{config_hash}` |
| Corpus hash | `{corpus_hash}` |
| Run timestamp | `{run_timestamp}` |
| Python | `{sys.version}` |
"""))
```

### Cell Ordering Pattern

Within each notebook, follow this pattern for every analytical section:

1. **Imports + config load** (collapsed in Quarto output with `#| echo: false`)
2. **Narrative Markdown:** explain *what you expect to find and why* — state the hypothesis before showing the result
3. **Code + output:** charts and tables
4. **Interpretation Markdown:** explain *what the output shows* — connect the evidence to the forensic question
5. **Summary cell:** one-sentence finding that feeds the final report

This narrative-first pattern is critical: if a reviewer can't separate the *finding* from the computation that produced it, the report fails under scrutiny.

## 2. The 10-Notebook Structure

Create 10 notebooks in `notebooks/` that import from `src/forensics/` for all logic. Notebooks contain narrative, visualization, and high-level orchestration calls — never raw data processing.

### notebooks/00_power_analysis.ipynb

**Forensic question:** Are our hypotheses, methods, and thresholds defined before we look at the data?

**Purpose:** Pre-registration. This is the single most important notebook for defending against "fishing" accusations. It documents all hypotheses, expected directions of change, significance thresholds, and primary vs. exploratory features *before* analysis runs.

Cells:
1. **Header cell** (mandatory pattern above)
2. **Hypotheses table:** For each feature family, state expected direction of change:
   - AI text → lower TTR, lower hapax ratio
   - AI text → lower perplexity, lower burstiness (if Phase 9 complete)
   - AI text → higher AI marker phrase frequency
   - AI text → convergence toward AI baseline embedding centroid
3. **Expected change-point window:** Post-November 2022 (ChatGPT release) with 6-month ramp allowance
4. **Primary vs. exploratory features:** Classify which features are confirmatory (pre-specified) and which are exploratory (discovered during analysis). Only confirmatory features contribute to `FindingStrength` classification.
5. **Statistical thresholds:**
   - Significance: α = 0.05 after Benjamini-Hochberg correction
   - Minimum effect size: Cohen's d ≥ 0.5
   - Convergence: ≥3 features agreeing within 90-day window for STRONG finding
6. **Sample size justification:** Power analysis for the corpus size — given N articles per author, what effect sizes are detectable at 80% power?
7. **Frozen snapshot:** Write `docs/pre_registration.md` with all of the above, timestamped and hashed. Reference this from the methodology appendix.

### notebooks/01_scraping.ipynb

**Forensic question:** What data was collected, from where, and when?

**Purpose:** Document the data collection methodology and results.

Cells:
1. **Header cell**
2. **Methodology narrative:** Describe the two-step scraping process (WordPress REST API discovery + HTML fetch)
3. **Author summary table:** For each configured author: name, role, total articles, date range (earliest to latest), scrape dates
4. **Article volume over time:** Plotly bar chart of articles per month per author
5. **Data quality summary:** Count of redirects, duplicates, extraction failures, articles excluded and why
6. **Corpus statistics:** Total articles, total words, mean/median article length

### notebooks/02_corpus_audit.ipynb

**Forensic question:** Can we prove the corpus was not modified between collection and analysis?

**Purpose:** Chain of custody verification. This notebook exists specifically so reviewers can verify data integrity independently from the analysis.

Cells:
1. **Header cell**
2. **Corpus hash verification:** Compute corpus hash, compare against stored hash from scrape run. Display pass/fail.
3. **Wayback Machine spot-checks:** For a random sample of 10-20 articles, fetch the Wayback Machine snapshot closest to the `scraped_at` date and compare content hashes. Report match rate.
4. **Content integrity distribution:** Word count distribution of the full corpus — flag any articles with suspiciously low or high counts
5. **Duplicate analysis:** Identify exact and near-duplicate articles (Jaccard similarity > 0.9). Show how many were excluded and why.
6. **Scrape timestamp audit:** Call `audit_scrape_timestamps()` — verify all articles have `scraped_at`, show scrape duration and coverage
7. **Raw archive integrity:** Verify `data/raw/*.tar.gz` files haven't been modified since creation
8. **Audit summary:** One-paragraph chain-of-custody statement suitable for inclusion in the final report

### notebooks/03_exploration.ipynb

**Forensic question:** What does the corpus look like before any analysis — what are the baseline characteristics?

**Purpose:** Corpus characterization. Shows the "before" picture so readers understand the data landscape.

Cells:
1. **Header cell**
2. **Word count distribution:** Histogram of article lengths per author (Plotly)
3. **Publication cadence:** Articles per week heatmap, year × week (Plotly heatmap)
4. **Article length over time:** Scatter plot with rolling average trend line
5. **Day-of-week distribution:** Bar chart showing publication day patterns
6. **Topic distribution:** LDA topic clusters per author with representative keywords
7. **Missing data audit:** Gaps in coverage, months with zero articles
8. **Baseline period identification:** Define the stable baseline period (pre-2020) for each author, with justification

### notebooks/04_feature_analysis.ipynb

**Forensic question:** How do writing features evolve over time, and when do they deviate from baseline?

**Purpose:** Feature extraction results, per-feature time series, baseline characterization.

Cells:
1. **Header cell**
2. **Feature correlation matrix:** Heatmap of Pearson correlations between all numeric features
3. **Baseline characterization:** For each author's baseline period, compute mean ± std for every feature. Present as a styled table.
4. **Per-feature time series:** For the top 10 most discriminative features, show:
   - Raw values as scatter plot
   - 30-day and 90-day rolling averages with confidence bands
   - Annotated with baseline period shading
5. **Feature distribution comparison:** Violin plots comparing baseline vs. recent periods
6. **AI marker frequency timeline:** Dedicated chart for AI marker phrase frequency over time
7. **Probability features timeline** (if Phase 9 complete): Perplexity, burstiness, Binoculars score over time

### notebooks/05_change_point_detection.ipynb

**Forensic question:** Where and when do statistically significant shifts occur in writing features?

**Purpose:** PELT + BOCPD results, cross-feature convergence.

Cells:
1. **Header cell**
2. **Change point summary table:** Feature, date, method, confidence, effect size, direction
3. **Feature heatmap over time:** Rows = features, columns = months, color = z-score relative to baseline. Change points marked with vertical lines.
4. **Convergence windows:** Highlight time periods where 60%+ of features agree on a change. Show a stacked chart of which features triggered.
5. **BOCPD probability plot:** For selected features, show the posterior probability of a change point over time (the gradual shift visualization)
6. **Effect size summary:** Forest plot of Cohen's d for all significant change points

### notebooks/06_embedding_drift.ipynb

**Forensic question:** Does the author's semantic fingerprint shift toward AI-generated text over time?

**Purpose:** Centroid tracking, UMAP visualization, AI baseline comparison, probability feature trajectories.

Cells:
1. **Header cell**
2. **UMAP trajectory plot:** 2D projection of monthly centroids, color-coded by year. Target author trajectory vs. control author trajectories. AI baseline centroid marked with a distinct symbol.
3. **Cosine similarity decay curve:** Author's similarity to their own baseline over time. Annotated with convergence windows from Phase 7.
4. **Centroid velocity timeline:** Monthly centroid movement speed, with spike annotations.
5. **AI convergence chart:** Similarity to AI baseline centroid over time (if AI baseline exists). Dual-axis with baseline similarity decay for comparison.
6. **Intra-period variance trend:** Within-month embedding variance over time.
7. **Perplexity/burstiness time series** (if Phase 9 complete): Mean perplexity, perplexity variance (burstiness), and low-PPL sentence ratio over time. Annotated with change points.
8. **Binoculars score timeline** (if available): Score over time with the 0.9 detection threshold marked.

### notebooks/07_statistical_evidence.ipynb

**Forensic question:** Which changes are statistically significant after controlling for multiple comparisons?

**Purpose:** Hypothesis test results, effect sizes, convergence scoring.

Cells:
1. **Header cell**
2. **Hypothesis test results table:** All tests with raw p-value, corrected p-value, effect size, CI, significant (yes/no). Styled with significant rows highlighted. Separate confirmatory from exploratory features (per notebook 00).
3. **Multiple comparison visualization:** Show the Benjamini-Hochberg step-up procedure graphically (ranked p-values vs. BH threshold line)
4. **Effect size forest plot:** All significant features with Cohen's d and 95% CI
5. **Convergence score summary:** Pipeline A score vs. Pipeline B score (and Pipeline C if available) for each convergence window
6. **FindingStrength classification:** Present the `FindingStrength` verdict (STRONG / MODERATE / WEAK / NONE) with full justification showing which criteria were met

### notebooks/08_control_comparison.ipynb

**Forensic question:** Do control authors show the same patterns, ruling out site-wide or editorial confounds?

**Purpose:** Confound elimination. This is the notebook that separates a defensible finding from a spurious one. If controls show the same drift, the signal is likely editorial/site-wide, not author-specific.

Cells:
1. **Header cell**
2. **Control author selection rationale:** Explain which control authors were selected and why (same outlet, same time period, similar topic coverage, no suspected AI use)
3. **Side-by-side feature comparison:** For each significant feature from notebook 07, show target vs. control time series on the same axes
4. **Control change-point analysis:** Run the same PELT/BOCPD on controls — how many significant change points do they have? At what dates?
5. **Effect size comparison dashboard:** Target vs. each control:
   - Number of significant change points
   - Mean effect size
   - Convergence window count
   - Drift score
6. **Topic drift as covariate:** Did the author's topic mix shift at the same time as their style? Topic drift could explain style changes without AI.
7. **Outlet-wide vs. author-specific signals:** Compare the magnitude of style changes across all tracked authors at the outlet. Is this one author, or a site-wide shift?
8. **Editorial vs. author attribution:** Signal attribution score — what fraction of the observed change is explainable by editorial factors vs. individual authorship changes?
9. **Confound summary:** One-paragraph statement: do controls rule out confounds, or do they weaken the finding?

### notebooks/09_full_report.ipynb

**Forensic question:** What are the conclusions and how strong is the evidence?

**Purpose:** Assembled final report. This is the only notebook non-technical readers see. Contains no raw code cells — only narrative Markdown and charts imported from prior notebooks.

Sections:

1. **Cover / Metadata Block**
   - Title: "AI Writing Forensics: Mediaite Investigation"
   - Run date, config hash, corpus hash (from provenance module)
   - Pipeline version, software versions

2. **Executive Summary**
   - Headline finding (1-2 sentences)
   - Article count, time span
   - Number of significant change points and convergence windows
   - `FindingStrength` verdict with visual indicator (STRONG=red, MODERATE=orange, WEAK=yellow, NONE=green)
   - Key chart: single most compelling visualization
   - Plain-language interpretation:
     - STRONG: "Multiple independent analytical methods strongly indicate a significant change in writing characteristics, not observed in control authors"
     - MODERATE: "Statistical evidence suggests a change in writing characteristics, though fewer independent signals converge"
     - WEAK: "Limited or borderline evidence of change — insufficient for confident conclusions"
     - NONE: "No statistically significant change detected"

3. **Author Profile**
   - Baseline voice characterization from earliest stable period
   - Summary statistics table for baseline features

4. **Productivity Analysis**
   - Publication frequency, word count trends
   - Burst detection results
   - Output volume timeline

5. **Stylometric Timeline**
   - Feature heatmap (from notebook 05)
   - Top 5 most significant feature time series with change points marked
   - Rolling averages with confidence bands

6. **Embedding Drift Analysis**
   - UMAP trajectory (from notebook 06)
   - Cosine similarity decay curve
   - AI convergence (if applicable)

7. **Probability Features** (if Phase 9 complete)
   - Perplexity and burstiness trajectories
   - Binoculars score timeline (if available)

8. **Statistical Evidence Summary**
   - Table of all corrected tests (confirmatory features only)
   - Effect size forest plot
   - Convergence scores across all pipelines

9. **Control Comparison**
   - Key finding: do controls show similar drift?
   - Side-by-side summary
   - Confound assessment

10. **Findings Summary with Confidence Taxonomy**
    - For each author with detected changes, present the `FindingStrength` classification
    - Number of converging features, effect sizes, whether controls showed the same pattern
    - Pre-registration compliance: which hypotheses were confirmed vs. which findings were exploratory?

11. **Methodology Appendix** (formal, expert-witness-grade)
    - **Feature Dictionary:** Complete mathematical definition of every extracted feature, organized by family (lexical, structural, content, productivity, probability, POS patterns). Include formulas, parameter choices, and references to source literature.
    - **Statistical Test Selection:** Rationale for each test (Welch's t, Mann-Whitney U, KS), assumptions, when each is appropriate, and why all three are used.
    - **Multiple Comparison Correction:** Explanation of Benjamini-Hochberg procedure and why it was chosen over Bonferroni.
    - **Effect Size Interpretation:** Cohen's d thresholds, minimum reportable effect size, and justification.
    - **Corpus Statistics:** Total articles, date range, word count distribution per author, articles excluded and why.
    - **Parameter Choices:** All configurable parameters (PELT penalty, convergence window, bootstrap samples, effect size threshold) with justification.
    - **Software Versions:** Python version, all package versions (from `uv pip freeze`), embedding model SHA, reference LM version (if Phase 9 completed).
    - **Reproducibility:** Instructions for re-running the full pipeline from scratch, expected runtime, hardware requirements.
    - **Limitations:** Explicitly acknowledge what the analysis cannot prove — it cannot distinguish "author used AI" from "editor replaced author's text with AI-generated content," it cannot identify which specific LLM was used, it cannot account for all possible confounds (ghostwriters, style coaching, personal life changes affecting writing).

12. **Data Provenance**
    - Scrape dates and method
    - Article counts per author
    - Chain-of-custody statement (from notebook 02)
    - Wayback validation results
    - Pre-registration reference (from notebook 00)

## 3. Plotly Chart Theme

All charts use a consistent theme. Create a helper module:

### src/forensics/utils/charts.py (new file)

```python
import plotly.graph_objects as go
import plotly.io as pio

FORENSICS_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        template="plotly_white",
        font=dict(family="Inter, system-ui, sans-serif", size=12),
        title=dict(font=dict(size=16)),
        colorway=["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                   "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"],
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
)

pio.templates["forensics"] = FORENSICS_TEMPLATE
pio.templates.default = "forensics"


def apply_change_point_annotations(fig: go.Figure, change_points: list, ...) -> go.Figure:
    """Add vertical lines and annotations for detected change points."""
    ...

def apply_baseline_shading(fig: go.Figure, start: date, end: date) -> go.Figure:
    """Add shaded rectangle for the baseline period."""
    ...
```

### src/forensics/utils/provenance.py (new file)

```python
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


def compute_config_hash(settings) -> str:
    """Deterministic hash of the pipeline configuration."""
    config_str = json.dumps(settings.model_dump(), sort_keys=True, default=str)
    return hashlib.sha256(config_str.encode()).hexdigest()[:12]


def compute_corpus_hash(db_path: Path) -> str:
    """Hash all content_hash values from the articles table."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    hashes = conn.execute(
        "SELECT content_hash FROM articles ORDER BY id"
    ).fetchall()
    conn.close()
    combined = "|".join(h[0] for h in hashes if h[0])
    return hashlib.sha256(combined.encode()).hexdigest()[:12]


def get_run_metadata(settings) -> dict:
    """Generate run metadata dict for notebook headers."""
    return {
        "config_hash": compute_config_hash(settings),
        "corpus_hash": compute_corpus_hash(settings.db_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python_version": f"{__import__('sys').version}",
    }
```

## 4. Quarto Configuration

### quarto.yml (project root)

```yaml
project:
  type: book
  output-dir: data/reports

book:
  title: "AI Writing Forensics: Mediaite Investigation"
  author: "Abstract Data LLC"
  date: today
  chapters:
    - index.qmd
    - notebooks/00_power_analysis.ipynb
    - part: "Data Collection & Audit"
      chapters:
        - notebooks/01_scraping.ipynb
        - notebooks/02_corpus_audit.ipynb
    - part: "Exploration & Features"
      chapters:
        - notebooks/03_exploration.ipynb
        - notebooks/04_feature_analysis.ipynb
    - part: "Analysis"
      chapters:
        - notebooks/05_change_point_detection.ipynb
        - notebooks/06_embedding_drift.ipynb
    - part: "Evidence & Conclusions"
      chapters:
        - notebooks/07_statistical_evidence.ipynb
        - notebooks/08_control_comparison.ipynb
        - notebooks/09_full_report.ipynb

execute:
  freeze: auto
  echo: false
  warning: false

format:
  html:
    theme: cosmo
    toc: true
    toc-depth: 3
    number-sections: true
    code-fold: true
    code-summary: "Show code"
  pdf:
    toc: true
    number-sections: true
    documentclass: report
```

### index.qmd (project root)

```markdown
---
title: "AI Writing Forensics: Mediaite Investigation"
---

This report presents a forensic analysis of writing style evolution at Mediaite.com,
investigating potential AI writing adoption through stylometric analysis, embedding drift
detection, and probability-based language model scoring.

Navigate to **Chapter 1: Pre-Registration** to begin, or jump directly to
**Chapter 10: Full Report** for the executive summary and conclusions.
```

The `type: book` format renders all notebooks as numbered chapters with a shared sidebar table of contents. The `execute: freeze: auto` setting ensures Quarto only re-runs notebooks whose source has changed — critical for reproducibility without re-running expensive scraping or model inference on every render.

## 5. CLI Integration

```
uv run forensics report                   # render all notebooks
uv run forensics report --notebook 05     # render specific notebook
uv run forensics report --format html     # HTML only
uv run forensics report --format pdf      # PDF only
uv run forensics report --verify          # verify corpus hash matches before rendering
```

The `report` command should:
1. Verify `data/analysis/` contains results for all configured authors
2. Optionally verify corpus hash matches the stored hash (chain of custody check)
3. Execute notebooks via `quarto render`
4. Output to `data/reports/` (rendered HTML/PDF book)

## 6. Makefile

Create or update `Makefile` at project root:

```makefile
.PHONY: scrape extract analyze report all deploy clean

scrape:
	uv run forensics scrape

extract:
	uv run forensics extract

analyze:
	uv run forensics analyze

report:
	uv run forensics report

all:
	uv run forensics all

quarto-build:
	quarto render --output-dir data/reports

deploy: quarto-build
	npx wrangler pages deploy data/reports --project-name=ai-writing-forensics

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest tests/ -v

clean:
	rm -rf data/features/*.parquet
	rm -rf data/embeddings/*.npy
	rm -rf data/analysis/*.json
	rm -rf data/reports/*
```

## 7. Git LFS Setup

Create `.gitattributes`:

```
data/raw/**/*.tar.gz filter=lfs diff=lfs merge=lfs -text
data/articles.db filter=lfs diff=lfs merge=lfs -text
data/features/**/*.parquet filter=lfs diff=lfs merge=lfs -text
data/embeddings/**/*.npy filter=lfs diff=lfs merge=lfs -text
```

## 8. Cloudflare Pages Deployment (Optional)

### CI/CD via GitHub Actions

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy Report
on:
  push:
    branches: [main]
    paths: [notebooks/**, src/**]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true
      - uses: quarto-dev/quarto-actions/setup@v2
      - run: quarto render --output-dir data/reports
      - uses: cloudflare/pages-action@v1
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          accountId: ${{ secrets.CF_ACCOUNT_ID }}
          projectName: ai-writing-forensics
          directory: data/reports
```

## 9. Tests

### tests/test_report.py (new file)

- **test_chart_theme_loads**: Verify forensics Plotly template is registered
- **test_change_point_annotations**: Verify annotations are added to a figure
- **test_notebook_imports**: For each of the 10 notebooks, verify the imports resolve (no missing modules)
- **test_report_config_validation**: Verify ReportConfig accepts valid configs and rejects invalid ones
- **test_quarto_config_exists**: Verify quarto.yml is valid YAML with required fields and lists all 10 notebooks
- **test_provenance_hash_deterministic**: Same config/corpus → same hash
- **test_provenance_hash_changes**: Modified config → different hash
- **test_index_qmd_exists**: Verify index.qmd exists and references the report

## Validation

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v

# Generate report (requires all prior phases to have run):
uv run forensics report
ls -la data/reports/

# Quarto build (requires quarto installed):
make quarto-build

# Verify all 10 notebooks are listed in quarto.yml:
grep -c ".ipynb" quarto.yml  # should return 10
```

## Handoff

After this phase, the entire pipeline is complete:

```
uv run forensics all    # scrape -> extract -> analyze -> report
make deploy             # publish to Cloudflare Pages
```

The report is a Quarto book with 10 numbered chapters. The pre-registration notebook (00) proves hypotheses were formed before analysis. The corpus audit notebook (02) establishes chain of custody. The control comparison notebook (08) eliminates confounds. The final report notebook (09) is the only chapter non-technical readers need — it contains no code, only narrative and key charts.

The report is reproducible — anyone cloning the repo with LFS can re-run any stage. `execute: freeze: auto` ensures unchanged notebooks aren't re-executed unnecessarily.
