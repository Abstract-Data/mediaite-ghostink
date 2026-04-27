# PR #94 Review Remediation — Full Implementation

Version: 0.1.0
Status: active
Last Updated: 2026-04-26
Model: claude-opus-4-7

---

## Mission

Close every issue raised in the code review of PR #94 (`notion-review-refactor-run10`). Nothing is deferred. Every item below must land in a single working branch with passing tests, updated docs (`HANDOFF.md`, `docs/RUNBOOK.md`, `docs/GUARDRAILS.md` where applicable), and `gitnexus_detect_changes` confirmation. Items are grouped by severity. Each item lists: **target**, **current behavior**, **required behavior**, **implementation**, **acceptance test**.

The PR being remediated is at HEAD of branch `notion-review-refactor-run10` (PR #94). Apply changes on top of that branch, *not* on `main`.

## Pre-flight (run once)

1. `git fetch origin && git checkout notion-review-refactor-run10`
2. `uv sync`
3. `uv run pytest tests/ -v --no-cov` — capture baseline pass count
4. `uv run ruff check .` — baseline
5. `npx gitnexus analyze --embeddings` if the index is stale
6. For every symbol you touch in steps 1–17 below, run `gitnexus_impact({target: "<symbol>", direction: "upstream"})` first; abort and report if any return CRITICAL with no path forward.

---

## CRITICAL — must land before merge

### 1. Parallel author refresh swallows worker exceptions inconsistently

**Target:** `src/forensics/analysis/orchestrator/parallel.py:411-417` — `_run_isolated_author_jobs`

**Current behavior:** `future.result()` is called without `try/except`. Any worker exception aborts the entire refresh, even though the matching loop in `_run_full_analysis_per_authors` (`parallel.py:271-281`) catches `Exception`, logs it, and continues with empty stage timings.

**Required behavior:** `_run_isolated_author_jobs` must mirror the `_run_full_analysis_per_authors` pattern: catch `Exception`, log with the worker identity (`author_slug`, `job_kind`), persist a per-author error record under `paths.scrape_errors_path / f"isolated_refresh_{author_slug}.json"` (or extend the existing per-author error JSONL — pick whichever the surrounding module already uses), and continue iterating over remaining futures.

**Implementation:**

```python
for fut, author_slug in pending:
    try:
        result = fut.result()
    except Exception as exc:  # pragma: no cover - exercised by test
        logger.exception(
            "isolated refresh worker failed",
            extra={"author_slug": author_slug, "error": repr(exc)},
        )
        _persist_isolated_refresh_error(author_slug, exc)
        continue
    results.append(result)
```

Add `_persist_isolated_refresh_error` as a private helper alongside the existing error persistence used by `_run_full_analysis_per_authors`. If that module already exposes a private error-writer, reuse it instead of duplicating.

**Acceptance test:** add `tests/unit/test_isolated_refresh_resilience.py` that monkey-patches one worker target to raise `RuntimeError("boom")`, runs `_run_isolated_author_jobs` against a 3-author fixture, and asserts (a) returned results contain the 2 surviving authors, (b) one error record is persisted, (c) no exception escapes.

---

### 2. `merge_parquet_metadata` writes non-atomically and corrupts features parquet on crash

**Target:** `src/forensics/storage/parquet.py:73-92` — `merge_parquet_metadata`; downstream caller `write_features` at `parquet.py:184-188` (N-04 stamping).

**Current behavior:** `pq.write_table(path, ...)` writes directly to the destination, replacing a file that `write_parquet_atomic` had previously written via tmp+rename. Crash mid-write corrupts the just-written features parquet.

**Required behavior:** preserve atomicity across the metadata-stamping step. Write to a `.tmp` sibling and `os.replace` only on successful flush.

**Implementation:**

```python
def merge_parquet_metadata(path: Path, extra_metadata: dict[str, str]) -> None:
    table = pq.read_table(path)
    existing = dict(table.schema.metadata or {})
    merged = {**existing, **{k.encode(): v.encode() for k, v in extra_metadata.items()}}
    new_schema = table.schema.with_metadata(merged)
    new_table = table.replace_schema_metadata(merged)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        pq.write_table(new_table, tmp, compression="zstd")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
```

Confirm `os` is imported. Confirm the compression and other write kwargs match the original `pq.write_table` call exactly so the file payload is byte-identical aside from metadata.

**Acceptance test:** extend `tests/unit/test_storage_parquet.py` (create if absent) with two cases: (a) successful stamp leaves `path` with merged metadata and no `.tmp` sibling; (b) stub `pq.write_table` to raise — assert `path` content is unchanged from before the call and `.tmp` is cleaned up.

---

### 3. Per-author empty filter silently falls back to entire multi-author frame

**Target:** `src/forensics/analysis/orchestrator/per_author.py:322-326`

**Current behavior:** when `lf_author.collect()` is empty, the code re-collects `lf_all` (the full frame for all authors). Downstream code may then filter by `author_id` against the wrong rows, or worse, treat the multi-author frame as the per-author corpus.

**Required behavior:** when the per-author filter is empty, return `None` from the helper and log a structured warning (`author_slug`, `filter_predicate`, `expected_rows>=1`). Do not fall back to the unfiltered frame.

**Implementation:** remove the `lf_all.collect()` fallback and replace with:

```python
df_author = lf_author.collect()
if df_author.is_empty():
    logger.warning(
        "per_author frame empty after filter; skipping author",
        extra={"author_slug": author.slug, "author_id": author.id},
    )
    return None
```

Verify every caller of this helper handles `None`. If any caller currently assumes a non-empty frame, add the same guard at the call site.

**Acceptance test:** add `tests/unit/test_per_author_empty_filter.py` with a fixture frame that contains zero rows for the target `author_id`, assert the helper returns `None`, assert the warning is emitted, assert the orchestrator continues with remaining authors.

---

### 4. D-01 NFKC simhash change has no migration; will mass-undeduplicate existing corpora

**Target:** `src/forensics/utils/hashing.py:71-78`, `src/forensics/scraper/dedup.py:67`, plus migration command + RUNBOOK note + artifact key version bump.

**Current behavior:** the NFKC normalization added in this PR changes the simhash output for every previously-fingerprinted article. The next dedup run on an existing store will compute a fresh distribution of fingerprints, fail to match historical near-duplicates, and re-admit them.

**Required behavior:** ship a migration path *and* a version-tagged artifact key so stale stores are detected at startup, not silently miscomputed.

**Implementation:**

1. **Bump fingerprint version.** Add `SIMHASH_FINGERPRINT_VERSION = "v2"` (or whatever monotonic identifier matches the project convention — check `forensics/utils/hashing.py` for a precedent) and stamp it into the simhash artifact alongside the bit value. Persist via the existing simhash record schema.

2. **Repository read-side gate.** When `Repository.load_dedup_simhashes` (or equivalent — locate via `gitnexus_query({query: "load simhash"})`) reads a row whose stored version differs from `SIMHASH_FINGERPRINT_VERSION`, *exclude it from the active near-duplicate set* and emit a structured warning summarizing the count of stale rows.

3. **CLI command.** Add `forensics dedup recompute-fingerprints` (subcommand under the existing dedup CLI; if no dedup CLI exists, add it under `src/forensics/cli/dedup.py` mirroring the pattern from `cli/analyze.py`). The command:
   - takes optional `--limit N` for testing,
   - iterates over `articles` whose `dedup_simhash_version != SIMHASH_FINGERPRINT_VERSION`,
   - recomputes via `simhash(clean_text)`,
   - writes back inside a `BEGIN IMMEDIATE` transaction (mirror the pattern from `repository.py:540-577`),
   - prints a JSON summary `{"recomputed": N, "skipped": M, "errors": K}`.

4. **RUNBOOK update.** Add a section "Migrating simhash fingerprints after D-01 (NFKC normalization)" to `docs/RUNBOOK.md` with the exact command and a one-line warning that running dedup *without* the migration will admit historical near-duplicates.

5. **Hashing docstring.** Extend the docstring on `simhash` in `hashing.py` to call out the v2 version (NFKC) and reference the RUNBOOK section.

**Acceptance test:** `tests/unit/test_simhash_migration.py` with three rows: one v2-fingerprinted, one v1-fingerprinted, one missing version; assert `load_dedup_simhashes` excludes the latter two, assert the recompute command updates them, assert a re-load returns all three.

---

### 5. Orchestrator `_sync_patchable_globals` propagates incompletely

**Target:** `src/forensics/analysis/orchestrator/__init__.py:36-46` plus `:80-81` (`__all__` leak) and `:38-40` (no-op self-rebinds).

**Current behavior:** the shim pins `uuid4`/`datetime`/`_clean_feature_series` into select sub-modules but **does not** propagate `_run_per_author_analysis` into `_parallel`, where `_per_author_worker` and `_run_full_analysis_per_authors` resolve the symbol from their *own* module globals. Any test that monkey-patches the package symbol and exercises a parallel/serial path will silently see the unpatched function. Additionally, `__all__` exports `datetime` and `uuid4` purely as patch hooks, leaking implementation detail through the public surface; lines 38–40 self-rebind module attributes back to themselves and only matter once external code has *already* monkey-patched the package — they are misleading scaffolding.

**Required behavior:** explicit, complete propagation, with the patch surface documented.

**Implementation:**

1. Replace `_sync_patchable_globals` with an explicit table:

```python
# Symbols whose value is allowed to be monkey-patched at the package level
# (forensics.analysis.orchestrator.<symbol>) and must be re-bound into
# every sub-module that resolves them from its own globals.
_PATCH_TARGETS: dict[str, tuple[ModuleType, ...]] = {
    "uuid4":                     (_per_author, _parallel, _staleness),
    "datetime":                  (_per_author, _parallel, _staleness),
    "_clean_feature_series":     (_per_author,),
    "_run_per_author_analysis":  (_parallel, _runner),
    "_resolve_parallel_refresh_workers": (_parallel,),
}

def _sync_patchable_globals() -> None:
    for name, modules in _PATCH_TARGETS.items():
        value = globals()[name]
        for module in modules:
            setattr(module, name, value)
```

Call `_sync_patchable_globals()` at the bottom of `__init__.py` (after all imports), and add a top-of-module `MODULE_DOCSTRING` paragraph documenting:
- which symbols are patch-safe (the keys of `_PATCH_TARGETS`),
- that any other symbol must be patched at its defining module, not at the package.

2. Remove `datetime` and `uuid4` from `__all__`. They remain importable through `forensics.analysis.orchestrator.datetime` for monkey-patching, but should not be advertised as public exports.

3. Delete the no-op self-rebind lines at `__init__.py:38-40`. They are subsumed by the `_PATCH_TARGETS` table.

**Acceptance test:** add `tests/unit/test_orchestrator_patch_surface.py` with one test per `_PATCH_TARGETS` entry: monkey-patch the package-level symbol to a sentinel, call the public entry that ultimately resolves the symbol from a sub-module, assert the sentinel was used. Include a negative test that asserts a symbol *not* in `_PATCH_TARGETS` (e.g. `_resolve_target_authors`) cannot be patched at the package level — i.e. the test documents the patch surface contract.

---

## HIGH — must land before merge

### 6. `runner.py` reads/writes `run_metadata.json` twice in adjacent blocks

**Target:** `src/forensics/analysis/orchestrator/runner.py:140-148`.

**Required behavior:** fold the two near-identical read/merge/write blocks into one merge before a single atomic write. Keep the existing atomic-write helper.

**Implementation:** extract a `_merge_run_metadata(updates: dict) -> None` helper that reads the file once, merges, writes once via the existing atomic-write utility (locate via `gitnexus_query({query: "atomic write json"})`).

**Acceptance:** existing tests must still pass; add one test that asserts a single mtime change per orchestrator run via a `mtime_after - mtime_before` count fixture.

---

### 7. `comparison.py` duplicates target-iteration error handling

**Target:** `src/forensics/analysis/orchestrator/comparison.py:60-77` and `:115-130`.

**Required behavior:** extract a single `_iter_compare_targets(targets, controls, *, on_error) -> Iterator[CompareResult]` helper that owns the "try compare, log warning on `ValueError`/`OSError`, continue" idiom. Both call sites call it.

**Acceptance:** existing tests pass; line count for `comparison.py` drops by ≥ 15 lines.

---

### 8. Strip refactor-history commentary from `runner.py` docstring

**Target:** `src/forensics/analysis/orchestrator/runner.py:48-78`.

**Required behavior:** per `CLAUDE.md` ("don't reference the current task, fix, or callers; those belong in the PR description and rot as the codebase evolves"), remove the "Phase 15 G1", "C-09", "Previously declared async" historical commentary. Replace with a one-paragraph docstring that explains *what* `run_full_analysis` does and *what invariants it preserves*, not how it got here.

**Acceptance:** no test impact; review the diff against `CLAUDE.md` "tone and style" rules before commit.

---

### 9. BH adjustment ties depend on input order

**Target:** `src/forensics/analysis/statistics.py:447-467` — `_bh_adjusted_pvalues`.

**Required behavior:** stable, deterministic ordering when two authors have identical `pmin`. Sort by `(pmin, slug)` so two-author ties resolve by lexicographic slug order regardless of input ordering.

**Implementation:** locate the `sorted(...)` call inside `_bh_adjusted_pvalues` and replace the key with `key=lambda x: (x.pmin, x.slug)`. Confirm the test in `test_statistics.py` exercises a tie; if not, add one.

**Acceptance:** add `tests/unit/test_bh_tie_stability.py` with two slugs at identical `pmin`, asserting the same adjusted-p assignment regardless of input list order (test both permutations).

---

### 10. Single-author cross-author column carries un-adjusted `pmin` under a name implying adjustment

**Target:** `src/forensics/analysis/statistics.py:476-484`.

**Required behavior:** when `n_r < 2`, set `out[(slug, fam)] = None` and stamp a sibling `out[(slug, fam, "_reason")] = "single-author-no-cross-correction"` (or extend the existing result schema with an explicit `cross_author_corrected_p_status` field). Do not silently substitute `pmin`.

**Acceptance:** extend `tests/unit/test_statistics.py::test_apply_cross_author_correction_two_slugs` and add a one-author counterpart that asserts the field is `None` plus the reason is captured.

---

### 11. Audit `detect_pelt` callers for upstream non-finite imputation

**Target:** `src/forensics/analysis/changepoint.py:140-150` (the new raise on non-finite input).

**Required behavior:** every call site that does not go through `_impute_finite_feature_series` must either impute or be moved to do so. Run `gitnexus_query({query: "detect_pelt"})` to enumerate callers; expected list (verify):
- orchestrator paths — already imputed
- `scripts/synthetic_null_pelt_calibration.py` — verify
- any sensitivity / notebook / eval entry — verify

For each caller missing imputation, prepend a call to `_impute_finite_feature_series` (or the public alias if one is added).

**Acceptance:** add `tests/unit/test_detect_pelt_input_guard.py` that imports each public caller, feeds an array containing `np.nan` and `np.inf`, and asserts the callers either succeed (because they imputed) or raise a typed error — never produce silent garbage.

---

## MEDIUM — must land before merge (testing gaps)

### 12. E2E test silently excluded from CI

**Target:** `pyproject.toml:77` (`addopts = "-m 'not slow'"`), `.github/workflows/ci-tests.yml:30`, and the markers on `tests/integration/test_pipeline_end_to_end.py:111-112`.

**Current behavior:** the E2E test carries both `@pytest.mark.slow` and `@pytest.mark.integration`. The default `-m 'not slow'` in `pyproject.toml` excludes it. The CI workflow runs `uv run pytest tests/` with no override. Result: the only end-to-end test never runs in CI.

**Required behavior:** integration tests must run in CI as a distinct, gated job that does not slow down the default unit-test loop.

**Implementation:**

1. Drop `@pytest.mark.slow` from `test_pipeline_end_to_end.py`. Keep `@pytest.mark.integration`.
2. Add a second job to `.github/workflows/ci-tests.yml` named `integration`:

```yaml
  integration:
    runs-on: ubuntu-latest
    needs: tests
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run python -m spacy download en_core_web_sm
      - run: uv run pytest tests/ -m integration -v --no-cov
```

3. Verify `pyproject.toml` registers the `integration` marker (it should already from this PR; confirm).

**Acceptance:** push the branch, observe both `tests` and `integration` jobs run, observe `test_pipeline_end_to_end.py` selected by the integration job.

---

### 13. `test_scraper_gather_resilience.py` tests stdlib `asyncio.gather`, not the scraper

**Target:** `tests/unit/test_scraper_gather_resilience.py`.

**Required behavior:** the test must invoke an actual scraper code path (e.g. `forensics.scraper.crawler.collect_article_metadata` or whichever function owns the gather call site at `crawler.py:327-349`). Stub one author/task target to raise; assert sibling task results are persisted via `Repository` (or written to the scrape-errors JSONL); assert the gather call neither raises nor short-circuits.

**Implementation:** replace the current body. Use the same SQLite tmp_db fixture pattern as `test_dedup_transaction_rollback.py`. Use `monkeypatch.setattr` against the scraper's HTTP fetch dependency to inject the failure; do not stub `asyncio.gather` itself.

**Acceptance:** the test fails when the resilience hardening is removed (manually verify by reverting the `return_exceptions=True` flag temporarily in a scratch branch).

---

### 14. E2E asserts shape, not signal

**Target:** `tests/integration/test_pipeline_end_to_end.py:146-177`.

**Current behavior:** assertions like `assert n > 0`, `assert "ttr" in frame.columns`, `assert targets["fixture-target"]` only check that something was produced. The seeded corpus does not contain a real regime shift, so a broken changepoint detector still passes.

**Required behavior:** seed two distinct lexical regimes for `fixture-target` (e.g. pre-2022 articles use a "wire-style" template, post-2022 articles use a deliberately divergent template — increased sentence length, formulaic openings, AI-marker phrases) and a single-regime corpus for `fixture-control`. Then assert:
- at least one `ChangePoint` lands within ±30 days of the seeded shift for `fixture-target`,
- *zero* significant ChangePoints for `fixture-control`,
- `fixture-target.convergence_score > fixture-control.convergence_score`.

**Implementation:** factor the corpus generator into a fixture `tests/integration/fixtures/e2e/conftest.py::seed_two_regime_corpus(target_slug, shift_date)`. Keep the existing `config.toml`. Replace the weak assertions with the signal assertions above.

**Acceptance:** test must (a) pass on the unmodified PR HEAD, (b) fail if `detect_pelt` is replaced with a no-op stub.

---

### 15. Settings cache leak in E2E fixture

**Target:** `tests/integration/test_pipeline_end_to_end.py:134`.

**Required behavior:** `get_settings.cache_clear()` must be paired with restoration. Either move the clear to a fixture with a `yield` + `cache_clear()` in the teardown, or use a `monkeypatch.setattr(forensics.config, "_get_settings_impl", ...)` style override that auto-undoes.

**Implementation:** convert to a `@pytest.fixture(autouse=True)` scoped to the integration module:

```python
@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

**Acceptance:** add a follow-on test in the same module that asserts `get_settings()` returns the production settings object, not the E2E fixture override.

---

### 16. Simhash generator has no direct unit test

**Target:** new `tests/unit/test_simhash_generator.py`.

**Required behavior:** cover the generator-based `_ngrams_iter` (now a generator per this PR) and the `simhash` function:
- single-consumption invariant: passing the generator to `simhash` produces the same value as a list-materialized version,
- near-duplicate sensitivity: a 1-character substitution in a 500-word document produces a hamming distance below the configured dedup threshold,
- NFKC normalization: full-width vs half-width digit forms produce the same fingerprint,
- empty input: returns the documented sentinel (zero, `None`, or raises — match current implementation).

**Acceptance:** four test cases, all pass on PR HEAD.

---

### 17. `test_apply_cross_author_correction_two_slugs` asserts only non-`None`

**Target:** `tests/unit/test_statistics.py:209`.

**Required behavior:** assert numeric values. Compute the expected adjusted p-values by hand (or via `scipy.stats.false_discovery_control` if the project allows that import) and assert each adjusted value to within `1e-12`.

**Acceptance:** test fails if BH adjustment formula regresses.

---

## LOW — nice to have, but include in this branch

### 18. HTML fuzz test asserts only liveness

**Target:** `tests/unit/test_parser_html_fuzz.py:14-28`.

**Required behavior:** add at least one *semantic* invariant: e.g. for input HTML containing a unique sentinel string `"GHOSTINK_FUZZ_SENTINEL"`, assert the sentinel appears in the parsed plain text (when not inside a `<script>` or `<style>` block).

**Implementation:** extend the Hypothesis strategy to inject the sentinel at a random text position, then assert presence post-parse.

---

### 19. Hypothesis AI-marker test has weak strategy space

**Target:** `tests/unit/test_ai_marker_pre2020_hypothesis.py:46-54`.

**Required behavior:** broaden the strategy beyond ASCII noise on 5 fixed snippets. Either generate snippets via `hypothesis.strategies.text()` with realistic word-length distributions, or expand the snippet set to 30+ examples drawn from a fixture file.

---

## Documentation updates (mandatory per `CLAUDE.md`)

- **`HANDOFF.md`** — append a completion block titled "PR #94 review remediation" listing every item above with file lists and verification commands.
- **`docs/RUNBOOK.md`** — add the simhash migration section (item 4); add a "Running integration tests locally" subsection (item 12).
- **`docs/GUARDRAILS.md`** — add a Sign for the per-author empty-fallback footgun (item 3): "When a Polars filter against a per-entity LazyFrame returns empty, never re-collect the source frame as a fallback. The downstream code may treat the unfiltered frame as the per-entity corpus."
- **`docs/punch-list-closure-index.md`** — append a row per item above with status `closed` and the corresponding commit SHA once landed.

## Verification protocol (run before opening PR)

In order, all from the repository root:

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run pytest tests/ -v --cov=src --cov-report=term-missing` — coverage must not regress versus baseline captured in pre-flight.
4. `uv run pytest tests/ -m integration -v --no-cov` — integration suite must pass (item 12).
5. `npx gitnexus analyze --embeddings`
6. `gitnexus_detect_changes({scope: "all"})` — verify the changed-symbol set matches the intent of items 1–17. Anything outside that set requires justification in the PR description.
7. `uv run forensics preflight --output json` — must still produce byte-stable output (item 4 of the original PR added this; verify it survives the changes).

## Out of scope (explicitly)

The following are *not* part of this remediation prompt and must not be addressed in the same branch:
- Re-running the full pipeline against the production corpus.
- Re-locking the preregistration (M-01 remains under a separate workflow).
- Repointing `colby-hall` from `role=control` to `role=target` (M-04).
- Any modification to `prompts/punch-list/` or `prompts/implementation-plan/` (those are immutable per `prompts/README.md`).

If a remediation item appears to require any of the above, stop and surface the dependency in `HANDOFF.md` rather than expanding the branch.

## Definition of done

- All 19 items above are implemented and tested.
- `uv run pytest tests/ -v --cov=src` passes with coverage ≥ baseline.
- `uv run pytest tests/ -m integration` passes locally and in the new CI job.
- `HANDOFF.md`, `docs/RUNBOOK.md`, `docs/GUARDRAILS.md`, `docs/punch-list-closure-index.md` updated.
- `gitnexus_detect_changes` confirms the affected scope.
- PR description enumerates each item with file:line and the commit that closed it.
