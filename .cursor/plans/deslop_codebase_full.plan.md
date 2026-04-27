---
name: Deslop codebase (src + tests)
overview: Phased deslop of src/forensics and tests/ (comments, casts, nesting noise) with no behavior or contract changes; one PR per phase; GitNexus impact + detect_changes each PR. Phase detail, commands, and risk notes are in the body.
todos:
  - id: deslop-phase-0-baseline
    content: Phase 0 — Record BASE ref (main or release tag)
    status: completed
  - id: deslop-phase-0-churn
    content: Phase 0 — Churn report (git diff $BASE --stat -- src/ tests/) and prioritize Phases 1–3
    status: completed
  - id: deslop-phase-0-stop-list
    content: Phase 0 — Fill stop list (preregistration, AnalysisArtifactPaths, migrations) in To-dos below or PR
    status: completed
  - id: deslop-phase-1-cli
    content: Phase 1 — Deslop src/forensics/cli + CLI tests (validation in Phase 1 section)
    status: completed
  - id: deslop-phase-2-config
    content: Phase 2 — Deslop config, paths, preflight, preregistration + related tests
    status: completed
  - id: deslop-phase-3-storage
    content: Phase 3 — Deslop storage/repository (comments + dead code only; no schema edits)
    status: completed
  - id: deslop-phase-4-scraper
    content: Phase 4 — Deslop scraper (preserve scrape_errors / transient semantics)
    status: completed
  - id: deslop-phase-5-features
    content: Phase 5 — Deslop features pipeline + related tests
    status: pending
  - id: deslop-phase-6-analysis
    content: Phase 6 — Deslop analysis + orchestrator + parity tests
    status: pending
  - id: deslop-phase-7-reporting
    content: Phase 7 — Deslop reporting, survey, baseline, calibration, TUI + tests
    status: pending
  - id: deslop-phase-8-tests
    content: Phase 8 — Deslop remaining tests (do not weaken assertions)
    status: pending
  - id: deslop-gate-after-phase-1
    content: After Phase 1 merges — re-run churn on src/ + tests/ vs BASE; adjust phase order if needed
    status: pending
  - id: deslop-optional-testing-doc
    content: (Optional) Add deslop checklist bullets to docs/TESTING.md
    status: pending
  - id: deslop-optional-ci-type-ignore
    content: "(Optional) CI policy for new type: ignore in touched files"
    status: pending
isProject: false
---

# Plan: Repository-wide deslop (`src/` + `tests/`)

**Intent:** Remove AI-generated and inconsistent cruft (comments, casts, nesting, defensive noise) while **preserving behavior** and **stage/data contracts**. This plan follows the **deslop** skill guardrails: no unnecessary comments/casts/nesting, no drive-by refactors, no silent behavior changes, minimal diffs.

**Out of scope (do not “deslop” into these):**

- Changing pipeline stage boundaries, public JSON/Parquet schemas, or analysis thresholds without an ADR or explicit approval.
- Rewriting `prompts/` versioned artifacts (immutable releases); only operational docs if separately approved.
- Broad renames or structural moves (use a dedicated refactor plan + GitNexus `rename` workflow).

---

## Principles (load-bearing)

1. **Correctness > cleanliness.** If a comment or guard exists for forensic/traceability reasons, keep it or replace with a shorter factual line—not deletion by default.
2. **Slice, don’t tsunami.** One mergeable unit per phase (directory or theme), full test pass for that slice.
3. **Diff-first.** Every slice starts from `git diff <base> -- <paths>` (usually `main` or last release tag) so deslop targets **churn**, not stable legacy modules—unless a module is explicitly flagged.
4. **No new dependencies** for deslop; use stdlib + existing tooling (`uv run ruff`, `uv run pytest`).

---

## To-dos

**Cursor plan tasks** are the `todos:` list in the **YAML frontmatter** at the very top of this file. Update `status` there (`pending` → `in_progress` → `completed`) as work ships; the Plan UI reads that list (same pattern as [cli_agent-readiness](cli_agent-readiness_3878934e.plan.md)).

**One PR per phase** unless split per **PR and review strategy** (later in this doc). Scope, commands, and risk for each phase are in the **Phase 0** … **Phase 8** sections below—do not duplicate long checklists here.

### Stop list (Phase 0 — edit as you inventory)

High-touch paths; treat as higher risk even for comment-only edits (add/remove rows):

- [ ] *(e.g. preregistration lock / `data/preregistration/` workflow)*
- [ ] *(e.g. `AnalysisArtifactPaths`, `paths.py`)*
- [ ] *(e.g. `src/forensics/storage/migrations/*`)*

### Definition of done (every PR — copy into PR description)

- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass.
- [ ] `uv run pytest tests/ -v` passes (or documented subset + full suite before release train).
- [ ] No change to default CLI JSON envelope shape or exit codes without coordinated doc updates.
- [ ] GitNexus: **impact** (upstream) on each edited non-trivial symbol; **detect_changes** before merge.
- [ ] If operational behavior changed: append `docs/RUNBOOK.md` / `HANDOFF.md` per `AGENTS.md` (else omit).

---

## Phase 0 — Baseline and inventory (LOW)

**Goal:** Know where slop concentrates; avoid blind edits.

| Step | Action |
|------|--------|
| 0.1 | Record base ref: `BASE=main` (or `vX.Y.Z` if deslopting a release branch). |
| 0.2 | Churn report: `git diff $BASE --stat -- src/ tests/` — sort by lines changed; top 15 directories/files are Phase 1–3 priority. |
| 0.3 | Optional: `git diff $BASE --name-only -- src/ tests/ \| sort \| uniq -c` style grouping by top-level folder (`cli/`, `analysis/`, …). |
| 0.4 | Document “stop words”: files touching preregistration locks, `AnalysisArtifactPaths`, storage migrations—treat as **MEDIUM** default risk even for comment-only edits. |

**Validation:** No code changes required; optional checklist row in PR description.

---

## Phase 1 — CLI and agent-facing surface (LOW → MEDIUM)

**Paths:** `src/forensics/cli/**/*.py`, CLI-heavy tests `tests/unit/test_cli_*.py`, `tests/integration/test_cli*.py`

**Focus (deslop skill):**

- Module docstrings that restate Typer mechanics; redundant `# --- section ---` banners.
- `# type: ignore` / `Any` used only to satisfy decorators or dynamic attributes—prefer narrow `Protocol` + `cast`, or documented `noqa` with one-line rationale.
- Duplicate “help” prose between `epilog`, decorators, and docstrings—single source of truth.
- `try/except` that only wraps stable imports or known-safe paths—verify before removal.

**Risk:** **MEDIUM** for anything affecting exit codes, JSON envelopes, or `--output json` (agent contracts). Treat **HIGH** if changing documented exit codes or envelope keys—requires `docs/EXIT_CODES.md` and test updates in the same PR.

**Validation:**

```bash
uv run ruff check src/forensics/cli tests/unit/test_cli_*.py tests/integration/test_cli*.py
uv run ruff format --check src/forensics/cli tests/unit/test_cli_*.py tests/integration/test_cli*.py
uv run pytest tests/unit/test_cli_*.py tests/integration/test_cli.py tests/integration/test_cli_scrape_dispatch.py -q --no-cov
```

**GitNexus:** Before editing non-trivial functions, run **impact** upstream on the symbol (per `AGENTS.md` / `.cursor/rules/gitnexus-before-refactor.mdc`).

---

## Phase 2 — Config, paths, preflight (MEDIUM)

**Paths:** `src/forensics/config/`, `src/forensics/paths.py`, `src/forensics/preflight.py`, `src/forensics/preregistration.py`, related tests (`test_preflight.py`, `test_preregistration.py`, `test_settings.py`, `unit/test_config_hash.py`, …)

**Focus:**

- Verbose docstrings duplicating `config.toml` comments.
- Redundant defensive checks already enforced by Pydantic validators or preflight—remove only when a test proves redundancy.

**Risk:** **MEDIUM** (mis-touched env or path logic breaks CI and local runs).

**Validation:**

```bash
uv run pytest tests/test_preflight.py tests/test_preregistration.py tests/unit/test_settings.py tests/unit/test_config_hash.py -q --no-cov
```

---

## Phase 3 — Storage and repository (MEDIUM → HIGH)

**Paths:** `src/forensics/storage/**/*.py`, `src/forensics/storage/migrations/*.py`, `tests/test_storage.py`, `tests/unit/test_repository_*.py`, `tests/integration/test_repository_*.py`

**Focus:**

- Comment noise in hot transaction paths; duplicate explanations of SQLite pragmas.
- Over-broad `except`—narrow to expected exception types only where tests cover failure modes.

**Risk:** **HIGH** for migrations and `repository.py` (data integrity). Deslop here = comments + obvious dead code **only** with migration/repository tests green; no schema edits under deslop banner.

**Validation:**

```bash
uv run pytest tests/test_storage.py tests/unit/test_repository_*.py tests/integration/test_repository_*.py -q --no-cov
```

---

## Phase 4 — Scraper and fetcher (MEDIUM)

**Paths:** `src/forensics/scraper/**/*.py`, related root/integration tests (`test_scraper.py`, `test_fetcher_*.py`, `unit/test_scraper_*.py`, …)

**Focus:**

- Nested conditionals with repeated logging—early returns **only** if behavior and log messages stay equivalent (tests + spot-check logs).
- Transient error classification: do not “simplify” branches that map to `scrape_errors.jsonl` semantics without `tests/unit/test_scrape_transient_classification.py` (and friends).

