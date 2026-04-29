# HANDOFF

## Handoff Protocol

Every handoff should include:

1. Current status (`Complete`, `Partial`, or `Blocked`)
2. Exact command evidence used for verification
3. Files changed and rationale
4. Known risks and recommended next actions

Agents: append a new block below using this template after every multi-step task.

---

## Template (copy this for each new entry)

<!--
### [Task Title]
**Status:** Complete | Partial | Blocked
**Date:** YYYY-MM-DD
**Agent/Session:** [identifier]

#### What Was Done
- [Concise list of changes]

#### Files Modified
- `path/to/file` — [why]

#### Verification Evidence
```text
[paste the commands you ran and a summary of output]
```

#### Decisions Made
- [Key choices and rationale]

#### Unresolved Questions
- [Anything left open]

#### Risks & Next Steps
- [What should the next operator know or do]
-->

---

## Completion Log


> **History:** Older completion blocks live in [`docs/archive/handoff-history.md`](docs/archive/handoff-history.md). When this file grows past roughly 200 lines of log content, archive older blocks there in the same change set.

### Run 13 follow-up — inline review (parser, refresh, analyze CLI, settings, config audit)

**Status:** Complete  
**Date:** 2026-04-29  
**Agent/Session:** Cursor agent

#### What was done

- **REST parser:** `extract_article_text_from_rest` now runs `_strip_stray_angle_brackets` after sanitize so malformed fragments (e.g. a lone `<`) do not survive in plain text; satisfies `test_parser_rest_fuzz` idempotence + no-`<`/`>` invariants.
- **`refresh.py`:** Comment on `__all__` for patch targets; split `_run_isolated_author_parallel_jobs`; refactored `run_parallel_author_refresh` into helpers with docstring; parallel analyze path seeds audit / `run_metadata` like serial paths.
- **`analyze_dispatch.py`:** `_conflicting_analyze_flags` + validation in `_compare_only_or_parallel_early_exit` for invalid flag mixes (`--compare` with other stages; `--parallel-authors` with serial stages).
- **`analyze_models.py`:** Docstring on `AnalyzeContext.build`.
- **`config_cmd.py`:** JSON mode emits `{"status":"ok","diffs":[...],"count":N}` when overrides exist (no prose lines).
- **`settings.py`:** `mode="before"` mirror: when `survey` has `excluded_sections` and `features` is missing, inject `features` from survey.
- **`per_author.py`:** Polars LazyFrame pipeline for `_clean_feature_series` (ruff-formatted).
- **`test_parser_rest_fuzz.py`:** Stronger assertions + sentinel-preservation Hypothesis test.

#### Files modified

- `src/forensics/scraper/parser.py`, `tests/unit/test_parser_rest_fuzz.py`
- `src/forensics/analysis/orchestrator/refresh.py`, `per_author.py`
- `src/forensics/cli/analyze_dispatch.py`, `analyze_models.py`, `config_cmd.py`
- `src/forensics/config/settings.py`

#### Verification

```text
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/ -v --tb=line -q
```

1095 passed, 4 skipped (TUI), 1 xfailed; coverage 80.44% (meets fail-under).

#### Risks and next steps

- Stripping `<`/`>` in the REST path only removes markup-like characters from **flattened** text; legitimate angle brackets in article prose are rare for this corpus. If needed, narrow to known-malformed patterns only.

### Run 13 — Code review + refactoring plan (config, CLI, orchestrator)

**Status:** Complete  
**Date:** 2026-04-29  
**Agent/Session:** Cursor agent

#### What was done

