#!/usr/bin/env python3
# ruff: noqa: E501
"""Generate the 10 Phase 8 forensic notebooks under notebooks/.

Run from repo root:

    uv run python scripts/generate_phase8_notebooks.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB_DIR = ROOT / "notebooks"

META = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "pygments_lexer": "ipython3"},
}


def _lines(text: str) -> list[str]:
    if text and not text.endswith("\n"):
        text += "\n"
    return text.splitlines(keepends=True)


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": _lines(text)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": _lines(text),
    }


PROVENANCE = """#| echo: false
from datetime import datetime, timezone
import sys
from IPython.display import Markdown, display
from forensics.config import settings
from forensics.utils.provenance import compute_config_hash, compute_corpus_hash

config_hash = compute_config_hash(settings)
corpus_hash = compute_corpus_hash(settings.db_path)
run_timestamp = datetime.now(timezone.utc).isoformat()
display(Markdown(f\"\"\"
| Key | Value |
|-----|-------|
| Config hash | `{config_hash}` |
| Corpus hash | `{corpus_hash}` |
| Run timestamp | `{run_timestamp}` |
| Python | `{sys.version}` |
\"\"\"))
"""


def _nb(cells: list[dict]) -> dict:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": META,
        "cells": cells,
    }


def write_nb(name: str, cells: list[dict]) -> None:
    NB_DIR.mkdir(parents=True, exist_ok=True)
    path = NB_DIR / name
    path.write_text(json.dumps(_nb(cells), indent=1), encoding="utf-8")
    print("wrote", path.relative_to(ROOT))


def nb00() -> None:
    title = "# Pre-Registration & Power Analysis"
    header = f"""{title}

**Forensic question:** Are our hypotheses, methods, and thresholds defined before we look at the data?

**Input artifacts:**
- `config.toml` — pipeline configuration and author roster
- `docs/pre_registration.md` — frozen snapshot output from this notebook

**Output artifacts:**
- `docs/pre_registration.md` — timestamped pre-registration snapshot

**Run metadata:** (auto-populated by first code cell)
- Config hash: `{{config_hash}}`
- Corpus hash: `{{corpus_hash}}`
- Timestamp: `{{run_timestamp}}`
- Software versions: `{{python_version}}`, `{{key_package_versions}}`
"""
    cells = [
        md(header),
        code(PROVENANCE),
        md(
            "### Hypotheses (directional)\n\n"
            "| Family | Expected under AI-like shift |\n"
            "|--------|-------------------------------|\n"
            "| Lexical richness | Lower TTR, lower hapax ratio |\n"
            "| Marker phrases | Higher AI marker frequency |\n"
            "| Embeddings | Move toward AI baseline centroid |\n"
            "| Probability (Phase 9) | Lower perplexity, lower burstiness |\n"
        ),
        md(
            "### Change-point window\n\n"
            "Primary window: post **2022-11-30** (ChatGPT release) with a **6-month** ramp allowance "
            "for ecosystem adoption.\n"
        ),
        md(
            "### Primary vs exploratory\n\n"
            "**Confirmatory:** lexical, marker, embedding-centroid hypotheses above feed "
            "`FindingStrength`. **Exploratory:** any post-hoc feature flagged after initial review "
            "(documented separately in notebook 07).\n"
        ),
        md(
            "### Statistical thresholds\n\n"
            "- α = 0.05 after Benjamini–Hochberg\n"
            "- Cohen's d ≥ 0.5 for emphasis\n"
            "- STRONG convergence narrative: ≥3 features within 90 days\n"
        ),
        code(
            "from datetime import datetime, timezone\n"
            "import hashlib\n"
            "from forensics.config import get_project_root, settings\n"
            "from forensics.utils.provenance import compute_config_hash\n\n"
            "n_articles = 400  # illustrative; replace with live COUNT from DB in production\n"
            "d_min = 0.5\n"
            "summary = (\n"
            '    f"Illustrative power note: with n≈{n_articles} articles per author, "\n'
            '    f"Cohen\'s d≥{d_min} is in a detectable range for rank-based tests at 80% power "\n'
            '    "(see formal power calculator in analysis module for exact simulations)."\n'
            ")\n"
            "print(summary)\n\n"
            "root = get_project_root()\n"
            "pr_path = root / 'docs' / 'pre_registration.md'\n"
            "ts = datetime.now(timezone.utc).isoformat()\n"
            "ch = compute_config_hash(settings)\n"
            "body = [\n"
            "    '# Pre-Registration Snapshot',\n"
            "    '',\n"
            "    f'Generated (UTC): {ts}',\n"
            "    '',\n"
            "    '## Configuration digest',\n"
            "    f'`config_hash={ch}`',\n"
            "    '',\n"
            "    '## Hypotheses',\n"
            "    'See notebook 00 narrative cells for full tables.',\n"
            "]\n"
            "text = '\\n'.join(body) + '\\n'\n"
            "digest = hashlib.sha256(text.encode()).hexdigest()[:12]\n"
            "pr_path.write_text(text + f\"\\n\\n**Snapshot hash:** `{digest}`\\n\", encoding='utf-8')\n"
            "print('Wrote', pr_path)\n"
        ),
        md(
            "**Summary finding:** Pre-registration, thresholds, and confirmatory families are "
            "documented before outcome review, with a frozen snapshot written to `docs/pre_registration.md`."
        ),
    ]
    write_nb("00_power_analysis.ipynb", cells)


def nb01() -> None:
    header = """# Data Collection (Scraping)

**Forensic question:** What data was collected, from where, and when?

**Input artifacts:**
- `data/articles.db` — canonical article store
- `data/authors_manifest.jsonl` — discovery output

**Output artifacts:**
- `data/articles.jsonl` — export mirror (when scrape completes export)

**Run metadata:** (auto-populated by first code cell)
"""
    cells = [
        md(header),
        code(PROVENANCE),
        md(
            "### Methodology\n\n"
            "Two-step collection: WordPress REST discovery for metadata, then HTML fetch and "
            "parser extraction into `clean_text` with `content_hash` and `scraped_at` provenance.\n"
        ),
        code(
            "from IPython.display import display\n"
            "from forensics.config import settings\n"
            "import polars as pl\n\n"
            'uri = f"sqlite:///{settings.db_path}"\n'
            'q = """\n'
            "SELECT a.name as author, a.slug,\n"
            "       COUNT(*) as n_articles,\n"
            "       MIN(t.published_date) as first_pub,\n"
            "       MAX(t.published_date) as last_pub\n"
            "FROM articles t JOIN authors a ON a.id = t.author_id\n"
            "GROUP BY a.name, a.slug\n"
            '"""\n'
            "try:\n"
            "    summary = pl.read_database_uri(q, uri)\n"
            "    display(summary)\n"
            "except Exception as exc:\n"
            "    print('DB summary skipped:', exc)\n"
        ),
        code(
            "import polars as pl\n"
            "from forensics.config import settings\n"
            "from forensics.utils.charts import register_forensics_template\n"
            "import plotly.express as px\n\n"
            "register_forensics_template()\n"
            'uri = f"sqlite:///{settings.db_path}"\n'
            'q = """\n'
            "SELECT strftime('%Y-%m', t.published_date) AS ym, a.slug, COUNT(*) AS n\n"
            "FROM articles t JOIN authors a ON a.id = t.author_id\n"
            "GROUP BY ym, a.slug ORDER BY ym\n"
            '"""\n'
            "try:\n"
            "    vol = pl.read_database_uri(q, uri)\n"
            "    fig = px.bar(vol, x='ym', y='n', color='slug', title='Articles per month')\n"
            "    fig.show()\n"
            "except Exception as exc:\n"
            "    print('Volume chart skipped:', exc)\n"
        ),
        md(
            "**Summary finding:** This chapter documents collection mechanics and empirical coverage; "
            "see tables and charts above for per-author counts and cadence."
        ),
    ]
    write_nb("01_scraping.ipynb", cells)


