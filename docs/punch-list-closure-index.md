# Punch-list closure index

**Source of truth (audit text):** [prompts/punch-list/current.md](../prompts/punch-list/current.md) (92 items; original wording retained for traceability).

**Phase 0 operational closure (table):** [prompts/punch-list/CHANGELOG.md](../prompts/punch-list/CHANGELOG.md) — section *Phase 0 closure (2026-04-26)*.

**Session evidence:** [HANDOFF.md](../HANDOFF.md) — search the Completion Log for `Punch-list`, `Phase 1 methodology`, `provenance-obs`, `tests-h`, `code-c-d`, `Ollama baseline`, and `Phase 0`.

This document maps each punch **ID** to the **primary deliverable** (code path, artifact, ADR, test, or documented gate). It does not replace the implementation plan; it is the repo-local **remediation index** promised in the full punch-list plan.

---

## Legend

| Tag | Meaning |
|-----|---------|
| **code** | Implemented in `src/forensics/` (and tests where noted) |
| **artifact** | Checked-in or generated under `data/` / `docs/` |
| **ADR** | Architecture decision / explicit gate |
| **test** | Regression or property test |
| **ops** | Operator command (see `docs/RUNBOOK.md`) |

---

## A — Methodology (M-01–M-23)

| ID | Tag | Primary evidence |
|----|-----|-------------------|
| M-01 | artifact + ops | `data/preregistration/preregistration_lock.json`; `uv run forensics lock-preregistration` |
| M-02 | artifact + ops | `data/ai_baseline/` (often gitignored); stub script `scripts/seed_phase0_ai_baseline_stubs.py`; RUNBOOK Phase 0; non-null `ai_baseline_similarity` in `*_drift.json` after drift |
| M-03 | artifact | `data/analysis/comparison_report.json` after `forensics analyze --compare` |
| M-04 | code + config | `config.toml` — exactly one `role = "target"` (`colby-hall`); AGENTS roster rules |
| M-05 | artifact | `data/preregistration/amendment_phase15.md` (Fix-F / Fix-G disclosure) |
| M-06 | code | `src/forensics/features/lexical.py` — marker list audit; `AI_MARKER_LIST_VERSION` |
| M-07 | code + test | Staff / pooled-byline handling — `tests/unit/test_shared_byline.py`, reporting SQL paths |
| M-08 | artifact + config | `config.external_controls.example.toml`; RUNBOOK external-control steps (full scrape human-gated) |
| M-09 | code + test | `src/forensics/analysis/statistics.py` — `apply_cross_author_correction`; `AnalysisConfig.enable_cross_author_correction`; `tests/unit/test_statistics.py`; preregistration lock fields in `src/forensics/preregistration.py` |
| M-10 | code | `src/forensics/models/analysis.py` — `effect_proxy` on `ChangePoint`; `src/forensics/analysis/changepoint.py`; `tests/unit/test_pelt_l2_swap.py` |
| M-11 | code + config | `src/forensics/analysis/changepoint.py`; `AnalysisConfig.bocpd_hazard_rate` / `bocpd_hazard_auto` in `src/forensics/config/settings.py` |
| M-12 | artifact | `docs/research/phase1_self_similarity_timeseries.md` |
| M-13 | artifact | Same research note — split-date / exploratory anchor caveat |
| M-14 | code + artifact | Section sensitivity — `src/forensics/analysis/orchestrator/sensitivity.py`, `data/analysis/sensitivity/` |
| M-15 | code | `run_hypothesis_tests` — `hypothesis_min_segment_n` (default ≥ 10) in `statistics.py` / `settings.py` |
| M-16 | artifact + code | Serial-correlation **caveat** — `docs/GUARDRAILS.md` (Agent-learned Signs); bootstrap CIs — `bootstrap_ci` / `run_hypothesis_tests` in `statistics.py` |
| M-17 | artifact + code + test | `data/labels/README.md`, `data/labels/article_labels.seed.jsonl`; `src/forensics/models/labels.py`; `tests/unit/test_article_labels.py` |
| M-18 | code | `src/forensics/analysis/convergence.py` — drift-only channel documented / bounded in implementation |
| M-19 | code | `src/forensics/analysis/convergence.py` — Pipeline A family score behavior |
| M-20 | code | `AI_MARKER_LIST_VERSION` + Parquet metadata — `src/forensics/features/lexical.py`, `src/forensics/storage/parquet.py` |
| M-21 | code | `src/forensics/features/content.py` — formula patterns / version metadata |
| M-22 | ADR | `docs/adr/ADR-008-observational-limits-and-causal-identification.md` |
| M-23 | artifact + script | `scripts/synthetic_null_pelt_calibration.py`; `data/provenance/synthetic_null_pelt_calibration.json`; RUNBOOK |

