# Changelog — Phase 16: Adversarial Review Remediation

## [0.2.0] — 2026-04-25

**Model:** gpt-5.2-codex (verification pass)
**Status:** active

### DOCS

- **`docs/RUNBOOK.md`:** Expanded *Phase 16 hash-break migration* with preregistration template → lock workflow, `run_metadata.json` verification, corpus custody v1/v2 transition semantics, and a single-author exploratory E2E spot-check recipe (optional `scrape --fetch` when refreshing HTML).
- **`HANDOFF.md`:** Phase 16 I+K completion block with command evidence (this release).
- **`docs/GUARDRAILS.md`:** Confirmed present — *Pre-Phase-16 locked artifacts must be re-locked* and *corpus_hash_v1* transition Sign (no edit required for I.3).

### VERIFY (four integrity claims → enforceable code)

The adversarial review called out four gaps vs informal report language; implementation landed in Phases A–J — this entry records **verification** that operators can rely on:

1. **Encoder revision pin** — `SentenceTransformer(..., revision=...)` + `EmbeddingRecord.model_revision` + drift-time validator; confirmatory mismatch raises unless `--exploratory --allow-pre-phase16-embeddings`.
2. **Analysis-config / preregistration hash coverage** — `include_in_config_hash` on signal-bearing knobs (`pelt_penalty`, `bocpd_hazard_rate`, `min_articles_for_period`, `changepoint_methods`, `enable_ks_test`, `embedding_model_revision`, …); `validate_analysis_result_config_hashes()` gate; lock snapshot in `preregistration_lock.json`.
3. **Corpus hash determinism** — `compute_corpus_hash` uses analyzable corpus + `ORDER BY content_hash`; `CorpusCustody` schema v2 with `corpus_hash` + `corpus_hash_v1`; `verify_corpus_hash` dispatches on `schema_version`.
4. **Statistical test integrity** — `HypothesisTest` carries `n_pre` / `n_post` / `n_nan_dropped` / `skipped_reason` / `degenerate`; BH correction uses rankable-only denominators; convergence payload includes `n_rankable_per_family`.

### PATCH

- **`versions.json`:** `current_version` → `0.2.0`; registered `v0.2.0.md`; v0.1.0 marked `deprecated`.
- **`prompts/.../current.md`:** aligned to `v0.2.0.md`.
- **`pyproject.toml`:** `tool.ruff.extend-exclude = ["notebooks"]` so `ruff check .` matches package scope (Quarto cells are not flat Python modules).
- **`data/preregistration/preregistration_lock.json`:** committed unfilled template (`locked_at: null`, no `analysis`) so `verify_preregistration` reads `missing` under test fixtures and operators run `lock-preregistration` before confirmatory analyze.

### Eval impact (measured)

- Full `pytest` + coverage gate recorded in HANDOFF (Phase K). No new detector-accuracy benchmark in this release.

## [0.1.0] — 2026-04-25

**Model:** claude-opus-4-7
**Status:** active

### Added

- **Phase A (landed 2026-04-25):** `AnalysisConfig` now hash-includes and
  validates `pelt_penalty` (`gt=0`), `bocpd_hazard_rate` (`gt=0`, `le=1`),
  `min_articles_for_period` (`ge=1`), `bootstrap_iterations` (`ge=1`), plus
  existing `changepoint_methods` / `enable_ks_test`; added
  `embedding_model_revision` (HF commit pin, `include_in_config_hash`).
  `_snapshot_thresholds` carries `embedding_model_revision` and `enable_ks_test`;
  committed `data/preregistration/preregistration_lock.json` is the unfilled
  template (`locked_at: null`). **Sign:** Pre-Phase-16 locked artifacts must
  be re-locked — see `docs/GUARDRAILS.md` Agent-Learned Signs.
