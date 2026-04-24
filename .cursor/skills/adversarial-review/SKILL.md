---
name: adversarial-review
version: 1.0.0
description: >
  Adversarial architecture review for Python data pipelines using Polars, DuckDB, SQLite,
  Pydantic v2, and sentence-transformers. Use to pressure-test designs, find failure vectors,
  or evaluate high-stakes decisions before committing. Trigger on: "adversarial review",
  "devil's advocate", "architecture critique", "what can go wrong", "Critic-Builder",
  "review my models/pipeline", "find the failure modes", "stress-test this design", or when
  model definitions, pipeline stages, or storage code is pasted alongside questions about
  correctness or design safety. Two paths: (1) full-stack risk scan across eight attack
  surfaces, or (2) Critic-Builder pair for a single scoped decision. Includes curated prompt
  templates and full runbook. Always use this skill — do not improvise adversarial review
  prompts from memory.
---

# Adversarial Python Pipeline Review

Adversarial technique for pressure-testing **Polars + DuckDB + SQLite + Pydantic v2 + sentence-transformers** pipeline architecture before committing to a design. Output is **critique only** — no auto-applied changes. All flagged risks require human triage.

---

## Stack Assumption

**Python 3.13 + Polars (LazyFrame-first) + DuckDB + SQLite + Pydantic v2 + sentence-transformers + Typer CLI + pydantic-settings**

Pipeline contract: `scrape → extract → analyze → report` (four sacred stages).

If the stack differs significantly, flag it before proceeding.

---

## Choose Your Path

| Scenario | Use |
|---|---|
| Pre-merge or broad spike review | **Path A — Full-Stack Review** |
| One specific design decision | **Path B — Critic-Builder Pair** |
| Highest-stakes (irreversible) decision | **Path C — Multi-Model + Synthesis** |

---

## Path A — Full-Stack Review

**When to use:** Before merging any PR touching model definitions, pipeline stages, storage layers, or feature extraction logic. Architecture spike validation. Onboarding new engineers to known failure vectors.

**Inputs needed:**
- Project directory tree
- Pydantic v2 model definitions (especially data models in `models/`)
- Pipeline stage code samples (scraper, features, analysis, reporting)
- Storage layer code (SQLite repository, Parquet persistence, DuckDB queries)

**Runbook:**
1. Ask user to paste directory tree + key model definitions (and pipeline code if available)
2. Load **Template 1** from `references/templates.md`
3. Run Template 1 with pasted content
4. Present ranked risk list; invite user to triage by likelihood x impact
5. Cross-check output against the **Pipeline Hardening Cross-Check** table below — flag any gaps the adversarial pass surfaced
6. Offer to run scoped follow-up templates (Template 2, 3, or 5) for noisy areas
7. Append **Blind Spots follow-up probes** from `references/templates.md` after initial output
8. If stage boundary violations found: recommend refactoring to restore stage isolation
9. If storage correctness issues found: recommend adding integration tests with fixture databases

**Output:** Ranked risk list per attack surface — failure mode, trigger condition, impact category, likelihood.

---

## Path B — Critic-Builder Pair

**When to use:** One specific, scoped architecture decision that will be hard to reverse. Examples: collapsing feature families into a single Parquet schema, changing embedding dimensions, merging pipeline stages, switching from LazyFrame to DataFrame, changing storage backend.

**Inputs needed:**
- One-paragraph description of the architecture decision under review (specific and scoped)
- Stack constraints confirmed (Polars / DuckDB / SQLite / Pydantic v2 / sentence-transformers)

**Runbook:**
1. Ask user to describe the decision in exactly one paragraph — specific and scoped
2. Load **Prompt A (Critic)** from `references/templates.md`
3. Run Prompt A; capture full output without editing
4. Load **Prompt B (Builder)** from `references/templates.md`
5. Run Prompt B with Critic output pasted in
6. Present accept/reject log; call out points of disagreement explicitly — those require human judgment
7. Do NOT auto-apply any mitigations from Builder output; do NOT propose a redesign
8. If Critic surfaces stage boundary issues: point to AGENTS.md stage contract

**Output:** Critic pass (ranked fragilities with production failure scenarios) + Builder pass (accept/reject with concrete mitigations or technical rebuttals).

> Keep Prompt A and Prompt B as **separate calls**. Do not combine — the model will self-validate and miss real risks.

---

## Path C — Multi-Model Synthesis (Highest-Stakes)

**When to use:** Decisions essentially irreversible at scale — fundamental model boundary strategy, embedding model changes, storage architecture pivots, stage boundary redesigns.

**Runbook:**
1. Run Path B (full Critic-Builder) with Claude as the first model
2. Run **Prompt A (Critic only)** with a second LLM (GPT-4o, Gemini) — user does this step externally
3. Load **Multi-Model Synthesis Prompt** from `references/templates.md`
4. Run Synthesis Prompt with both Critic outputs pasted in
5. The value is in **disagreements** — where models diverge is where human judgment is required
6. Produce final ranked risk list with disagreement resolutions

---

## Pipeline Hardening Cross-Check

After the adversarial pass, scan the output for gaps across these four categories. Flag any the adversarial review likely missed:

| Category | Key signals to watch for |
|---|---|
| **Data Integrity** | Silent schema drift between stages, Parquet files missing columns, SQLite to Polars type mismatches, embedding dimension mismatches, hash collisions in dedup |
| **Performance** | Premature `.collect()` on LazyFrames, full-table scans in DuckDB, N+1 patterns in article fetching, unbounded memory from loading all embeddings at once |
| **Correctness** | Feature extractors producing NaN/None that propagate silently, change-point detectors receiving unsorted timeseries, statistical tests on insufficient sample sizes, cosine similarity on zero vectors |
| **Reproducibility** | Non-deterministic ordering in Polars operations, floating-point accumulation in feature aggregations, missing random seeds in statistical methods, prompt version drift |

---

## Constraints / Safety

- **Output is critique only** — never apply suggested changes automatically
- **Builder is stack-constrained** — reject any Builder response proposing a full redesign
- **Human triages all flagged risks** before acting
- **Human resolves all Critic/Builder disagreements** before committing
- **Stage boundaries are sacred** — flag but do not propose merging stages
- High likelihood + Data Integrity = escalate immediately; do not defer

---

## Reference Files

- `references/templates.md` — All copy-paste-ready prompt templates (Template 1, 2, 3, 5, Prompt A, Prompt B, Synthesis, Blind Spots table)

Read `references/templates.md` before running any prompt template. Do not improvise the prompts from memory.