---

## B — Code quality (C-01–C-12)

| ID | Tag | Primary evidence |
|----|-----|-------------------|
| C-01 | code + test | `src/forensics/utils/datetime.py`; stable sort `timestamp`, `article_id`; `tests/unit/test_changepoint_same_day_determinism.py` |
| C-02 | code | `src/forensics/analysis/changepoint.py` — single median-imputation path for detectors |
| C-03, C-04 | code | `src/forensics/analysis/drift.py` — shared cosine / guard helpers |
| C-05 | code + test | `src/forensics/scraper/dedup.py`; `tests/unit/test_dedup_transaction_rollback.py` |
| C-06 | ADR | **`docs/adr/ADR-009-analyze-stage-sqlite-reads.md`** — **Accepted Option A** (2026-04-26); `ARCHITECTURE.md` + `RUNBOOK.md` document analyze-stage SQLite for identity only; no Repository removal |
| C-07 | code | `src/forensics/analysis/statistics.py` — Cohen’s d metadata dedupe |
| C-08 | code | `src/forensics/analysis/convergence.py` — narrowed legacy exception handling |
| C-09 | code | `src/forensics/analysis/orchestrator/parallel.py` — explicit multiprocessing spawn context |
| C-10 | code | `src/forensics/features/content.py` / pipeline — `AnalysisConfig` required where applicable |
| C-11 | artifact | Process-local cache behavior documented in module / RUNBOOK |
| C-12 | code | `src/forensics/features/content.py` / `pipeline.py` — deque batching for peer windows |

---

## C — Data / corpus (D-01–D-10)

| ID | Tag | Primary evidence |
|----|-----|-------------------|
| D-01 | code + test | `src/forensics/utils/hashing.py`; simhash normalization tests |
| D-02 | code | `src/forensics/utils/datetime.py`; repository read paths |
| D-03 | code | `src/forensics/scraper/coverage.py` — coverage summary artifact |
| D-04 | ops | Recompute simhashes per RUNBOOK if normalization changes |
| D-05 | code | `src/forensics/storage/parquet.py` — manifest last-row wins |
| D-06 | code | `src/forensics/storage/export.py` — export manifest + DB hash sidecar |
| D-07 | code | `src/forensics/utils/url.py` — year-only path segment handling |
| D-08 | code | `src/forensics/storage/repository.py` — JSON decode resilience |
| D-09 | artifact + code | `docs/RUNBOOK.md`; `last_scraped_at` in run metadata merge |
| D-10 | code | `AnalysisConfig` / per-author analysis — optional `analysis_min_word_count` |

---

## D — Config / infra (I-01–I-06)

| ID | Tag | Primary evidence |
|----|-----|-------------------|
| I-01 | code + test | `src/forensics/config/fingerprint.py`; `tests/unit/test_config_hash.py`, `tests/unit/test_scraping_config_hash.py` |
| I-02 | code | `src/forensics/config/settings.py`; `src/forensics/analysis/convergence.py` — adaptive window |
| I-03 | code | `baseline_embedding_count_sensitivity` (and related) on `AnalysisConfig` |
| I-04 | code | `src/forensics/analysis/drift.py` — embedding dim from settings |
| I-05 | code | `src/forensics/utils/disk.py` |
| I-06 | code | Parallel promotion completeness marker (orchestrator paths) |