- **RF-DRY-001:** `CONFIG_HASH_EXTRA` in `src/forensics/config/constants.py`; replaced repeated `json_schema_extra` dicts in `analysis_settings.py` and `settings.py`.
- **RF-DRY-002 / P3-SEC-001:** `worker_errors.py` with recoverable-exception policy; `parallel.py` / `comparison.py` updated; `RuntimeError` included so isolated-refresh tests still pass.
- **RF-DRY-003:** `survey.excluded_sections` canonical; `mode="before"` validator on `ForensicsSettings` mirrors into `features` (dict and model init).
- **P2-ARCH-001:** `--verify-raw-archives/--no-verify-raw-archives`, `--log-all-generations/--no-log-all-generations` on analyze; wired via `AnalyzeCustodyParams`.
- **P3-SEC-002:** `_METADATA_INGEST_RECOVERABLE` narrowed to `IntegrityError` + `OperationalError` (not all `sqlite3.Error`).
- **P3-TEST-001:** `tests/unit/test_parser_rest_fuzz.py` for `extract_article_text_from_rest`.
- **P3-PERF-001:** Polars-native `_clean_feature_series` in `per_author.py`.
- **RF-COMPLEXITY-001:** `analyze_models.py`, `analyze_dispatch.py`, `analyze_section.py`; trimmed `analyze.py`.
- **RF-COMPLEXITY-002:** `parallel_shared.py`, `refresh.py`, slim `parallel.py` + lazy `import_module` re-exports for patch surface.
- **RF-SMELL-002:** Nested `AnalyzeRequest` (`stages`, `baseline`, `custody`); `pipeline.py` and tests updated.
- **P2-CQ-002:** `forensics analyze run` and `forensics analyze compare-only` subcommands.
- **P2-CQ-001 / RF-SMELL-003:** `forensics config audit`; flat `[analysis]` deprecation warning in `compat_analysis.py` (once per process); ADR-017 note.
- **RF-SMELL-001:** `ForensicsSettings` shortcuts `pelt`, `bocpd`, `convergence`, `content_lda`, `hypothesis`, `embedding`.
- **RF-ARCH-001:** Docstrings in `runner.py` and `analyze_dispatch.py` cross-referencing CLI vs `run_full_analysis`.

#### Files modified (high level)

- `src/forensics/config/` (`constants.py`, `settings.py`, `compat_analysis.py`, `analysis_settings.py`)
- `src/forensics/cli/` (`analyze.py`, `analyze_models.py`, `analyze_dispatch.py`, `analyze_section.py`, `analyze_options.py`, `config_cmd.py`, `__init__.py`)
- `src/forensics/analysis/orchestrator/` (`parallel.py`, `parallel_shared.py`, `refresh.py`, `worker_errors.py`, `per_author.py`, `comparison.py`, `runner.py`)
- `src/forensics/scraper/crawler.py`, `tests/unit/test_parser_rest_fuzz.py`, `tests/unit/test_config_audit.py`, `tests/unit/test_analyze_compare.py`, `tests/test_preregistration.py`, `tests/unit/test_settings.py`, `scripts/merge_embedding_manifest_shards.py` (E501 wrap)
- `docs/RUNBOOK.md`, `docs/adr/017-analysis-config-change-control.md`, `src/forensics/pipeline.py`

#### Verification

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/ -q --no-cov
```

All tests passed (4 skipped TUI, 1 xfail section-residualize).

#### Risks and next steps

- **Parallel refresh tests** must patch `forensics.analysis.orchestrator.refresh._validate_and_promote_isolated_outputs` (implementation lives in `refresh.py`).
- **ForensicsSettings** excluded-sections mirroring uses `mode="before"` so pydantic-settings applies the merged dict correctly.
- Consider migrating internal code to `settings.hypothesis` etc. incrementally; accessors are additive only.

### Run 12 — TASK-6 / TASK-7 / TASK-8 (patch surface, config compat, parallel dedup + coverage)

**Status:** Complete  
**Date:** 2026-04-27

#### What was done

- **TASK-6:** Expanded `forensics.analysis.orchestrator` module docstring with maintainer rules for `_PATCH_TARGETS` vs `__all__`; added `test_patch_targets_subset_of_all_exports`, `test_patch_surface_tests_track_patch_targets`, `test_patch_targets_modules_nonempty` in `tests/unit/test_orchestrator_patch_surface.py`.
- **TASK-7:** Added ADR-017 (AnalysisConfig change control; no `HashableField` — governance + compat split); moved flat TOML lift / `_FLAT_TO_GROUP` / `_GROUP_ATTRS` into `src/forensics/config/compat_analysis.py` with `analysis_settings` importing from it; amended ADR-016 references.
- **TASK-8:** Factored `_run_repo_per_author_pipeline_with_artifacts` in `parallel.py` for `_per_author_worker` and `_isolated_author_worker` (isolated path keeps `emit_success_log=False` for log parity); added root `coverage-tui.toml` and RUNBOOK § item 7 for `pytest --cov-config=coverage-tui.toml` when TUI extra is installed.

#### Files modified

- `src/forensics/analysis/orchestrator/__init__.py`, `parallel.py`
- `src/forensics/config/compat_analysis.py` (new), `analysis_settings.py`
- `docs/adr/017-analysis-config-change-control.md` (new), `docs/adr/016-analysis-config-nesting.md`, `docs/RUNBOOK.md`
- `tests/unit/test_orchestrator_patch_surface.py`, `coverage-tui.toml` (new), `HANDOFF.md`

#### Verification

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/ -q
uv run pytest tests/integration/test_parallel_parity.py -v --no-cov -q
uv run pytest tests/unit/test_config_hash.py -v --no-cov -q
```

