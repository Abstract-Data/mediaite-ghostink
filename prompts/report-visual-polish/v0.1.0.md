# Report Visual Polish — Quarto PDF Production Pass

Version: 0.1.0
Status: active
Last Updated: 2026-04-24
Model: claude-opus-4-7

---

## Mission

Take the existing Quarto-rendered bound PDF report (`AI Writing Forensics: Mediaite Investigation`, currently emitted to `data/reports/`) from "Quarto default LaTeX" presentation to "consulting deliverable" presentation. Fix typography, table rendering, chart consistency, page layout, and front-matter so the document reads as a finished forensic deliverable rather than a notebook export. Do not touch analysis content, stage boundaries, or pipeline code.

This is a production / styling pass on the **report stage only** of the scrape → extract → analyze → report pipeline. All changes must respect `AGENTS.md`, `docs/GUARDRAILS.md`, and the data-model contract in `docs/ARCHITECTURE.md`.

## Context

- The report is a **Quarto book** built from `quarto.yml` + `index.qmd` + chapter notebooks under `notebooks/`. Output goes to `data/reports/` (HTML and PDF).
- The current PDF engine is `pdflatex` (Quarto default) and the document class is `book`.
- The current bound PDF (28 pages) has the following observable defects, documented per page in the source review. **Each defect maps to a fix in the [Required fixes](#required-fixes) section. Do not improvise — apply the fixes listed.**

  - Tables on pages 3, 15, 17, 25 render as raw Polars DataFrame `print()` debug output (visible `str / u32 / f64` schema row, literal quoted string cells, mid-table `...` ellipsis row).
  - Greek letters and math operators are missing throughout: page 3 shows `"= 0.05 after Benjamini–Hochberg"` (should be `α ≤ 0.05`), `"Cohen's d   0.5"` (should be `Cohen's d ≥ 0.5`), `"STRONG convergence narrative: 3 features"` (should be `≥ 3`).
  - Title page (p1) is empty — title plus two short paragraphs over half a blank page. No client name, prepared-by, version, date, run ID, corpus hash, or classification banner.
  - Page numbering resets to 1 every chapter (pages labeled "1" appear on at least p2, p4, p8, p15).
  - Charts use **inconsistent rendering engines**: heatmap on p6 and bar chart on p17 are matplotlib; line charts on p11 and p22 and the histogram on p12 are Plotly. Different fonts, palettes, panel backgrounds.
  - Specific chart defects: heatmap (p6) author labels truncated to "-christopher" / "haary-leeman"; histogram (p12) title overlaps legend and 14 stacked author colors are unreadable; bar chart (p17) x-axis labels are cramped at 45°; line chart (p11) y-axis label awkwardly stacked.
  - Inline file paths break mid-token (e.g., `data-analysis/*_result.json` on p4, `forensics.analysis.drift.load_drift_summary` running off the right edge on p12).
  - No table of contents, no list of figures, no list of tables, no running headers/footers.
  - No figure or table numbers — figures float captionless under section-heading framing.
  - Several pages end with a third of the page empty due to the `book` class chapter-page-break behavior (p4, p8, p9, p19).

## Required fixes

Apply these in order. Each fix lists the specific files to edit and the verification that proves it landed.

### 1. Switch the PDF engine and fonts

**Edit `quarto.yml`.** Under `format.pdf`, replace the existing block with:

```yaml
format:
  pdf:
    pdf-engine: xelatex
    documentclass: scrartcl
    classoption:
      - paper=letter
      - DIV=12
      - parskip=half
    mainfont: "TeX Gyre Pagella"
    sansfont: "Inter"
    monofont: "JetBrains Mono"
    fontsize: 11pt
    linkcolor: "navy"
    urlcolor: "navy"
    toc: true
    toc-depth: 2
    lof: true
    lot: true
    number-sections: true
    colorlinks: true
    geometry:
      - margin=1in
      - top=0.9in
      - bottom=1.1in
    include-in-header:
      text: |
        \usepackage{unicode-math}
        \setmathfont{Latin Modern Math}
        \usepackage{microtype}
        \usepackage{seqsplit}
        \usepackage{xcolor}
        \definecolor{adnavy}{HTML}{0F2A44}
        \definecolor{adred}{HTML}{B23A48}
        \definecolor{adgreen}{HTML}{3F784C}
        \definecolor{adgray}{HTML}{6B7280}
        \definecolor{adgold}{HTML}{C7A04A}
        \usepackage{scrlayer-scrpage}
        \pagestyle{scrheadings}
        \clearpairofpagestyles
        \chead{\small\itshape AI Writing Forensics — Mediaite Investigation}
        \cfoot{\small Page \thepage\ of \pageref{LastPage} \quad·\quad 2026-04-24}
        \usepackage{lastpage}
```

If `TeX Gyre Pagella` or `Inter` are not installed in the build environment, fall back to `Source Serif 4` / `Source Sans 3`, then `Charter` / `IBM Plex Sans`. Document the chosen fonts in the HANDOFF block.

**Verify:** `quarto render --to pdf` succeeds. The compiled PDF page 3 shows `α`, `≤`, `≥` correctly. Page numbering is continuous from 1 to (LastPage). Running header reads "AI Writing Forensics — Mediaite Investigation" on every page, footer reads "Page X of N · 2026-04-24".

### 2. Build a real cover page

**Create `before-body.tex`** at the repo root, containing:

```latex
\begin{titlepage}
\thispagestyle{empty}
\centering
\vspace*{2cm}
{\color{adnavy}\rule{\textwidth}{1.5pt}}
\vspace{1.5cm}

{\Huge\bfseries AI Writing Forensics\par}
\vspace{0.4cm}
{\Large Mediaite Investigation\par}
\vspace{2cm}

{\large\itshape A stylometric, embedding-drift, and probability-based\\
forensic analysis of writing-style evolution at \texttt{Mediaite.com}\par}
\vfill

\begin{tabular}{rl}
\textbf{Prepared by:} & Abstract Data LLC \\
\textbf{Prepared for:} & (client) \\
\textbf{Report version:} & 1.0 \\
\textbf{Date:} & 2026-04-24 \\
\textbf{Run ID:} & 5d0fd46a-1949-41e0-b88b-e742e244d1cc \\
\textbf{Corpus hash:} & a2dd2579990b \\
\textbf{Build:} & \texttt{\jobname} \\
\end{tabular}

\vspace{2cm}
{\color{adred}\textbf{CONFIDENTIAL — INVESTIGATION WORKING DRAFT}}

\vspace{0.5cm}
{\color{adnavy}\rule{\textwidth}{1.5pt}}
\end{titlepage}
\clearpage
```

**Reference it from `quarto.yml`** under `format.pdf`:

```yaml
    include-before-body: before-body.tex
```

**Verify:** the first page of the rendered PDF shows the title block, metadata table, and red `CONFIDENTIAL` banner. The TOC starts on page 2 or 3.

### 3. Replace every Polars `print()` table with a properly rendered table

**Edit each notebook** under `notebooks/` whose Polars DataFrame outputs are visible in the rendered PDF (at minimum `02_corpus_audit.ipynb`, `04_feature_analysis.ipynb`, `05_change_point_detection.ipynb`, `07_statistical_evidence.ipynb`, `09_full_report.ipynb`).

Replace patterns of the form:

```python
df  # last expression, prints DataFrame
```

with:

```python
from IPython.display import Markdown
Markdown(df.to_pandas().to_markdown(index=False, floatfmt=",.3f"))
```

For headline tables that need formatting beyond plain markdown (column alignment, percentage formatting, conditional row highlighting), use `great_tables` instead:

```python
from great_tables import GT, md, html
GT(df.to_pandas()).tab_header(title="…").fmt_percent(columns="pct_significant", decimals=1)
```

For each table, add a Quarto cell option block:

```python
#| label: tbl-per-author-significance
#| tbl-cap: "Per-author significance rate (Phase 15 post-fix run)."
```

**Do not** leave any cell whose final expression is a raw Polars DataFrame. The rendered PDF must contain zero instances of the schema row (`str`, `u32`, `f64`) or the literal `"slug"` quoted-string cells or the `...` ellipsis row.

**Verify:** `grep -rn "f64$" data/reports/*.tex 2>/dev/null` returns nothing. Visually scan the rendered PDF and confirm every table has a numbered caption ("Table 1." style) and right-aligned numerics.

### 4. Unify chart rendering on matplotlib for the print path

**Decision:** Plotly is removed from the PDF render path entirely. It remains acceptable for the HTML build only.

**Edit each notebook** that produces charts. Replace Plotly figures with matplotlib equivalents using a shared style file. Create `notebooks/_styles.py`:

```python
"""Shared matplotlib style for the bound report. Import from every notebook."""
import matplotlib.pyplot as plt
import matplotlib as mpl

ABSTRACT_DATA_PALETTE = {
    "navy":  "#0F2A44",
    "red":   "#B23A48",
    "green": "#3F784C",
    "gray":  "#6B7280",
    "gold":  "#C7A04A",
}

def apply_report_style() -> None:
    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": ["TeX Gyre Pagella", "Palatino", "Charter", "DejaVu Serif"],
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.labelsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.prop_cycle": mpl.cycler(color=list(ABSTRACT_DATA_PALETTE.values())),
        "figure.dpi": 150,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "legend.frameon": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linestyle": "-",
    })
```

In every plotting notebook, import and call `apply_report_style()` in the first code cell before any chart.

**Per-chart fixes:**

- **p6 heatmap (`05_change_point_detection.ipynb`):** rotate y-axis author labels to 0° (horizontal) and increase the left margin so labels are not truncated. Rotate x-axis feature labels to 60° instead of 45°.
- **p11 line chart (`06_embedding_drift.ipynb`):** add an explicit title ("Monthly centroid velocity, top-3 high-density authors"); set y-axis label to a single line ("Centroid velocity (cosine distance, month-over-month)").
- **p12 histogram (`06_embedding_drift.ipynb`):** facet into a 4×4 small-multiples grid (one panel per author) using `plt.subplots(nrows=4, ncols=4, sharex=True, sharey=True)`. The current overlaid 14-author stacked histogram is unreadable.
- **p17 bar chart (`07_statistical_evidence.ipynb`):** rotate x-axis labels to 90° and increase bottom margin; or split into two bar charts (top 10 + bottom 10) on consecutive figures.
- **p22 dual-line target-vs-control chart (`08_control_comparison.ipynb`):** keep as-is — this is the reference style for the document.

**Verify:** the rendered PDF contains no Plotly figures (no Plotly's distinctive light-gray panel background, no Plotly legend pill above the title). Every figure uses Pagella/Palatino serif type. The Abstract Data palette is consistent across all charts.

### 5. Add figure and table numbering with captions

For every `#| fig-*` and `#| tbl-*` cell option in every notebook, ensure both a `label:` and a `cap:` are set. Quarto then auto-numbers and emits "Figure N." / "Table N." with a numbered caption block. Cross-reference figures from the prose with `@fig-...` syntax where the prose currently says "see chart above" or "shown below."

**Verify:** the LoF and LoT pages render with at least 8 figures and 6 tables. Spot-check three figure references in body text resolve to the correct numbers.

### 6. Path-break and inline-code fixes

In `before-body.tex` (or a separate `_macros.tex`), define a path-friendly inline code macro:

```latex
\providecommand{\codebrk}[1]{\texttt{\seqsplit{#1}}}
```

For occurrences of long file paths, dotted-module names, or run identifiers in body text (notebook markdown cells), replace e.g. `` `data/analysis/*_result.json` `` with a Quarto raw-LaTeX inline if needed, or rely on `microtype` from the header to soften breaks. The `seqsplit` macro is available for spots that still overflow.

For inline code visual separation, ensure prose `code` spans render with a soft tinted background. Add to `include-in-header`:

```latex
\usepackage{tcolorbox}
\newtcbox{\codebox}{nobeforeafter,colback=black!5,colframe=black!5,size=fbox,arc=2pt,boxsep=1pt,left=2pt,right=2pt,top=1pt,bottom=1pt}
```

**Verify:** spot-check pages 4, 9, 12 in the rebuilt PDF — no inline path breaks mid-token, no module names overflowing the right margin.

### 7. Confirm document class and page-break behavior

The class swap from `book` to `scrartcl` (in fix #1) eliminates forced page breaks at top-level headings. Verify by checking that pages 4, 8, 9, and 19 in the rebuilt PDF do not end with a third of the page empty. If they still do, set `\raggedbottom` in the header so trailing whitespace pools at the bottom rather than being justified.

## Acceptance criteria

The fix is **complete** when all of the following hold:

1. `quarto render --to pdf` succeeds with zero LaTeX errors and zero font warnings.
2. The rendered PDF has a styled cover page on page 1 with the metadata table and the red `CONFIDENTIAL` banner.
3. Page numbering is continuous from 1 to N, with running headers and footers on every page after the cover.
4. Every Greek letter and math operator (`α`, `β`, `≤`, `≥`, `χ²`, `≠`) renders correctly.
5. No table in the PDF shows a Polars schema row (`str`, `u32`, `f64`), literal-quoted string cells, or `...` ellipsis. Every table has a numbered caption.
6. No chart in the PDF is rendered by Plotly. All charts share the Abstract Data palette and Pagella/Palatino serif type.
7. The heatmap (p6 in old PDF), histogram (p12), bar chart (p17), and line chart (p11) defects listed in fix #4 are fixed.
8. TOC, LoF, and LoT are present and accurate. At least one prose `@fig-` cross-reference resolves correctly.
9. `HANDOFF.md` has a new completion block with the file list, decisions made (font choice, palette overrides, any deviations), verification commands run, and unresolved issues.
10. `docs/RUNBOOK.md` has a new entry under the Reports section documenting the new build dependencies (XeLaTeX, font packages) and the command to render the bound PDF.

## Verification commands

Run all of these locally before reporting complete. Capture the output for the HANDOFF block.

```bash
uv sync
quarto render --to pdf

# Confirm the build emitted a PDF and capture its page count
ls -lh data/reports/*.pdf
python3 -c "from pypdf import PdfReader; r=PdfReader('data/reports/AI-Writing-Forensics-Mediaite-Investigation.pdf'); print('pages:', len(r.pages))"

# Confirm no Polars schema rows leaked into the rendered TeX
grep -rn -E '^(str|u32|f64|i64)\s' data/reports/*.tex 2>/dev/null && echo "FAIL: schema row leaked" || echo "OK: no schema rows"

# Confirm no Plotly residue in the TeX intermediate
grep -rn 'plotly' data/reports/*.tex 2>/dev/null && echo "WARN: plotly references in TeX" || echo "OK: no plotly residue"

# Optional: Quarto profile to confirm chapter-break behavior
quarto check
```

## Out of scope

- Any modification to `src/forensics/` analysis code, stage boundaries, the data model contract, or `config.toml` thresholds.
- Adding, removing, or reordering chapters in `quarto.yml`. Style only.
- Changing the prose narrative or interpretation of findings.
- The HTML render path (Plotly remains acceptable there). This pass is for the PDF only.
- Custom domain configuration for the deployed report (handled by the GitHub Pages migration, separate work item).

## Deliverables

A single PR (or clean staged-changes state) containing:

- `quarto.yml` (PDF format block rewritten per fix #1)
- `before-body.tex` (new file, cover page)
- `notebooks/_styles.py` (new file, matplotlib style)
- Edits to each notebook that previously used Polars `print()` tables or Plotly figures
- `HANDOFF.md` (new completion block)
- `docs/RUNBOOK.md` (new entry under Reports)

The PR description must list:

- The chosen fonts (in case the primary picks were unavailable in the build environment)
- The output PDF page count before vs after (sanity check)
- Any acceptance-criteria item that could not be met and why

## Constraints from `AGENTS.md` / `CLAUDE.md`

- Stage boundaries are sacred. Report-stage edits only.
- `HANDOFF.md` update is required before reporting complete.
- If the same LaTeX or Quarto error repeats 3+ times, append a Sign to `docs/GUARDRAILS.md` per the failure-pattern policy.
- All Python execution via `uv run`.
