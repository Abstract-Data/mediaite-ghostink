# Phase 13: Code Review & Refactoring Remediation

Version: 0.1.0
Status: active
Last Updated: 2026-04-22
Model: claude-opus-4-6

---

## Mission

Implement all actionable findings from the Apr 22, 2026 Code Review Report and Refactoring Analysis Report (5th review run). This phase addresses 2 Critical, 6 High, and 8 Medium priority items spanning performance, maintainability, DRY violations, dead code, and testing gaps.

The goal is to move the codebase's overall review score from 6.8 → 7.5+ and reduce the refactoring issue count from 16 distinct / 55 occurrences toward ≤8 distinct / ≤20 occurrences.

---

## Source Reports

- **Code Review:** [Apr 22, 2026: mediaite-ghostink Code Review Report](https://www.notion.so/34a7d7f562988109be48e7b17ec3ec7b)
- **Refactoring:** [Apr 22, 2026: mediaite-ghostink Refactoring Analysis Report](https://www.notion.so/34a7d7f56298811ebbecde350a65bde3)

---

## Guiding Principles

1. **Incremental, tested changes.** Each step should leave tests green. No big-bang rewrites.
2. **Respect stage boundaries.** scrape → extract → analyze → report. Do not merge stages.
3. **Preserve data model contracts.** Pydantic models are sacred. Additive changes only unless explicitly noted.
4. **One PR per phase.** Group logically related steps; keep the diff reviewable.
5. **Verify with commands.** Every step ends with `uv run pytest tests/ -v` and `uv run ruff check .`.

---

## Implementation Plan

### Phase A: Quick Wins (< 30 min each, Low risk)

These can be done independently in any order.

#### Step A1: Vectorize BOCPD Inner Loop
**Source:** P1-PERF-001, RF-CX-002
**Risk:** LOW
**Files:** `src/forensics/analysis/changepoint.py`
**What:** Replace the Python for-loop at L116-L117 with a vectorized NumPy slice assignment.
**Before:**
```python
for new_len in range(2, t + 2):
    log_pi_new[new_len - 1] = log_1mh + log_pi[new_len - 2] + log_pred[new_len - 2]
```
**After:**
```python
log_pi_new[1:t+1] = log_1mh + log_pi[:t] + log_pred[:t]
```
**Validation:** Existing `test_bocpd_vectorized_matches_reference` must still pass. Add a timing assertion for corpus sizes > 500 articles.

#### Step A2: Eliminate Duplicate `parse_datetime` Call
**Source:** RF-AR-001
**Risk:** LOW
**Files:** `src/forensics/analysis/timeseries.py`
**What:** At ~L246, delete the second `pub_ts = [parse_datetime(t) for t in ts_list]` and reuse the `timestamps` variable from ~L205.
**Validation:** `uv run pytest tests/ -k "timeseries" -v`

#### Step A3: Consolidate Parquet Path Construction
**Source:** RF-DRY-003
**Risk:** LOW
**Files:** `src/forensics/analysis/changepoint.py`, `src/forensics/analysis/timeseries.py`, `src/forensics/analysis/comparison.py`, `src/forensics/features/pipeline.py`
**What:** Replace all hand-built `project_root / "data" / "features" / f"{slug}.parquet"` with `AnalysisArtifactPaths.features_parquet(slug)`. Verify that `AnalysisArtifactPaths` has this method; if not, add it.
**Validation:** `uv run pytest tests/ -v` (full suite — touches 4 modules)

#### Step A4: Dead-code audit (manifest helper + repository import)
**Source:** RF-DC-001, RF-DC-002
**Risk:** LOW
**Files:** `src/forensics/scraper/crawler.py`, `src/forensics/storage/repository.py`
**What:**
- **`_iter_manifests_from_users_json`:** Keep in `crawler.py`. It is not used by the live crawl path but is part of the **supported test/tooling surface** (`tests/test_scraper.py::test_iter_manifests_from_users_json`). Treat as intentional; do not delete without moving the same behavior beside tests first.
- **`repository.py`:** `from uuid import uuid4` is already in place (style consistency vs `import uuid`).
**Validation:** `uv run ruff check .` + `uv run pytest tests/ -v`

#### Step A5: Migrate `read_features` to Lazy Scan
**Source:** P3-STYLE-001
**Risk:** LOW
**Files:** `src/forensics/storage/parquet.py`
**What:** Change `read_features` from `pl.read_parquet(path)` to `pl.scan_parquet(path).collect()`. This is a no-op for current callers but aligns with LazyFrame policy. Downstream callers in `timeseries.py` can later defer `.collect()`.
**Validation:** `uv run pytest tests/ -k "parquet or timeseries" -v`

---

### Phase B: DRY Extraction (1-4 hours, Medium risk)

#### Step B1: Extract `ensure_repo` Context Manager
**Source:** RF-DRY-001 (Critical)
**Risk:** MEDIUM
**Files:** `src/forensics/storage/repository.py` (add helper), `src/forensics/cli/scrape.py`, `src/forensics/scraper/crawler.py`, `src/forensics/scraper/fetcher.py`
**What:** Create a helper that yields either a caller-provided `Repository` or opens a new one:
```python
@contextmanager
def ensure_repo(db_path: Path, repo: Repository | None = None):
    """Yield an active Repository, opening one if not provided."""
    if repo is not None:
        yield repo
    else:
        with Repository(db_path) as owned:
            yield owned
```
Replace all 6 instances of the `if repo is not None: ... else: with Repository(db_path) as owned:` pattern.
**Validation:** `uv run pytest tests/ -v` (full suite — touches scraper and CLI)
**Test:** Add a unit test for `ensure_repo` covering both branches.

#### Step B2: Centralize Feature Frame Loading
**Source:** RF-DRY-002
**Risk:** MEDIUM
**Files:** `src/forensics/analysis/changepoint.py`, `src/forensics/analysis/timeseries.py`, `src/forensics/analysis/utils.py`
**What:** `changepoint.py` and `timeseries.py` still inline the `load_feature_frame + filter by author_id` logic. Route both through `load_feature_frame_for_author()` from `analysis/utils.py`.
**Validation:** `uv run pytest tests/ -k "changepoint or timeseries" -v`

#### Step B3: Extract Shared Changepoint Builder
**Source:** RF-DRY-004
**Risk:** MEDIUM
**Files:** `src/forensics/analysis/changepoint.py`
**What:** Extract `_changepoints_from_breaks(feature_name, author_id, values, timestamps, raw_breaks) -> list[ChangePoint]` and have both `changepoints_from_pelt` and `changepoints_from_bocpd` call it.
**Validation:** `uv run pytest tests/ -k "changepoint" -v`

#### Step B4: Add `load_drift_summary` to Drift Module
**Source:** RF-CS-003 (Feature Envy), P2-ARCH-001
**Risk:** MEDIUM
**Files:** `src/forensics/analysis/drift.py`, `src/forensics/analysis/comparison.py`
**What:** Add `load_drift_summary(slug, paths) -> DriftSummary` to `drift.py` that returns a typed struct of velocities and baseline curve. Replace `_velocity_and_baseline_for_slug` in `comparison.py` with a call to this function.
**Validation:** `uv run pytest tests/ -k "drift or comparison" -v`
**Test:** Unit test for `load_drift_summary` with fixture data.

---

### Phase C: Decomposition (2-4 hours, Medium-High risk)

#### Step C1: Decompose `extract_all_features` God Function
**Source:** RF-CX-001 (Critical), P2-MAINT-001
**Risk:** HIGH — this is the most complex refactor. Plan carefully, test after each sub-step.
**Files:** `src/forensics/features/pipeline.py`
**What:** Split the 163-line function into three focused helpers:
1. `_extract_features_for_article(article, idx, seq, nlp, settings) -> FeatureVector` — pure feature computation for a single article
2. `_process_author_batch(author_id, articles, nlp, settings, ...) -> tuple[list[FeatureVector], list[EmbeddingTuple]]` — author-level iteration, embedding computation, batch NPZ writing
3. `extract_all_features(...)` — orchestration only: load articles, iterate authors, call `_process_author_batch`, write Parquet, check failure ratio

**Sub-steps:**
1. Write tests for `_extract_features_for_article` first (TDD — red/green)
2. Extract the function, run tests
3. Write tests for `_process_author_batch`
4. Extract it, run tests
5. Slim down `extract_all_features` to orchestration, run full suite
**Validation:** `uv run pytest tests/ -v --cov=src/forensics/features --cov-report=term-missing`

#### Step C2: Extract `_persist_and_log` from `_fetch_one_article_html`
**Source:** RF-CX-003
**Risk:** MEDIUM
**Files:** `src/forensics/scraper/fetcher.py`
**What:** The three mutation branches (HTTP fail, off-domain, success) each duplicate the `async with ctx.db_lock` → `get_article_by_id` → `_resume_skip_fetch` → mutate → `upsert_article` → `async with ctx.done_lock` → log ceremony. Extract a `_persist_and_log(ctx, article, row, label)` async helper.
**Validation:** `uv run pytest tests/ -k "fetch" -v`

#### Step C3: Compose `_full_pipeline` from `_discover_and_metadata`
**Source:** RF-AR-002
**Risk:** LOW
**Files:** `src/forensics/cli/scrape.py`
**What:** Have `_full_pipeline` call `_discover_and_metadata` for its first phase instead of duplicating the discover + metadata inline logic.
**Validation:** `uv run pytest tests/ -k "scrape" -v`

---

### Phase D: Testing & Coverage (2-3 hours, Low risk)

#### Step D1: Raise Coverage Threshold
**Source:** P1-TEST-001
**Risk:** LOW
**Files:** `pyproject.toml`
**What:** Bump `fail_under` from 50 to 65. This should pass with current coverage (~64%) after the new tests from steps above.

#### Step D2: Add Convergence Unit Tests
**Source:** P1-TEST-001
**Files:** `tests/unit/test_convergence.py` (new)
**What:** Test `compute_convergence_scores` with fixture data. Cover: no changepoints → empty windows, single changepoint → single window, multiple changepoints across features → convergence window detection.

#### Step D3: Add Content LDA Unit Tests
**Source:** P1-TEST-001
**Files:** `tests/unit/test_content_lda.py` (new)
**What:** Test `_topic_entropy_lda` with mock corpus. Mock spaCy to avoid model dependency. Cover: single-topic corpus → low entropy, multi-topic → high entropy, empty corpus → graceful fallback.

#### Step D4: Add Fetcher Mutation Unit Tests
**Source:** P2-TEST-002
**Files:** `tests/unit/test_fetcher_mutations.py` (new)
**What:** Test the `_persist_and_log` helper (from Step C2) in isolation with mock locks and repository.

#### Step D5: Remove C901 Suppressions Where Possible
**Source:** P3-STYLE-002
**Files:** `pyproject.toml`
**What:** After C1 and C2 are complete, remove C901 suppressions for `features/pipeline.py`, `scraper/fetcher.py`, and any others that now pass. Target: reduce from 9 to ≤6.

---

### Phase E: Structural Improvements (2-4 hours, Medium risk)

#### Step E1: Introduce `AnalyzeContext` Dataclass
**Source:** RF-CS-001
**Files:** `src/forensics/cli/analyze.py`, `src/forensics/analysis/` (as needed)
**What:** Create `@dataclass AnalyzeContext` bundling `db_path`, `settings`, `paths`, and `author_slug`. Replace the `(db_path, settings, *, root, author)` data clump across all `_run_*_stage` functions.
**Validation:** `uv run pytest tests/ -k "analyze" -v`

#### Step E2: DRY the `_accept_legacy_flat_payload` Validator
**Source:** RF-CX-004
**Files:** `src/forensics/models/features.py`
**What:** Replace the 6 sequential dict-pop blocks with a `for family_cls, key in FAMILIES` loop.

#### Step E3: Consolidate ADR Naming Scheme
**Source:** P3-DOC-001
**Files:** `docs/adr/`
**What:** Ensure all ADR files use consistent `ADR-NNN` prefix naming. Rename any inconsistencies.

---

### Phase F: Self-Similarity Cache Fix (1 hour, Medium risk)

#### Step F1: Hash-Based Cache Key for `_self_similarity_cached`
**Source:** P2-PERF-002
**Files:** `src/forensics/features/content.py`
**What:** Replace `@lru_cache` with `tuple(peers)` key with a hash-based approach. Options:
- Use `functools.lru_cache` with `tuple(hash(p) for p in peers)` as key
- Or switch to a dict-based cache keyed on `frozenset(peer_ids)` if peer identity is sufficient
**Validation:** `uv run pytest tests/ -k "content" -v`

---

## Execution Order & Dependencies

```
Phase A (Quick Wins) — all independent, do first
    ↓
Phase B (DRY Extraction) — B1 first (enables B2-B4)
    ↓
Phase C (Decomposition) — C1 is the critical path; C2 depends on B1
    ↓
Phase D (Testing) — D1 depends on D2+D3 passing; D4 depends on C2; D5 depends on C1+C2
    ↓
Phase E (Structural) — independent of C/D, can run in parallel
    ↓
Phase F (Cache Fix) — independent, can run anytime after Phase A
```

## Estimated Total Effort

- Phase A: 1-2 hours
- Phase B: 3-4 hours
- Phase C: 3-5 hours
- Phase D: 2-3 hours
- Phase E: 2-3 hours
- Phase F: 1 hour
- **Total: 12-18 hours**

## Definition of Done

Closure note **2026-04-22:** Items below were verified or explicitly deferred in-repo (see HANDOFF completion block “Phase 12–13 gap closure — prompts, controls doc, F1 cache”).

- [x] All 16 refactoring issues addressed (closed or documented as deferred with rationale) — e.g. Step A4 manifest helper kept as intentional test surface; full `validate_against_controls` statistics deferred per Phase 12 doc.
- [x] `uv run pytest tests/ -v` passes
- [x] `uv run ruff check .` passes
- [x] `uv run ruff format --check .` passes
- [x] Coverage ≥ 65% with `fail_under = 65`
- [x] C901 suppressions reduced from 9 to ≤ 6
- [x] No new GUARDRAILS Signs triggered
- [x] HANDOFF.md updated with completion block
- [x] Re-run python-project-review to validate improvement — **recorded 2026-04-22:** no `python-project-review` CLI in this repository; substitute verification was `uv run pytest`, `uv run ruff check`, and `uv run ruff format --check` (see HANDOFF). Run the **python-project-review** / project-alignment skill separately if a full external audit is required.

## Risk Mitigation

- **C1 (extract_all_features):** TDD approach — write tests before extraction. Keep old function as `_extract_all_features_legacy` behind a flag until new version is verified.
- **B1 (ensure_repo):** The context manager must handle both sync and async callers. Verify with integration tests.
- **D1 (coverage threshold):** Only bump after new tests are in place. Use 60 as intermediate if 65 fails.