Full suite: **passed** (1 known xfail); parallel parity: **3 passed**. GitNexus MCP server not available in this Cursor session; run upstream `impact` on edited symbols before merge when enabled.

#### Unresolved / next steps

- None for this slice.

---

### Pipeline B default, config_hash gate, direction concordance scoping, embedding compare parity

**Status:** Complete  
**Date:** 2026-04-27  
**Agent/Session:** Cursor agent (plan slice: doc-hash-migration, integration-hash-test, direction-concordance-filter, comparison-embedding-propagate, probability-trajectory-verify)

#### What was done

- **RUNBOOK:** Documented why `pipeline_b_mode` participates in `config_hash`, symptoms (`Analysis artifact compatibility failed` / stale hashes), and remediation (full `forensics analyze` cohort vs `pipeline_b_mode = "legacy"` to match old artifacts).
- **Integration:** `tests/integration/test_analysis_config_hash_gate.py` asserts `validate_analysis_result_config_hashes` returns failure and `_validate_compare_artifact_hashes` raises `ValueError` on mismatched `*_result.json` `config_hash`.
- **Direction concordance:** `classify_direction_concordance` filters hypothesis rows to `convergence_window.features_converging` when that list is non-empty; unit tests updated + new scoping test; Phase 17 golden fixtures already align feature names with `features_converging` (no golden JSON edit).
- **Compare path:** Introduced `orchestrator/embedding_policy.py` with `embedding_fail_should_propagate` (avoids `parallel` ↔ `comparison` import cycle); `_iter_compare_targets` re-raises embedding drift/revision errors in confirmatory mode; `parallel.py` uses the shared helper; unit tests in `test_comparison_target_controls.py`.
- **Pipeline C:** Comment on equal-weight monthly means and sparse Binoculars months in `probability_trajectories.py`; unit test `test_sparse_binoculars_months_pipeline_c_score_finite` for length inequality + finite score.

#### Files modified

- `docs/RUNBOOK.md` — `pipeline_b_mode` / `config_hash` operator subsection
- `HANDOFF.md` — this block
- `src/forensics/analysis/orchestrator/embedding_policy.py` — new shared policy
- `src/forensics/analysis/orchestrator/parallel.py`, `comparison.py` — embedding propagation
- `src/forensics/models/report.py` — concordance scoping
- `src/forensics/analysis/probability_trajectories.py` — comments
- `tests/integration/test_analysis_config_hash_gate.py` — new
- `tests/unit/test_direction_concordance.py`, `test_comparison_target_controls.py`, `test_probability_trajectories.py` — tests