---

## E — Reporting (R-01–R-09)

| ID | Tag | Primary evidence |
|----|-----|-------------------|
| R-01–R-09 | artifact | `data/reports/AI_USAGE_FINDINGS.md` (exploratory tone, caveats, tables); Quarto/report inputs as applicable |

---

## F — Provenance (P-01–P-05)

| ID | Tag | Primary evidence |
|----|-----|-------------------|
| P-01 | code + test | `src/forensics/utils/provenance.py` — mixed `config_hash` rejection; `tests/unit/test_provenance_validate.py` |
| P-02–P-04 | code | `include_in_config_hash` on LDA / bootstrap / UMAP seeds in `settings.py` |
| P-05 | code | `src/forensics/storage/parquet.py` — full embedding manifest scan |

---

## G — Observability (L-01–L-06)

| ID | Tag | Primary evidence |
|----|-----|-------------------|
| L-01 | code | `{slug}_convergence_components.json` — `paths.py`, `convergence.py`, orchestrator |
| L-02 | code | WARN empty comparison targets — `orchestrator/runner.py`, `parallel.py`, `comparison.py` |
| L-03 | code | Drift WARN when baseline layout empty — `drift.py` |
| L-04 | code | `crawl_summary.json` — `src/forensics/scraper/crawler.py` |
| L-05 | code | `{slug}_imputation_stats.json` — `changepoint.py`, `per_author.py` |
| L-06 | code | `src/forensics/preregistration.py` — WARNING when lock missing / unfilled |

---

## H — Tests (T-01–T-07)

| ID | Tag | Primary evidence |
|----|-----|-------------------|
| T-01 | test | `tests/unit/test_comparison_target_controls.py` |
| T-02 | test | `tests/unit/test_changepoint_same_day_determinism.py` |
| T-03 | test | `tests/unit/test_ai_marker_pre2020_hypothesis.py` |
| T-04 | test | `tests/unit/test_config_hash.py`, `tests/unit/test_provenance_validate.py` |
| T-05 | code + CI | `scripts/report_analysis_module_coverage.py`; `.github/workflows/ci-tests.yml` |
| T-06 | test | `tests/unit/test_parser_html_fuzz.py` |
| T-07 | test | `tests/unit/test_dedup_transaction_rollback.py` |

---

## I — Miscellaneous (N-01–N-06)

| ID | Tag | Primary evidence |
|----|-----|-------------------|
| N-01, N-02, N-04 | code | Marker / schema propagation — lexical `AI_MARKER_LIST_VERSION`, Parquet metadata |
| N-03 | code | `src/forensics/analysis/drift.py` — skip UMAP when insufficient centroids |
| N-05 | code | `src/forensics/utils/velocity_metrics.py` — velocity helpers out of `models` |
| N-06 | code + test | `run_metadata` — `last_processed_author`, `authors_in_run`; `tests/integration/test_parallel_parity.py` |

---

## Human gates (explicit)

| ID | Gate |
|----|------|
| C-06 | Product decision on ADR-009 option (a), (b), or (c) before removing analyze-stage SQLite reads |
| M-08 | Legal / ToS — external outlet choice before live external scrape |

---

## Maintenance

When a punch item’s remediation changes materially, update this file **and** append a short note to [HANDOFF.md](../HANDOFF.md). After merges that touch `src/`, refresh the GitNexus graph: `npx gitnexus analyze` (use `npx gitnexus analyze --embeddings` only if `.gitnexus/meta.json` already tracks embeddings; see `AGENTS.md` / `CLAUDE.md`).