- 11-phase (A–K) implementation plan covering every actionable finding from
  the 2026-04-25 adversarial architecture review (Phase A Full-Stack pass +
  Phase B Builder pass over Phase A's output).
- **Phase A — Pre-registration hash coverage:** audit `AnalysisConfig` for
  signal-bearing fields missing `include_in_config_hash`; add
  `embedding_model_revision`; promote `pelt_penalty`, `bocpd_hazard_rate`,
  `bocpd_min_run_length`, `min_articles_for_period` to hashed fields;
  regenerate the `preregistration_lock.json` template; document the
  one-time hash break in `GUARDRAILS.md` as a Sign.
- **Phase B — Embedding integrity:** pin `sentence-transformers` by
  revision in `features/embeddings.py`; persist `model_revision` on
  `EmbeddingRecord`; validate `embedding_dim` and `model_revision` on
  read; decide and document the pre-pin embedding policy
  (quarantine + re-extract is the recommended default); reject
  mismatched embeddings in confirmatory mode.
- **Phase C — Corpus hash determinism:** pin the current bug as an
  `xfail` regression test, change `compute_corpus_hash` to
  `ORDER BY content_hash`, bump `corpus_custody.json` to
  `schema_version=2`, persist both `corpus_hash_v1` and `corpus_hash`
  for one transition cycle, update the verifier to dispatch on schema
  version.
- **Phase D — Statistical test integrity:** extend `HypothesisTest` with
  `n_pre`, `n_post`, `n_nan_dropped`, `skipped_reason`, `degenerate`;
  drop NaN values at `run_hypothesis_tests` entry with logged counts;
  return explicit `HypothesisTest(skipped_reason=...)` rather than `[]`;
  flag Mann-Whitney/Cohen's d fallbacks as `degenerate=True`; update
  `apply_correction` to exclude skipped + degenerate from the BH
  denominator; update family-ratio convergence to use rankable-feature
  count as denominator.
- **Phase E — Repository concurrency enforcement:** add internal
  `threading.Lock` to `Repository`; wrap every mutating method
  (`upsert_article`, `mark_duplicates`, `clear_duplicate_flags`,
  `apply_migrations`); add `tests/integration/test_repository_concurrency.py`
  exercising N concurrent writers; supersede the P1-SEC-001 external-lock
  contract.
- **Phase F — Configuration validators and CLI wiring:** wire
  `settings.scraping.simhash_threshold` end-to-end through the dedup CLI;
  add `Field(ge=...)` validators on `word_count`, `bocpd_hazard_rate`,
  `min_articles_for_period`; SQLite migration adding
  `CHECK (word_count >= 0)`; tighten `changepoint_methods` to
  `list[Literal["pelt", "bocpd", "chow", "cusum"]]`; add hash-coverage
  smoke tests.
- **Phase G — Stage-config coherence:** `model_validator(mode="after")`
  on `ForensicsSettings` asserts `features.excluded_sections ==
  survey.excluded_sections` unless explicit override.
- **Phase H — Defensive logging in confirmatory mode:** promote silent
  `{}` fallback in `_maybe_decode_dict_field` to logged WARNING in
  exploratory mode and hard raise in confirmatory mode; plumb the
  strict flag via `ContextVar`.
- **Phase I — Documentation amendments:** scope the integrity report's
  provenance claim to the analyze stage; add Section 7.5 Phase-16
  amendments; add Phase-16 hash-break migration section to RUNBOOK.md.
- **Phase J — Performance and defensive low-priority:** refactor
  `compute_rolling_stats` to a single `.with_columns([...])`; document
  the brute-force dedup cliff above `simhash_threshold = 3` in RUNBOOK;
  range-guard `chow_test` `breakpoint_idx`; monotonic-increasing
  assertion at `chow_test`/`stl_decompose` entry; explicit empty-text
  filter in `scraper/parser.py` before dedup so audit trail records
  "dropped: empty content."
- **Phase K — Verification:** ruff lint + format clean; pytest with
  ≥ 75% coverage; end-to-end pipeline run; confirmatory-mode
  regression; CHANGELOG entries; HANDOFF.md update; GUARDRAILS Sign
  append; `npx gitnexus analyze --embeddings` re-run.

### Out of scope (Builder rebuttals)

- Recorded as explicit "do not re-litigate" with technical rebuttals: R6
  (per-family BH direction misread by Phase A), R7 (eager DataFrame, not
  LazyFrame), R12 (CLI orchestration is allowed cross-stage imports),
  R14 (SQLite type affinity makes TEXT/DATETIME storage equivalent),
  R16 (empty-text dedup outcome is correct; only audit trail wording
  improved in J.5), R17 (CPython 3.7+ dict ordering is guaranteed), R24
  (`mode="before"` runs against input dict, not partial state), R25
  (SQLite has no native BOOLEAN), R26 (TUI out of forensic-credibility
  scope).

### Eval impact (measured)

Not yet measured. Phase A/B adversarial review output is qualitative; no
detector-accuracy benchmarks are gated on Phase 16 outcomes. Post-Phase-16
evaluation should measure:

- Whether Phase D NaN-handling changes the count of significant
  hypothesis tests in confirmatory output (expected: small increase, as
  previously NaN-poisoned families now produce real BH ranks).
- Whether Phase B revision pinning changes embedding values for a
  fixed-corpus sanity run (expected: identical; the pin lock to the
  same revision currently in production).

### Sources

- Phase A — Full-Stack adversarial review (Template 1) over the
  mediaite-ghostink codebase. 26 risks across eight pipeline attack
  surfaces (stage boundaries, Pydantic boundaries, LazyFrame
  discipline, storage correctness, embedding integrity, feature
  extraction, statistical method validity, dedup/hashing). Inline
  cowork session, 2026-04-25.
- Phase B — Builder pass (Prompt B) reframed at user request from
  single-decision Critic-Builder to a full Builder pass over Phase A's
  risk list. 17 accepts, 9 rejects-with-rebuttal. Inline cowork
  session, 2026-04-25.
- Project skill `.claude/skills/adversarial-review/` — both Path A and
  Path B were run via this skill. Phase 16 is the implementation pass
  the skill's runbook explicitly delegates to follow-up work.
- Companion document: `mediaite-ghostink-integrity-report.docx`
  (workspace folder root) — Phase 16 closes the gaps the adversarial
  review surfaced in this document's claims.
