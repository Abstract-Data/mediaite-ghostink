# Mintlify Component & Developer Documentation Setup

Version: 0.1.0
Status: active
Last Updated: 2026-04-24
Model: claude-opus-4-7

---

## ⚠️ Scope boundary — read first

> **This prompt is NOT a replacement for the Quarto-rendered forensic report.**
>
> The Quarto build (`quarto.yml`, `index.qmd`, `notebooks/*.ipynb` → `data/reports/`) is the project's **client-facing bound deliverable** and is **out of scope for this work**. Do not modify `quarto.yml`, the notebooks, the rendered report, or anything in the `report` pipeline stage.
>
> **Mintlify is being added solely to host developer / component / operations documentation for the software itself** — module references, stage contracts, architecture docs, ADRs, runbook, prompts library, and CLI reference. Two distinct audiences, two distinct build paths, two distinct deploys. They must not be conflated.
>
> If at any point during this work you find yourself touching `quarto.yml`, `index.qmd`, any file under `notebooks/`, or any file under `data/reports/`, **stop and surface the question** in the HANDOFF block. The two systems must remain independent.

---

## Mission

Stand up [Mintlify](https://www.mintlify.com/docs) as the developer documentation platform for the `mediaite-ghostink` software. Produce a `mintlify/` directory at the repo root containing a `docs.json` and an MDX content tree that documents:

- The pipeline architecture and stage contracts
- Each pipeline stage (scrape → extract → analyze → report) as a top-level component
- Each analysis module (change-points, embedding drift, convergence, hypothesis tests, baseline)
- Each feature family (lexical, sentence-structure, content-repetition, probability)
- Storage layers (SQLite, Parquet, DuckDB, embeddings)
- CLI / TUI / Survey / Reporting surfaces
- Operations docs (runbook, deployments, testing, guardrails)
- All ADRs (currently `docs/adr/ADR-001` … `ADR-007`)
- The prompt library (every family in `prompts/`)

Wire it to deploy on every push to `main`. Single source of truth for shared content lives in the existing `docs/` markdown files and `prompts/*/current.md`; the Mintlify content is **derived** from those at build time.

## Context

- The repo is `mediaite-ghostink`, a Python 3.13 + uv-managed forensic pipeline.
- `docs/` already contains: `ARCHITECTURE.md`, `GUARDRAILS.md`, `RUNBOOK.md`, `TESTING.md`, `DEPLOYMENTS.md`, `pre_registration.md`, plus `docs/adr/` (7 ADRs) and `docs/plans/`.
- `prompts/` is a versioned prompt library with a strict contract documented in `prompts/README.md`.
- The Quarto book (out of scope here — see top section) renders to `data/reports/`.
- The codebase has gitnexus-identified component areas (per `CLAUDE.md`): Tests, Unit, Features, Analysis, Scraper, Survey, Cli, Integration, Screens, Scripts, Tui, Storage, Baseline, Progress, Reporting, Forensics, Calibration, Evals, Migrations, Config. These map to navigation groups in Mintlify.
- Current Mintlify config file is `docs.json` (as of 2025; the older `mint.json` was deprecated).
- Mintlify CLI requires Node.js 20.17+ and is installed via `npm i -g mint`.

## Required steps

Apply these in order. Each step lists files to create/edit and verification.

### 1. Create the `mintlify/` directory at the repo root

**Do not** put Mintlify content inside `docs/` (which contains canonical markdown), `data/reports/` (Quarto output, off-limits), `notebooks/` (Quarto chapters, off-limits), or `src/` (code).

```
mediaite-ghostink/
  mintlify/
    docs.json
    introduction.mdx
    quickstart.mdx
    architecture/
    components/
    operations/
    adr/
    prompts/
    snippets/
    logo/
```

Add `mintlify/` to `.gitignore` *only* for derived/generated content (e.g., snippet copies). Hand-authored MDX (the page wrappers and `docs.json`) is committed.

### 2. Author `mintlify/docs.json`

Use exactly this scaffold, with `<owner>` replaced by the actual GitHub owner. The navigation tree mirrors the gitnexus component areas plus operations/ADR/prompts.

```json
{
  "$schema": "https://mintlify.com/docs.json",
  "theme": "mint",
  "name": "mediaite-ghostink",
  "description": "Hybrid forensic pipeline for AI writing adoption analysis at Mediaite.com — developer documentation. (For the bound forensic report, see the project's Quarto deployment.)",
  "colors": {
    "primary": "#0F2A44",
    "light":   "#3F6B91",
    "dark":    "#0F2A44"
  },
  "logo": {
    "light": "/logo/abstract-data-light.svg",
    "dark":  "/logo/abstract-data-dark.svg"
  },
  "favicon": "/favicon.svg",
  "navigation": {
    "tabs": [
      {
        "tab": "Get Started",
        "groups": [
          {
            "group": "Introduction",
            "pages": ["introduction", "quickstart"]
          },
          {
            "group": "Architecture",
            "pages": [
              "architecture/overview",
              "architecture/stage-contracts",
              "architecture/data-models",
              "architecture/storage-architecture",
              "architecture/feature-families",
              "architecture/analysis-methods"
            ]
          }
        ]
      },
      {
        "tab": "Components",
        "groups": [
          {
            "group": "Pipeline stages",
            "pages": [
              "components/stages/scrape",
              "components/stages/extract",
              "components/stages/analyze",
              "components/stages/report"
            ]
          },
          {
            "group": "Analysis modules",
            "pages": [
              "components/analysis/change-points",
              "components/analysis/embedding-drift",
              "components/analysis/convergence",
              "components/analysis/hypothesis-tests",
              "components/analysis/baseline",
              "components/analysis/calibration",
              "components/analysis/probability"
            ]
          },
          {
            "group": "Feature families",
            "pages": [
              "components/features/lexical",
              "components/features/sentence-structure",
              "components/features/content-repetition",
              "components/features/productivity",
              "components/features/probability"
            ]
          },
          {
            "group": "Storage layers",
            "pages": [
              "components/storage/sqlite",
              "components/storage/parquet",
              "components/storage/duckdb",
              "components/storage/embeddings"
            ]
          },
          {
            "group": "Surfaces",
            "pages": [
              "components/surfaces/cli",
              "components/surfaces/tui",
              "components/surfaces/survey",
              "components/surfaces/reporting"
            ]
          }
        ]
      },
      {
        "tab": "Operations",
        "groups": [
          {
            "group": "Day-to-day",
            "pages": [
              "operations/runbook",
              "operations/testing",
              "operations/guardrails",
              "operations/deployments",
              "operations/pre-registration"
            ]
          }
        ]
      },
      {
        "tab": "Decision Records",
        "groups": [
          {
            "group": "ADRs",
            "pages": [
              "adr/index",
              "adr/001-hybrid-forensics-methodology",
              "adr/002-storage-layer-sqlite-parquet-duckdb",
              "adr/003-agent-governance-and-hooks",
              "adr/004-scraper-storage-concurrency",
              "adr/005-sqlite-connection-management",
              "adr/006-cli-command-dispatch",
              "adr/007-deferred-scraper-storage-decoupling"
            ]
          }
        ]
      },
      {
        "tab": "Prompts",
        "groups": [
          {
            "group": "Prompt library",
            "pages": [
              "prompts/index",
              "prompts/contract",
              "prompts/core-agent",
              "prompts/phase1-scaffold-and-models",
              "prompts/phase2-scraper-discovery",
              "prompts/phase3-scraper-html-fetch",
              "prompts/phase4-feature-extraction",
              "prompts/phase5-analysis-changepoint-timeseries",
              "prompts/phase6-analysis-embedding-drift",
              "prompts/phase7-analysis-convergence-statistics",
              "prompts/phase8-report-and-deployment",
              "prompts/phase9-probability-features",
              "prompts/phase10-ai-baseline-generation",
              "prompts/phase11-typer-cli-migration",
              "prompts/phase12-survey-tui-hardening",
              "prompts/phase13-review-remediation",
              "prompts/phase14-review-remediation-r6",
              "prompts/phase15-optimizations",
              "prompts/report-visual-polish",
              "prompts/mintlify-component-docs"
            ]
          }
        ]
      }
    ],
    "global": {
      "anchors": [
        {
          "anchor": "GitHub",
          "icon": "github",
          "href": "https://github.com/<owner>/mediaite-ghostink"
        },
        {
          "anchor": "Forensic Report (Quarto)",
          "icon": "file-pdf",
          "href": "https://<owner>.github.io/mediaite-ghostink/"
        }
      ]
    }
  },
  "footer": {
    "socials": {
      "github": "https://github.com/<owner>/mediaite-ghostink"
    }
  }
}
```

The "Forensic Report (Quarto)" anchor in the footer/global section is mandatory — it links readers from the dev docs to the bound Quarto report deployed at `https://<owner>.github.io/mediaite-ghostink/`. The two sites must cross-reference each other but never be merged.

### 3. Build the content-derivation script

**Create `scripts/build_mintlify_content.py`**. This is the single mechanism that turns canonical markdown in `docs/` and `prompts/` into MDX pages under `mintlify/`. Hand-edited MDX (only the introduction, quickstart, and component pages) lives in `mintlify/` directly and is committed; derived content is regenerated by the script.

The script must:

1. Walk `docs/*.md` and `docs/adr/*.md`. For each file, read the H1 title and emit `mintlify/operations/<slug>.mdx` (or `mintlify/adr/<slug>.mdx`) with Mintlify YAML frontmatter (`title`, `description`, `icon`) followed by the original markdown body. Strip leading H1 since Mintlify renders the title from frontmatter.
2. Walk `prompts/*/current.md`. For each, emit `mintlify/prompts/<family>.mdx` with frontmatter and a `<Tabs>` block listing every version from `versions.json` so readers can switch between current and historical versions.
3. Walk `src/forensics/` to enumerate stages, analysis modules, feature families, storage layers, and surfaces. For each Python module, extract the module-level docstring and any class/function docstrings tagged with a `# mintlify:` directive. Emit a stub `mintlify/components/<area>/<module>.mdx` if and only if a hand-authored page does not already exist (do not overwrite hand-authored pages).
4. Print a summary at the end: number of pages emitted, number skipped because hand-authored, list of any `docs.json` page references that have no matching MDX file (broken-link preview).

**Do not** hardcode paths in MDX wrappers. The script must read the source files at build time so a single update in `docs/` propagates to the Mintlify site.

Run path:

```bash
uv run python scripts/build_mintlify_content.py --out mintlify
```

### 4. Author the small set of hand-written pages

Some pages introduce the project and should not be auto-generated. Author these by hand:

- `mintlify/introduction.mdx` — what the project is, who it's for (developers / operators), and an explicit pointer to the Quarto bound report for stakeholders. Use the `<Note>` Mintlify component to make the Quarto separation crystal clear:

  ```mdx
  <Note>
    This site is the **developer reference** for the `mediaite-ghostink` software.
    For the **bound forensic report** intended for stakeholders, see the
    [Quarto deployment](https://<owner>.github.io/mediaite-ghostink/). The
    two sites are independent: this site documents the code; that site
    documents the findings.
  </Note>
  ```

- `mintlify/quickstart.mdx` — local development setup (`uv sync`, `uv run forensics all`, where outputs land).
- `mintlify/architecture/overview.mdx` — high-level diagram and pointer to the canonical `docs/ARCHITECTURE.md` (rendered via the build script).
- One page per pipeline stage (`components/stages/{scrape,extract,analyze,report}.mdx`) following the [component template](#5-component-page-template) below.

For the `report` stage page specifically, write it carefully: it documents the report-stage *code* (Quarto build invocation, output paths, deploy workflow), and links out to the Quarto report URL. It must not duplicate the Quarto report's content.

### 5. Component page template

Use this exact structure for every component page (stages, analysis modules, feature families, storage layers, surfaces). Save as `mintlify/_templates/component.mdx` for reference.

```mdx
---
title: "<Component Name>"
description: "<one-line purpose>"
icon: "<lucide icon name>"
---

## Purpose

<one paragraph: what this component does, why it exists>

<CardGroup cols={2}>
  <Card title="Source" icon="folder" href="https://github.com/<owner>/mediaite-ghostink/tree/main/src/forensics/<path>">
    <code>src/forensics/<path></code>
  </Card>
  <Card title="Tests" icon="vial" href="https://github.com/<owner>/mediaite-ghostink/tree/main/tests/<path>">
    <code>tests/<path></code>
  </Card>
</CardGroup>

## Inputs and outputs

<ParamField path="input" type="<type>">
  <description of input artifact and its on-disk location>
</ParamField>

<ParamField path="output" type="<type>">
  <description of output artifact and its on-disk location>
</ParamField>

## Configuration

<CodeGroup>
```toml config.toml
[<section>]
key = value
```

```python Python API
from forensics.<module> import <function>
result = <function>(...)
```
</CodeGroup>

## Methods / behavior

<AccordionGroup>
  <Accordion title="<method name>" icon="<icon>">
    <description>
  </Accordion>
</AccordionGroup>

## Related

- [Architecture / stage contracts](/architecture/stage-contracts)
- [<other related component>](/components/<path>)
- [<related ADR>](/adr/<file>)
```

Every component page must:

- Link to source and tests on GitHub
- Document inputs and outputs with `<ParamField>` (artifact types and on-disk locations)
- Include a `<CodeGroup>` with at least the relevant `config.toml` block and a Python API example
- Cross-link to the architecture page, related components, and any relevant ADR

### 6. Local dev loop

```bash
# one-time
npm i -g mint   # requires Node 20.17+

# every time you write content
cd mintlify
mint dev        # http://localhost:3000, hot-reload

# before committing
mint broken-links
```

### 7. Deploy via Mintlify hosted

Manual one-time setup (cannot be automated — surface as a checklist for the maintainer in the HANDOFF block):

1. Sign up at mintlify.com.
2. Create a project linked to the `mediaite-ghostink` GitHub repo via the Mintlify GitHub App.
3. Set **Content Directory** to `mintlify/` in the project settings.
4. Site goes live at `https://mediaite-ghostink.mintlify.app`.
5. Optional: configure a custom domain (e.g., `docs.<chosen-domain>`).

### 8. Add CI for broken-link checks

Create `.github/workflows/mintlify-lint.yml`:

```yaml
name: Mintlify Lint
on:
  pull_request:
    paths:
      - "mintlify/**"
      - "docs/**"
      - "prompts/**"
      - "src/forensics/**"
      - "scripts/build_mintlify_content.py"
  workflow_dispatch:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: uv sync
      - run: uv run python scripts/build_mintlify_content.py --out mintlify
      - run: npm i -g mint
      - run: cd mintlify && mint broken-links
```

This must NOT be added to `.github/workflows/deploy.yml` (which is the Quarto → GitHub Pages deploy and remains untouched). Mintlify hosting handles its own deploy via the GitHub App; CI here is only lint/preview.

### 9. Update repo-level docs

- **Append to `docs/RUNBOOK.md`** under a new "Mintlify (developer docs)" section: the local-dev command (`cd mintlify && mint dev`), the build-content command (`uv run python scripts/build_mintlify_content.py --out mintlify`), the live URL once known, and a one-line statement clarifying that Mintlify is for developer/component docs and the Quarto report at `https://<owner>.github.io/mediaite-ghostink/` is the unrelated client-facing deliverable.
- **Append to `HANDOFF.md`** with a completion block per the existing template, listing all files created/edited, the maintainer-action checklist (Mintlify project creation, content-directory setting, optional custom domain), and any unresolved decisions.
- **Do NOT modify** `docs/DEPLOYMENTS.md` to mention Mintlify deployment unless you also explicitly preserve and reinforce the existing Quarto/GitHub Pages section. If you touch this file, the edit must add a new "Developer documentation (Mintlify)" subsection that begins with the sentence: *"Mintlify hosts the developer/component documentation. It is independent of the bound forensic report, which is built by Quarto and deployed separately."*

## Acceptance criteria

The fix is **complete** when all of the following hold:

1. `mintlify/` exists at the repo root with `docs.json`, the introduction, quickstart, architecture overview, and at least one component page per navigation group.
2. `scripts/build_mintlify_content.py` exists and runs to completion. Re-running it is idempotent (no spurious diffs on a clean tree).
3. `cd mintlify && mint dev` serves a working local site at `http://localhost:3000` with all navigation entries resolvable.
4. `cd mintlify && mint broken-links` exits 0.
5. `.github/workflows/mintlify-lint.yml` exists and is valid YAML.
6. `docs/RUNBOOK.md` has a new Mintlify section with the developer/component scoping statement.
7. `HANDOFF.md` has a completion block including the maintainer checklist for Mintlify hosted setup.
8. **Quarto invariants:** `quarto.yml`, `index.qmd`, every file under `notebooks/`, every file under `data/reports/`, and `.github/workflows/deploy.yml` are byte-identical to their pre-task state. `git diff --stat` confirms zero touched lines in those paths.
9. The Mintlify site has both a footer/global anchor and an introduction `<Note>` linking to the Quarto-deployed forensic report. The two sites cross-reference each other.
10. No file inside `mintlify/` references `docs.json` content from anywhere outside `mintlify/`, except via the build script's read-from-source pattern.

## Verification commands

```bash
# Step 1 — prove Quarto pipeline is untouched
git diff --stat -- quarto.yml index.qmd notebooks/ data/reports/ .github/workflows/deploy.yml
# expected: empty output (zero changed lines)

# Step 2 — content build is reproducible
uv run python scripts/build_mintlify_content.py --out mintlify
git diff --stat -- mintlify/
# inspect: no spurious diffs after a clean rebuild

# Step 3 — local site builds
cd mintlify && mint dev &
DEV_PID=$!
sleep 5
curl -fs http://localhost:3000 > /dev/null && echo "OK: dev site responds"
kill $DEV_PID

# Step 4 — broken-link check
cd mintlify && mint broken-links

# Step 5 — workflow YAML lint
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/mintlify-lint.yml'))" && echo "OK: workflow yaml"

# Step 6 — confirm Mintlify navigation entries all have backing MDX files
python3 -c "
import json, pathlib
cfg = json.load(open('mintlify/docs.json'))
def walk(node):
    if isinstance(node, dict):
        for v in node.values(): yield from walk(v)
    elif isinstance(node, list):
        for v in node: yield from walk(v)
    elif isinstance(node, str):
        yield node
pages = [p for p in walk(cfg.get('navigation', {})) if '/' in p or p in ('introduction','quickstart')]
missing = [p for p in pages if not (pathlib.Path('mintlify')/(p+'.mdx')).exists() and not (pathlib.Path('mintlify')/(p+'.md')).exists()]
print('missing:', missing or 'none')
"
```

Capture each command's output for the HANDOFF block.

## Out of scope (explicit prohibitions)

The following are absolutely NOT part of this task. If any of them appear in the diff, the work is rejected.

- **Any** modification to `quarto.yml`, `index.qmd`, the Quarto preview/build path, or files under `notebooks/`. The Quarto book is the bound forensic report; Mintlify is for developer docs only. They are separate deliverables for separate audiences.
- **Any** modification to `data/reports/` content. Quarto owns that directory.
- **Any** modification to `.github/workflows/deploy.yml` (the existing Quarto → GitHub Pages deploy). Mintlify deploys via its own GitHub App, separately.
- Migrating, replacing, or "consolidating" the Quarto report into Mintlify. Do not propose this.
- Hosting the Quarto-rendered HTML inside Mintlify as static assets.
- Editing the analysis stage code, feature extractors, the data model, `config.toml` thresholds, or stage boundaries.
- Adding Mintlify content to `docs/` or any directory other than `mintlify/`. The new content tree must live in `mintlify/`.

## Rollback

If the Mintlify site does not deploy or causes confusion downstream:

1. `git revert` the commits creating `mintlify/`, `scripts/build_mintlify_content.py`, and `.github/workflows/mintlify-lint.yml`.
2. Disconnect the Mintlify GitHub App from the repo (manual maintainer step in Mintlify dashboard).
3. The Quarto deploy is unaffected and continues to publish the bound report at `https://<owner>.github.io/mediaite-ghostink/`. This is the rollback safety net.

## Constraints from `AGENTS.md` / `CLAUDE.md`

- Stage boundaries are sacred. This task only touches the *documentation* layer; no stage code changes.
- All Python execution via `uv run`.
- `HANDOFF.md` update is required before reporting complete.
- If the same Mintlify CLI or build error repeats 3+ times, append a Sign to `docs/GUARDRAILS.md` per the failure-pattern policy.
- Respect the `prompts/` library contract: this prompt itself follows the contract; do not break it for any prompt-library files generated into `mintlify/prompts/`.

## Deliverables

A single PR (or clean staged-changes state) containing:

- `mintlify/docs.json`
- `mintlify/introduction.mdx`, `mintlify/quickstart.mdx`, `mintlify/architecture/*.mdx`, hand-authored component pages
- `mintlify/_templates/component.mdx`
- `scripts/build_mintlify_content.py`
- `.github/workflows/mintlify-lint.yml`
- New section in `docs/RUNBOOK.md`
- New completion block in `HANDOFF.md`

The PR description must include:

- The `git diff --stat` output for `quarto.yml`, `notebooks/`, `data/reports/`, and `.github/workflows/deploy.yml` (must be empty — proof the Quarto pipeline is untouched).
- The maintainer-action checklist for Mintlify hosted setup (sign up, GitHub App, content directory).
- The chosen GitHub `<owner>` value used throughout `docs.json`.
- Output of `mint broken-links` (must be clean).