#### Verification evidence

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/integration/test_analysis_config_hash_gate.py tests/unit/test_direction_concordance.py tests/unit/test_comparison_target_controls.py tests/unit/test_probability_trajectories.py tests/integration/test_phase17_classification.py -v --no-cov
```

#### Decisions made

- **Embedding policy module:** `comparison.py` cannot import `parallel.py` (existing `parallel` → `comparison` edge); policy lives in `embedding_policy.py` instead of duplicating logic.

#### Unresolved questions

- None.

#### Risks & next steps

- **GitNexus:** `gitnexus_impact` / `gitnexus_detect_changes` were not run (GitNexus MCP server not available in this Cursor session). Run on `classify_direction_concordance`, `_iter_compare_targets`, and `embedding_fail_should_propagate` before merge when enabled.
- Operators with pre–percentile-default `*_result.json` should follow the new RUNBOOK subsection before compare/report.

---

### Full confirmatory re-run for all 12 configured authors → fresh PDF report
**Status:** Complete
**Date:** 2026-04-28
**Agent/Session:** Claude Code (Opus 4.7, 1M context)

#### What Was Done
- Re-ran the full forensic pipeline end-to-end for all 12 configured authors and produced a confirmatory-mode PDF report.
- Diagnosed and patched a manifest-stomping bug in `forensics extract --author <slug>` that would have silently destroyed the manifest under any multi-call workflow.
- Added per-author manifest shards plus a merge step; verified shards accumulate correctly and the canonical manifest is rebuilt before `forensics analyze`.
- Recovered from a bash `set -e` gotcha (loop body inside `&&` chain) that left an ostensibly-killed extract loop racing a replacement chain.
- Captured both failure patterns as Signs in `docs/GUARDRAILS.md`.

#### Files Modified
- `src/forensics/features/pipeline.py` — write per-author manifest shards (`<slug>_manifest.jsonl`) when `author_slug` is set; legacy single-write path retained for unscoped runs.
- `scripts/merge_embedding_manifest_shards.py` — new helper; merges shards + canonical (last-wins by `article_id`), atomically rewrites canonical manifest, deletes shards.
- `docs/GUARDRAILS.md` — appended two Signs (`set -e` for-loop/`&&` interaction; pre-patch manifest-stomping behavior of `extract --author`).
- `data/reports/Mediaite-writing-analysis-—-technical-report.pdf` — final confirmatory PDF (90 KB, mtime 2026-04-28 01:33:03 CDT).
- `data/analysis/run_metadata.json`, `comparison_report.json`, all per-author `*_result.json` / `*_changepoints.json` / `*_convergence.json` / `*_hypothesis_tests.json` / `*_drift.json` etc. — fresh artifacts.
- `data/embeddings/manifest.jsonl` — 49,126 rows / 12 distinct `author_id`s (canonical, post-merge).
- `data/embeddings_archive_20260428T002003Z/` — auto-archived prior embeddings (revision-pin mismatch).
- `data/embeddings/manifest.jsonl.pre-revrepin-20260427T191951` — operator-side manifest snapshot (pre-rerun rollback breadcrumb; safe to delete now).
- `data/logs/path_b_parallel_20260427T220619.log` — main run log; per-author logs at `data/logs/extract_<slug>.log`.

#### Verification Evidence
```text
$ tail -2 data/logs/path_b_parallel_20260427T220619.log
Tue Apr 28 01:33:03 CDT 2026
EXIT=0