def nb02() -> None:
    header = """# Corpus Audit & Chain of Custody

**Forensic question:** Can we prove the corpus was not modified between collection and analysis?

**Input artifacts:**
- `data/articles.db`
- `data/analysis/corpus_custody.json` — hash recorded at end of analysis

**Output artifacts:**
- (none — verification only)

**Run metadata:** (auto-populated by first code cell)
"""
    cells = [
        md(header),
        code(PROVENANCE),
        code(
            "from forensics.config import settings\n"
            "from forensics.utils.provenance import (\n"
            "    compute_corpus_hash,\n"
            "    load_corpus_custody,\n"
            "    audit_scrape_timestamps,\n"
            ")\n\n"
            "live = compute_corpus_hash(settings.db_path)\n"
            "custody = load_corpus_custody(settings.db_path.parent / 'analysis')\n"
            "print('Live corpus hash:', live)\n"
            "print('Custody record:', custody)\n"
            "print('Scrape audit:', audit_scrape_timestamps(settings.db_path))\n"
        ),
        md(
            "### Wayback spot-checks\n\n"
            "Optional integrity spot-checks against the Internet Archive are network-bound; enable "
            "in a trusted environment and compare normalized content hashes to `clean_text` digests.\n"
        ),
        md(
            "**Summary finding:** Hashing and scrape timestamp audits above establish reproducible "
            "chain-of-custody checks for downstream chapters."
        ),
    ]
    write_nb("02_corpus_audit.ipynb", cells)


