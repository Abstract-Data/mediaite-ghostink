---
name: Notebook alignment + client report
overview: Harden analyze for embedding drift, align defaults, wire Pipeline C from features, optional prereg CI — plus rewrite Quarto book copy for client delivery (no recommendations, no dev notes).
todos:
  - id: strict-drift-inputs
    content: "TASK-1: Non-exploratory hard-fail on missing/insufficient embeddings; align drift.py + per_author.py + CLI errors; integration tests"
    status: pending
  - id: percentile-default
    content: "TASK-2: Default HypothesisConfig.pipeline_b_mode to percentile; update prereg/hash tests and brief doc note"
    status: pending
  - id: wire-pipeline-c
    content: "TASK-3: Build ProbabilityTrajectory map from features.parquet; pass through run_full_analysis and parallel paths; tests"
    status: pending
  - id: prereg-ops-ci
    content: "TASK-4 (optional): RUNBOOK/CI checklist for preregistration lock before publication"
    status: pending
  - id: client-quarto-copy
    content: "TASK-5: Client-facing Quarto book — rewrite prose, strip recommendations and dev-note tone across chapters + generated narrative"
    status: pending
---

# Notebook–codebase alignment + client-facing report

## Policy (embedding strictness)

- **Non-exploratory** analyze must not silently accept missing embeddings / insufficient pairs for study authors. **Exploratory** keeps permissive logging + empty drift.

---

## TASK-1 — Strict embedding drift inputs (non-exploratory)

**Exec mode:** sequential  
**Model:** claude-sonnet-4-6  
**Est. tokens:** ~50K

1. Add typed failure (e.g. `EmbeddingDriftInputsError` in [`src/forensics/analysis/drift.py`](src/forensics/analysis/drift.py)).
2. In [`_load_drift_signals`](src/forensics/analysis/orchestrator/per_author.py): on `ValueError`/`OSError` from `load_article_embeddings`, **re-raise** when `not exploratory`; after load, if `not exploratory` and `len(pairs)<2`, raise.
3. Align [`load_drift_summary`](src/forensics/analysis/drift.py) and [`run_drift_analysis`](src/forensics/analysis/drift.py) for non-exploratory semantics.
4. Map exceptions in [`run_analyze`](src/forensics/cli/analyze.py) to stable exit codes.
5. Tests under `tests/integration/`; update units that assumed silent continuation.

**Execution:** GitNexus `impact` on edited symbols before changes.

---

## TASK-2 — `pipeline_b_mode` default to `percentile`

**Exec mode:** sequential after TASK-1  
**Model:** gpt-5-3-codex  
**Est. tokens:** ~10K

1. Change default in [`HypothesisConfig`](src/forensics/config/analysis_settings.py).
2. Update [`tests/test_preregistration.py`](tests/test_preregistration.py), [`tests/unit/test_config_hash.py`](tests/unit/test_config_hash.py), prereg fixtures if needed; note intentional hash shift.

---

## TASK-3 — Wire Phase 9 (Pipeline C) from `features.parquet`

**Exec mode:** sequential after TASK-2  
**Model:** claude-sonnet-4-6  
**Est. tokens:** ~50K–~200K

1. New helper: build [`ProbabilityTrajectory`](src/forensics/analysis/convergence.py) per slug from feature parquet (columns from [`probability_pipeline.py`](src/forensics/features/probability_pipeline.py): `mean_perplexity`, `perplexity_variance`, optional `binoculars_score`), aggregated to monthly series.
2. Call from [`_run_full_analysis_stage`](src/forensics/cli/analyze.py) or [`run_full_analysis`](src/forensics/analysis/orchestrator/runner.py); thread through [`parallel.py`](src/forensics/analysis/orchestrator/parallel.py).
3. Optional config `require_probability_inputs` (default false) for publication runs.
4. Tests for loader + optional convergence `pipeline_c_score` assertion.

**Execution:** GitNexus `impact` on `run_full_analysis`, `_run_full_analysis_stage`, new loader.

---

## TASK-4 — Preregistration lock (optional automation)

**Exec mode:** parallel / last  
**Model:** claude-haiku-4-5  
**Est. tokens:** ~10K

- Document operational checklist, or add CI smoke that fails when lock artifacts missing.

---

## TASK-5 — Client-facing Quarto book (work product tone)

**Exec mode:** sequential (can parallelize sub-edits by chapter in execution only)  
**Model:** claude-sonnet-4-6  
**Model rationale:** Editorial pass across many markdown cells + optional Python narrative strings.  
**Est. tokens:** ~50K–~200K

**Goal:** The rendered book ([`_quarto.yml`](_quarto.yml): [`index.qmd`](index.qmd) + [`notebooks/*.ipynb`](notebooks/)) reads as a **client deliverable**: neutral forensic language, no engineering backlog, no “recommendations” sections, no Phase/PR/`uv run` developer breadcrumbs unless strictly needed for reproducibility (and then moved to an appendix or footnote, not body copy).

### Scope

| Area | Action |
|------|--------|
| [`index.qmd`](index.qmd) | Reframe intro for external readers; remove “jump to chapter” meta that sounds internal if replaced by standard book foreword language. |
| [`notebooks/09_full_report.ipynb`](notebooks/09_full_report.ipynb) | Remove or replace **`cell-recommendations`** and any similar sections (e.g. G1 wiring, Phase 15 H2, serial run times). Replace with **findings / limitations / methods** appropriate for counsel or editorial review — not a punch list. |
| [`notebooks/00`–`08`](notebooks/) | Strip **“Phase context”**, **PR numbers**, **internal fix narratives** (e.g. “Phase 15 E2 (PR #67)”) from chapter headers and body. Consolidate methodology into plain-language **Methods** where the detail is legally/scientifically relevant; drop pure implementation history. |
| [`notebooks/11_calibration.ipynb`](notebooks/11_calibration.ipynb) | Excluded from `_quarto.yml` book chapters today — only edit if it is ever linked or rendered for clients. |
| Generated narrative | [`src/forensics/reporting/narrative.py`](src/forensics/reporting/narrative.py): review [`generate_evidence_narrative`](src/forensics/reporting/narrative.py) header (currently exposes `run_id`, `config_hash`, `author_slug` — decide client-appropriate identifiers: e.g. display name from config, shortened run id, or move hashes to a **Chain of custody** appendix). Review [`pipeline_b_diagnostics_block`](src/forensics/reporting/narrative.py) and [`PIPELINE_B_DIAGNOSTIC_NOTE`](src/forensics/reporting/narrative.py) for internal tone. |
| [`src/forensics/reporting/__init__.py`](src/forensics/reporting/__init__.py) | `_author_evidence_markdown` / `_summary_lines`: ensure per-author evidence pages match the same client tone when `--per-author` is used. |

### Acceptance criteria

- No section titled **Recommendations**, **Next steps (engineering)**, or equivalent backlog language in client-facing chapters.
- No **Phase N**, **PR #**, or **fix ticket** references in narrative body (methodology may cite **pre-registration** and **analysis thresholds** in neutral terms).
- Executive summary and conclusions describe **what was measured, what was observed, and stated limitations** — not what developers should build next.
- Tests that **pin exact narrative strings** (e.g. in `tests/unit/` for narrative) are updated to match revised copy.

### Validation

- `uv run forensics report --format html` (or `quarto render` from repo root) succeeds.
- Spot-check PDF/HTML for tone and absence of dev-only blocks.

---

## Validation (global)

- `uv run ruff check .` / `uv run ruff format .`
- `uv run pytest tests/ -v`
- GitNexus `detect_changes` before commit