$ stat -f '%Sm %z %N' data/reports/*.pdf
Apr 28 01:33:03 2026 92234 data/reports/Mediaite-writing-analysis-—-technical-report.pdf

$ uv run python -c 'import json; ids=set(); n=0
> for line in open("data/embeddings/manifest.jsonl"):
>     line=line.strip()
>     if line: ids.add(json.loads(line)["author_id"]); n+=1
> print(f"rows={n} authors={len(ids)}")'
rows=49126 authors=12

$ jq '{exploratory, allow_pre_phase16_embeddings, preregistration_status, config_hash}' \
    data/analysis/run_metadata.json
{
  "exploratory": false,
  "allow_pre_phase16_embeddings": false,
  "preregistration_status": "ok",
  "config_hash": "6bffd326f0074688514c3d595ad2bc6065725ea17e783489"
}
```

Total wallclock: 22:06:19 → 01:33:03 = **3 h 26 min 44 s** (4-way parallel extract via `xargs -P 4` + merge + `forensics analyze --max-workers 4` + Quarto/lualatex PDF render, 3 passes).

#### Decisions Made
- **Path B over A.** Delivered confirmatory-mode report (`exploratory=false`) instead of taking the faster A-mode shortcut, because the report is preregistration-clean and matches the locked thresholds at 2026-04-26T09:46:47.
- **Per-author manifest shards over fcntl locking.** Cleaner — each writer owns its own path; the merge step is a single-process operation. Reader (`read_embeddings_manifest`) needed no changes because last-wins-by-`article_id` semantics already match.
- **Killed alex-griffing's 95-min run mid-extract** to land the patch and restart with parallelism. Net savings on remaining 11 authors outweighed the loss.
- **4-way parallel** chosen as the sweet spot for an M1 Max (10 cores, 64 GB, single MPS GPU). Measured ~36% wall slowdown per author vs serial baseline (much better than my 30% MPS-contention worst case); effective ~3× speedup.
- **Skipped re-extracting `ahmad-austin`** — its rows from the (failed) earlier sequential run were already in the canonical manifest and its `batch.npz` was on disk. The merge step preserved them.

#### Unresolved Questions
- **Section-residualized sensitivity flags** (in `run_metadata.json`): 4 authors have `downgrade_recommended=true` (`ahmad-austin`, `colby-hall`, `isaac-schorr`, `sarah-rumpf`). Their primary findings drop substantially when section composition is residualized, suggesting section bias inflates the raw signal. Worth scrutinizing in the narrative before client delivery.
- **CLI behavior cleanup (deferred):** `forensics extract` (no `--author` flag) iterates all 505 DB authors via `list_articles_for_extraction(author_id=None)`, while `resolve_author_rows(author_slug=None)` returns only the 12 configured authors. The two are inconsistent. `forensics analyze` already scopes to configured authors when no `--author` is given. Worth a separate PR to align `extract`'s default scope with `analyze`'s — would let a single `forensics extract` call replace the 12 sequential `--author` invocations.
- **Manifest-shard cleanup is destructive.** `merge_embedding_manifest_shards.py` deletes shards after merge. If a multi-author run is interrupted between extract and merge, partial state requires manual cleanup. Consider keeping shards under `data/embeddings/_shards/` with a configurable retention policy.

#### Risks & Next Steps
- **`pipeline.py` patch needs a unit test.** Currently no test asserts that scoped extract writes shards rather than the canonical manifest. Suggested: add to `tests/test_parquet_embeddings_duckdb.py` or a new `tests/unit/test_extract_manifest_shards.py` covering (a) shard-only write when `author_slug` is set, (b) canonical write when `author_slug` is `None` (legacy path), (c) merge script idempotency on no-shards.
- **GitNexus impact analysis was not run** on the patched `extract_all_features` symbol or the new merge script (per the project's GitNexus rule). Run before any subsequent edits to `pipeline.py`.
- **GUARDRAILS Sign: confirm `set -e` claim.** I asserted the bash POSIX/bash-specific behavior from observed evidence (the OLD chain continued past a killed inner command). The exact set-of-conditions where bash suppresses `set -e` inside compound commands is more nuanced than the Sign captures — if a future operator encounters edge cases, the canonical reference is `bash(1)` and POSIX 2.14.1.4. Keep the Sign as a heuristic.
- **`data/embeddings_archive_20260428T002003Z/` and `data/embeddings/manifest.jsonl.pre-revrepin-20260427T191951`** can be deleted once the new artifacts are blessed. Combined ~hundreds of MB.
- **Operator hint:** If you ever re-run extract for a subset of authors after this point, use `forensics extract --author <slug>` (the patch makes that safe) followed by `uv run python scripts/merge_embedding_manifest_shards.py` before `forensics analyze`. Or, for a full corpus, run `forensics extract` (no flag) — that path still uses the legacy single-write semantics, which are correct when there's only one writer for the whole manifest.

---

### Root cleanup, README, and production readiness

**Status:** Complete  
**Date:** 2026-04-28  
**Agent/Session:** Cursor agent

#### What was done

- Archived historical `HANDOFF.md` completion log to [`docs/archive/handoff-history.md`](docs/archive/handoff-history.md); trimmed root `HANDOFF.md` to protocol + last three blocks + pointer; documented size discipline in [`AGENTS.md`](AGENTS.md).
- README: **At a glance**, **Five-minute smoke test**, `_quarto.yml` corrections, repository layout row, **Contributing** section; documentation table entries for `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/RUNBOOK.md`](docs/RUNBOOK.md): `_quarto.yml` wording; E2E bullet uses `_quarto.yml`.
- Moved root `TASK.md` to [`docs/TASK.md`](docs/TASK.md); updated [`docs/adr/ADR-003-agent-governance-and-hooks.md`](docs/adr/ADR-003-agent-governance-and-hooks.md); removed redundant `!TASK.md` from [`_quarto.yml`](_quarto.yml).
- Added [`LICENSE`](LICENSE) (MIT), [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md); [`pyproject.toml`](pyproject.toml) `license` + `Repository` URL.
- Moved [`docs/coverage-tui.toml`](docs/coverage-tui.toml) from repo root; updated RUNBOOK `pytest --cov-config` path.
- Removed local ephemeral files where present (`coverage.json`, `.coverage`, `_freeze/`, `.DS_Store`).

#### Files modified

- `HANDOFF.md`, `docs/archive/handoff-history.md` (new), `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`, `docs/TASK.md` (moved from root), `docs/adr/ADR-003-agent-governance-and-hooks.md`, `_quarto.yml`, `pyproject.toml`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/coverage-tui.toml` (moved from root)

#### Verification evidence

```bash
uv build
# sdist + wheel OK

uv run ruff check . && uv run ruff format --check .
uv run pytest tests/test_report.py -v --no-cov
```

#### Risks and next steps

- **License:** Root [`LICENSE`](LICENSE) is **MIT** with Abstract Data LLC copyright. If the org requires a different license, replace the file and `pyproject.toml` `license` metadata in one commit.
- GitNexus `impact` / `detect_changes` not run (no MCP server in this session); run before merge if your workflow requires it.