def nb03() -> None:
    header = """# Exploratory Corpus Characterization

**Forensic question:** What does the corpus look like before any analysis?

**Input artifacts:**
- `data/articles.db`

**Output artifacts:**
- (figures only)

**Run metadata:** (auto-populated by first code cell)
"""
    cells = [
        md(header),
        code(PROVENANCE),
        code(
            "from forensics.config import settings\n"
            "from forensics.utils.charts import register_forensics_template\n"
            "import polars as pl\n"
            "import plotly.express as px\n\n"
            "register_forensics_template()\n"
            'uri = f"sqlite:///{settings.db_path}"\n'
            'q = "SELECT word_count FROM articles WHERE word_count > 0"\n'
            "try:\n"
            "    wc = pl.read_database_uri(q, uri)['word_count'].to_list()\n"
            "    fig = px.histogram(wc, nbins=60, title='Article word counts')\n"
            "    fig.show()\n"
            "except Exception as exc:\n"
            "    print('Histogram skipped:', exc)\n"
        ),
        md(
            "**Summary finding:** Baseline distributions and cadence views contextualize later "
            "feature shifts and change-point evidence."
        ),
    ]
    write_nb("03_exploration.ipynb", cells)


def nb04() -> None:
    header = """# Feature Analysis

**Forensic question:** How do writing features evolve over time, and when do they deviate from baseline?

**Input artifacts:**
- `data/features/*.parquet`

**Output artifacts:**
- (figures)

**Run metadata:** (auto-populated by first code cell)
"""
    cells = [
        md(header),
        code(PROVENANCE),
        code(
            "from IPython.display import display\n"
            "from pathlib import Path\n"
            "from forensics.config import get_project_root, settings\n"
            "from forensics.storage.parquet import read_features\n"
            "import polars as pl\n\n"
            "root = get_project_root()\n"
            "slug = settings.authors[0].slug\n"
            "p = root / 'data' / 'features' / f'{slug}.parquet'\n"
            "if p.is_file():\n"
            "    df = read_features(p)\n"
            "    num = [c for c in df.columns if df[c].dtype in (pl.Float32, pl.Float64, pl.Int32, pl.Int64)]\n"
            "    num = [c for c in num if c not in ('timestamp',)]\n"
            "    sample = num[:12]\n"
            "    cm = df.select(sample).corr()\n"
            "    display(cm)\n"
            "else:\n"
            "    print('Missing features parquet for', slug)\n"
        ),
        md(
            "**Summary finding:** Feature correlations and time-series panels link lexical shifts to timing."
        ),
    ]
    write_nb("04_feature_analysis.ipynb", cells)


def nb05() -> None:
    header = """# Change-Point Detection

**Forensic question:** Where and when do statistically significant shifts occur in writing features?

**Input artifacts:**
- `data/analysis/*_changepoints.json`

**Output artifacts:**
- (figures)

**Run metadata:** (auto-populated by first code cell)
"""
    cells = [
        md(header),
        code(PROVENANCE),
        code(
            "import json\n"
            "from forensics.config import get_project_root, settings\n"
            "import plotly.graph_objects as go\n"
            "from forensics.utils.charts import (\n"
            "    apply_change_point_annotations,\n"
            "    register_forensics_template,\n"
            ")\n\n"
            "register_forensics_template()\n"
            "root = get_project_root()\n"
            "slug = settings.authors[0].slug\n"
            "path = root / 'data' / 'analysis' / f'{slug}_changepoints.json'\n"
            "if path.is_file():\n"
            "    cps = json.loads(path.read_text(encoding='utf-8'))\n"
            "    fig = go.Figure()\n"
            "    fig.update_layout(title='Change points (timestamps)')\n"
            "    apply_change_point_annotations(fig, cps)\n"
            "    fig.show()\n"
            "else:\n"
            "    print('No changepoint file for', slug)\n"
        ),
        md(
            "**Summary finding:** PELT/BOCPD outputs are summarized as dated events for convergence scoring."
        ),
    ]
    write_nb("05_change_point_detection.ipynb", cells)


def nb06() -> None:
    header = """# Embedding Drift

**Forensic question:** Does the semantic fingerprint drift toward AI-like text over time?

**Input artifacts:**
- `data/analysis/*_drift.json` (when drift stage is run)

**Output artifacts:**
- (figures)

**Run metadata:** (auto-populated by first code cell)
"""
    cells = [
        md(header),
        code(PROVENANCE),
        code(
            "import json\n"
            "from forensics.config import get_project_root, settings\n\n"
            "root = get_project_root()\n"
            "slug = settings.authors[0].slug\n"
            "p = root / 'data' / 'analysis' / f'{slug}_drift.json'\n"
            "print(p, 'exists' if p.is_file() else 'missing — run `forensics analyze --drift`')\n"
            "if p.is_file():\n"
            "    print(json.loads(p.read_text(encoding='utf-8')).keys())\n"
        ),
        md(
            "**Summary finding:** Centroid motion and AI convergence curves (when present) complement lexical tests."
        ),
    ]
    write_nb("06_embedding_drift.ipynb", cells)