**Validation:** Full scraper unit subset + any integration tests that mock HTTP (grep `scraper` in `tests/` for the list to freeze in the PR).

---

## Phase 5 — Features pipeline (MEDIUM)

**Paths:** `src/forensics/features/**/*.py`, `tests/test_features.py`, `tests/unit/test_features_*.py`, `test_embedding_*.py` as applicable

**Focus:**

- Long module preambles; redundant `# complexity: justified` without algorithm context—either one line of justification or remove.
- `LazyFrame` chains: deslop means **comments**, not re-chaining for style.

**Validation:** `uv run pytest tests/test_features.py tests/unit/test_features_*.py -q --no-cov` (expand glob as shell supports, or run `tests/unit` subset for features).

---

## Phase 6 — Analysis core and orchestrator (MEDIUM → HIGH)

**Paths:** `src/forensics/analysis/**/*.py`, `tests/test_analysis.py`, `tests/unit/test_statistics*.py`, `tests/unit/test_changepoint*.py`, `tests/unit/test_orchestrator_*.py`, `tests/integration/test_parallel_parity.py`, …

**Focus:**

- Essay comments above stable formulas; duplicate parameter explanations already in `ForensicsSettings` / ADRs.
- Deep nesting: prefer early `continue`/`return` **only** with parity tests (numerical outputs must match).

**Risk:** **HIGH** for `changepoint.py`, `statistics.py`, `orchestrator/*`—small edits can change evidence outputs. Pair deslop with **determinism** tests already in tree; extend only if you discover missing coverage before a risky collapse.

**Validation:**

```bash
uv run pytest tests/test_analysis.py tests/unit/test_statistics.py tests/unit/test_orchestrator_patch_surface.py tests/integration/test_parallel_parity.py -q --no-cov
```

(Adjust list upward if a file touched has dedicated tests—use GitNexus **context** on the symbol.)

---

## Phase 7 — Reporting, survey, baseline, calibration, TUI (LOW → MEDIUM)

**Paths:** `src/forensics/reporting/`, `survey/`, `baseline/`, `calibration/`, `tui/`, matching tests.

**Focus:** Narrative duplication between docstrings and markdown templates; TUI copy that mirrors CLI help.

**Risk:** **LOW** for pure presentation; **MEDIUM** if survey gates or report section ordering affects downstream Quarto.

---

## Phase 8 — Tests-only pass (LOW)

**Paths:** `tests/**/*.py` not fully covered above.

**Focus:**

- Over-commented fixtures; redundant `try/except` in tests that should `pytest.raises`.
- Magic strings duplicated 10+ times—prefer module-level constants **only** if it improves clarity without widening assertion surface.

**Guardrail:** Do not weaken assertions or shrink parametrization “for readability.”

**Validation:** Targeted `pytest` per edited file’s imports (e.g. `uv run pytest path/to/test_foo.py`).

---

## Discovery cheatsheet (run per slice)

Use these to **find** candidates; human decides delete vs trim.

| Pattern | Command / idea |
|---------|------------------|
| Long added comment blocks | `git diff $BASE -- path \| rg '^\+.*#'` |
| Broad ignores | `rg 'type: ignore|noqa: E501' src/forensics tests` |
| `Any` | `rg ': Any|typing\.Any' src/forensics tests` |
| Bare or broad except | `rg 'except\\s*:|except Exception' src/forensics` (review manually) |
| Nested depth | Ruff `PLR0911` / `PLR0912` if enabled; else manual read of hotspots from churn stat |

---

## PR and review strategy

- **One PR per phase** (or half-phase if > ~400 LOC touched)—easier rollback and clearer review story.
- PR title prefix: `chore(deslop): phase N — <area>` (no `fix:` unless correcting a bug uncovered during deslop).
- Each PR description lists: base ref, paths, **explicit “no behavior change”** statement, tests run.

---

## Execution order (summary)

| Phase | Area | Default risk |
|-------|------|----------------|
| 0 | Inventory | LOW |
| 1 | CLI + CLI tests | LOW–MEDIUM |
| 2 | Config / preflight / preregistration | MEDIUM |
| 3 | Storage / repository | MEDIUM–HIGH |
| 4 | Scraper | MEDIUM |
| 5 | Features | MEDIUM |
| 6 | Analysis / orchestrator | MEDIUM–HIGH |
| 7 | Reporting / survey / baseline / TUI | LOW–MEDIUM |
| 8 | Remaining tests | LOW |

---

## Optional follow-up (not blocking deslop)

Tracked as the last two `todos` entries (`deslop-optional-*`) in YAML frontmatter.

---

## Approval gate

Do **not** start Phase 3+ in a single combined PR. Ship Phase 0–1 first; reassess churn stats after Phase 1 merges (remaining slop may shift).

When you are ready to execute, pick a **base ref**, run Phase 0.2, and open Phase 1 as the first implementation PR.