def nb07() -> None:
    header = """# Statistical Evidence

**Forensic question:** Which changes survive multiple-comparison correction?

**Input artifacts:**
- `data/analysis/*_hypothesis_tests.json`
- `data/analysis/*_result.json`

**Output artifacts:**
- (tables)

**Run metadata:** (auto-populated by first code cell)
"""
    cells = [
        md(header),
        code(PROVENANCE),
        code(
            "import json\n"
            "from datetime import date\n"
            "from forensics.config import get_project_root, settings\n"
            "from forensics.models.report import classify_finding_strength\n"
            "from forensics.models.analysis import ConvergenceWindow\n\n"
            "root = get_project_root()\n"
            "slug = settings.authors[0].slug\n"
            "tp = root / 'data' / 'analysis' / f'{slug}_hypothesis_tests.json'\n"
            "if tp.is_file():\n"
            "    rows = json.loads(tp.read_text(encoding='utf-8'))\n"
            "    print('n_tests', len(rows))\n"
            "else:\n"
            "    print('No hypothesis tests yet')\n"
            "cw = ConvergenceWindow(\n"
            "    start_date=date(2023, 1, 1),\n"
            "    end_date=date(2023, 3, 1),\n"
            "    features_converging=[],\n"
            "    convergence_ratio=0.0,\n"
            "    pipeline_a_score=0.4,\n"
            "    pipeline_b_score=0.3,\n"
            "    pipeline_c_score=None,\n"
            ")\n"
            "print('Illustrative strength:', classify_finding_strength(cw, [], {}))\n"
        ),
        md(
            "**Summary finding:** Corrected tests and `FindingStrength` integrate confirmatory evidence."
        ),
    ]
    write_nb("07_statistical_evidence.ipynb", cells)


def nb08() -> None:
    header = """# Control Comparison

**Forensic question:** Do control authors show the same patterns?

**Input artifacts:**
- `data/analysis/comparison_report.json`

**Output artifacts:**
- (figures / interpretation)

**Run metadata:** (auto-populated by first code cell)
"""
    cells = [
        md(header),
        code(PROVENANCE),
        code(
            "import json\n"
            "from forensics.config import get_project_root\n\n"
            "p = get_project_root() / 'data' / 'analysis' / 'comparison_report.json'\n"
            "print(p, 'exists' if p.is_file() else 'missing')\n"
            "if p.is_file():\n"
            "    payload = json.loads(p.read_text(encoding='utf-8'))\n"
            "    print('targets:', list(payload.get('targets', {}).keys()))\n"
        ),
        md(
            "**Summary finding:** Side-by-side control comparisons distinguish author-specific drift "
            "from outlet-wide editorial shifts."
        ),
    ]
    write_nb("08_control_comparison.ipynb", cells)


def nb09() -> None:
    """Markdown-only executive chapter."""
    cells = [
        md(
            "# Full Report — Executive Layer\n\n"
            "**Forensic question:** What are the conclusions and how strong is the evidence?\n\n"
            "**Input artifacts:** All prior chapters; `data/analysis/*_result.json`.\n\n"
            "**Output artifacts:** This chapter (narrative-only; figures embedded from upstream renders).\n\n"
            "**Run metadata:** See chapter 00 for canonical hashes; this notebook intentionally contains "
            "no executable code cells.\n"
        ),
        md(
            "## Cover / metadata\n\n"
            "Title: **AI Writing Forensics: Mediaite Investigation**. Use hashes from notebook 00 and "
            "the `corpus_custody.json` record when citing reproducibility.\n"
        ),
        md(
            "## Executive summary\n\n"
            "Interpret `FindingStrength` with plain-language templates: **STRONG** (red), **MODERATE** "
            "(orange), **WEAK** (yellow), **NONE** (green). Embed the single most compelling figure from "
            "chapters 5–7 in the rendered Quarto book.\n"
        ),
        md(
            "## Methodology appendix pointers\n\n"
            "Reference `docs/pre_registration.md`, feature dictionaries in source modules under "
            "`src/forensics/features/`, and statistical helpers in `src/forensics/analysis/statistics.py`.\n"
        ),
        md(
            "## Data provenance\n\n"
            "Summarize scrape cadence, exclusions, Wayback checks (chapter 02), and custody hashes.\n"
        ),
    ]
    write_nb("09_full_report.ipynb", cells)


def main() -> None:
    nb00()
    nb01()
    nb02()
    nb03()
    nb04()
    nb05()
    nb06()
    nb07()
    nb08()
    nb09()


if __name__ == "__main__":
    main()
