# mediaite-ghostink — Implementation Plan

Version: 0.1.0
Status: active
Last Updated: 2026-04-26
Model: claude-sonnet-4-6

---

**References:** [punch-list](../punch-list/current.md) (92 items, IDs M-01 through N-06)
**Goal:** Progress from "exploratory signals with critical gaps" to "defensible forensic findings."

Phases are ordered by dependency and severity. Items that are blocked by other items are noted explicitly. Items that require a human decision before code can be written are marked **[HUMAN DECISION]**.

---

## Phase 0 — Blockers: Prerequisites for Any Public Claim
**Covers:** M-01, M-04, M-03, M-02, M-05, R-01
**Effort:** Small–Medium (1–2 days, no code changes required in most items)
**Must complete before any Phase 1+ work is presented publicly.**

These items require no code changes; they are operational and editorial decisions.

---

### 0.1 — File the preregistration lock (M-01)

**What:** Convert `data/preregistration/preregistration_lock.json` from an unfilled template into a real, populated lock.

**Exact steps:**
```bash
# Review and confirm thresholds in config.toml first (see Phase 0.3 for target config)
uv run forensics lock-preregistration
```

This writes the current analysis thresholds (split date, feature list, test battery, α, |d| gate, BH correction, embedding model revision) into the lock file with `locked_at` populated.

**Precondition:** All threshold decisions (Phase 0.3, M-05) must be made FIRST. You cannot lock thresholds that were changed post-hoc in response to data (Fix-F, Fix-G) and call them preregistered. Options:
- (a) Revert Fix-F and Fix-G to the original thresholds (0.5 for both), lock, then see what that does to findings. Or:
- (b) Lock the current thresholds but explicitly amend `amendment_phase15.md` to document Fix-F and Fix-G as exploratory post-hoc changes that apply to the current run only and will be re-evaluated in any future confirmatory run.

**[HUMAN DECISION]** — Which option above to take. Recommendation: option (b), document honestly.

**Verification:** `cat data/preregistration/preregistration_lock.json` should show `locked_at` populated, and `uv run forensics analyze --author colby-hall` (without `--exploratory`) should succeed without a "missing preregistration" error.

---

### 0.2 — Configure colby-hall as target author (M-04)

**What:** Edit `config.toml` to set `colby-hall.role = "target"`.

**Exact edit in `config.toml`:**
```toml
[[authors]]
name = "Colby Hall"
slug = "colby-hall"
role = "target"          # was "control"
# ... rest of existing entry unchanged
```

**Note:** After this change, re-run analysis for colby-hall so its result JSON reflects the correct role:
```bash
uv run forensics analyze --author colby-hall --exploratory
```

**Verification:** `data/analysis/colby-hall_result.json` should reflect the updated config_hash that includes the role change.

---

### 0.3 — Run comparison analysis (M-03)

**Blocked by:** 0.2 (must have at least one target author)

**What:** Re-run the comparison stage to produce a non-empty `comparison_report.json`.

```bash
uv run forensics analyze --comparison-only
# or the full run:
uv run forensics analyze --all-authors --exploratory
```

**Verification:** `cat data/analysis/comparison_report.json` must contain non-empty `targets` and `controls` dictionaries. `signal_attribution` scores must be computed for colby-hall against the 11 control authors.

---

### 0.4 — Run the AI baseline pipeline (M-02)

**Blocked by:** Nothing (baseline generation is independent of analysis), but the Ollama service must be running.

**What:** Generate AI baseline articles and embed them so `ai_baseline_similarity` is populated.

**Exact steps:**
```bash
# Verify Ollama is running and the correct model is available
ollama list

# Run baseline generation for each target/flagged author
uv run forensics baseline --author colby-hall
uv run forensics baseline --author isaac-schorr
uv run forensics baseline --author michael-luciano
uv run forensics baseline --author mediaite-staff

# Then re-run drift analysis to pick up the new baseline embeddings
uv run forensics analyze --drift-only --all-authors --exploratory
```

**Verification:** `data/analysis/colby-hall_drift.json` should show `ai_baseline_similarity` as a non-null float. Repeat check for all flagged authors.

**Note:** If baseline embeddings already exist in `data/baseline/` but weren't connected, verify paths match what `_iter_ai_baseline_embedding_paths` expects: either `data/baseline/{slug}/embeddings/*.npy` or `data/baseline/{slug}/generation_manifest.json` with nested `.npy` files.

---

### 0.5 — Document Fix-F and Fix-G as exploratory (M-05)

**What:** Add an explicit amendment entry to `data/preregistration/amendment_phase15.md`.

**Content to append:**
```markdown
## Amendment: Post-hoc Threshold Changes (Fix-F and Fix-G)

Recorded: 2026-04-26

### Fix-F — PIPELINE_SCORE_PASS_THRESHOLD lowered 0.5 → 0.3
Reason: the 0.5 threshold filtered all percentile-mode pipeline-B windows because
peak_signal alone tops at 0.5 when sim_signal=ai_signal=0 (baseline not populated).

Status: **EXPLORATORY ONLY.** This threshold was chosen after observing output, not
before. Any confirmatory run must either restore 0.5 or preregister 0.3 with a
documented rationale independent of the current data.

### Fix-G — DRIFT_ONLY_PB_THRESHOLD = 0.3 added
Reason: 13 of 14 authors persisted zero convergence windows under the original
two-gate (ratio OR ab) logic.

Status: **EXPLORATORY ONLY.** Same constraint as Fix-F. The drift-only channel is
a potentially valid forensic tool but must be preregistered before use in
confirmatory analysis.
```

**Verification:** Read the file, confirm the amendment is timestamped and clearly marks both changes as exploratory.

---

### 0.6 — Downgrade all confidence verdicts in findings document (R-01, R-02, R-03, R-04)

**[HUMAN DECISION]** — The findings document must be revised before any external sharing.

**Exact changes to `data/reports/AI_USAGE_FINDINGS.md`:**

1. Replace the "Strength of Evidence" column header with "Exploratory Signal Strength"
2. Replace "AI-ASSISTED — HIGH confidence" with "EXPLORATORY SIGNAL — strong"
3. Replace "Likely AI-assisted" with "EXPLORATORY SIGNAL — moderate"
4. Add this disclosure block immediately after the Executive Summary header:

```markdown
> **Status: EXPLORATORY — NOT CONFIRMATORY**
> `run_metadata.json` records `preregistration_status: "missing"`. All findings below
> are exploratory signals under the project's own pre-registration contract
> (AGENTS.md, preregistration.py). No finding should be presented as a confirmed
> result until: (1) the preregistration lock is filed, (2) ai_baseline_similarity
> is populated for all flagged authors, and (3) the comparison analysis produces
> a non-empty report. See [punch-list](../../prompts/punch-list/current.md) for the
> complete remediation backlog.
```

5. Remove `comparison_report.json` from the "Files this report draws on" list, or replace with `# NOTE: comparison_report.json is currently empty ({"targets": {}}) — comparison analysis was not run`
6. Fix the author count claim: "12 individuals analyzed in the April 26 run; mediaite and mediaite-staff artifacts are from an earlier run with a different config_hash"
7. Add a section "Section Coverage (Untested Confound)" noting that J5 residualization was BORDERLINE-disabled and section-level confounds are uncontrolled for flagged authors

---

## Phase 1 — Methodology / Forensic Integrity
**Covers:** M-06, M-07, M-08, M-09, M-10, M-11, M-12, M-13, M-14, M-15, M-16, M-17, M-18, M-19, M-20, M-21, M-22, M-23
**Effort:** Large (1–2 weeks; several items are [HUMAN DECISION])
**Blocked by:** Phase 0 completion.

---

### 1.1 — Audit and trim the AI marker list (M-06, M-20, M-21)

**[HUMAN DECISION]** — Which phrases to drop requires editorial judgment.

**Plan:**
1. Export a stratified random sample of 200 pre-2020 Mediaite articles (use DuckDB on `articles.db`, filter `published_date < 2020-01-01`, stratified by author):
   ```bash
   uv run python -c "
   import duckdb
   con = duckdb.connect('data/articles.db', read_only=True)
   sample = con.execute('''
     SELECT a.author_id, a.id, a.clean_text
     FROM articles a
     WHERE a.published_date < '2020-01-01'
       AND a.is_duplicate = 0
       AND a.word_count >= 100
     USING SAMPLE 200
   ''').df()
   sample.to_csv('data/marker_audit_sample.csv', index=False)
   "
   ```
2. Run `extract_lexical_features` on each sampled article and record which of the 16 marker phrases fire.
3. **Drop threshold: any phrase firing in > 5% of the pre-2020 sample is a false positive and must be removed or reclassified.**
4. Candidate removals (high probability of FP > 5%): "arguably," "navigate," "underscores," "serves as a," "represents a significant."
5. Candidate additions after independent review of GPT-4o / Gemini news article generation: phrases that appear specifically in AI-generated news drafts but not in this pre-2020 sample.
6. Update `_AI_MARKER_SPECS` in `lexical.py`, bump `AI_MARKER_LIST_VERSION` to "0.2.0", re-run feature extraction for all authors, re-run analysis.

**Files changed:** `src/forensics/features/lexical.py`, all `data/features/*.parquet` must be regenerated.

**Verification:** Re-run `uv run pytest tests/test_features.py -v`. Verify that colby-hall's pre-ChatGPT AI-marker increases drop substantially. If they don't, investigate further.

---

### 1.2 — Disaggregate or caveat the mediaite-staff byline (M-07)

**Plan:**
1. Query `data/articles.db` to understand whether the "Mediaite Staff" byline's post-split articles are individually attributable to specific WordPress user IDs (even if bylined to "Staff"):
   ```bash
   uv run python -c "
   import duckdb
   con = duckdb.connect('data/articles.db', read_only=True)
   print(con.execute('''
     SELECT modifier_user_id, COUNT(*) as n
     FROM articles a
     JOIN authors au ON a.author_id = au.id
     WHERE au.slug = 'mediaite-staff'
     GROUP BY modifier_user_id ORDER BY n DESC LIMIT 20
   ''').df())
   "
   ```
2. If `modifier_user_id` is populated, attempt to link to specific authors and re-run analysis on the disaggregated corpus.
3. If not disaggregable, add a prominent caveat to the findings document: "The mediaite-staff byline aggregates content from an unknown number of contributors. Stylometric features for this byline measure the aggregate stream, not any individual's writing. The bigram_entropy increase (d=+4.68) is consistent with growing staff diversity and cannot be attributed to AI adoption without additional evidence."
4. Move `mediaite-staff` out of the main ranked verdict table into a separate "Aggregate Bylines" section.

**Files changed:** `data/reports/AI_USAGE_FINDINGS.md`, possibly `config.toml` (add `is_shared_byline = true` flag)

---

### 1.3 — Identify and add external control authors (M-08)

**[HUMAN DECISION]** — Which external publication to use as a control requires editorial and legal judgment.

**Plan:**
1. Identify a comparable political news publication that has:
   - A public WordPress REST API (or equivalent)
   - Similar editorial scope to Mediaite (political news/commentary)
   - A documented AI-writing policy that either bans or never adopted AI (ideally with public statements)
   - Willing to be scraped (check robots.txt, ToS)
2. Candidates to evaluate: The Hill, Reason, National Review, The Dispatch — research each for AI policy statements and WordPress API availability.
3. Add 3–5 external control authors to `config.toml` with `role = "control"` and `outlet = "external"`.
4. Run the full pipeline for these authors.
5. If external controls show the same style shifts as Mediaite authors, that is evidence of industry-wide effects rather than Mediaite-specific AI adoption.

**Files changed:** `config.toml`, `data/` (new scrape data)

---

### 1.4 — Add cross-investigation BH correction (M-09)

**What:** After per-author BH correction runs, add a second-pass BH correction across all authors' per-family best corrected p-values.

**Plan:**
1. Add `apply_cross_author_correction(all_authors_tests: dict[str, list[HypothesisTest]]) -> dict[str, list[HypothesisTest]]` to `statistics.py`.
2. For each family, collect the minimum corrected_p across all authors, apply BH across authors, add `cross_author_corrected_p` field to `HypothesisTest`.
3. Update `AnalysisConfig` with `enable_cross_author_correction: bool = False` (off by default, so existing behavior is unchanged until this is preregistered).
4. Update `AI_USAGE_FINDINGS.md` to note that cross-author correction was not applied to current findings.

**Files changed:** `src/forensics/analysis/statistics.py`, `src/forensics/models/analysis.py`, `src/forensics/config/settings.py`

**Verification:** `uv run pytest tests/unit/test_analyze_compare.py -v`

---

### 1.5 — Rename PELT "confidence" to `effect_proxy` (M-10)

**What:** The field `confidence` on PELT change-points is a monotone function of effect size, not a probabilistic confidence. Rename to avoid misleading consumers.

**Plan:**
1. Add `effect_proxy: float` field to `ChangePoint` model (alongside `confidence` for backward compat initially).
2. Populate `effect_proxy = _pelt_confidence_from_effect(d)` in `changepoints_from_pelt`.
3. For BOCPD, `confidence` retains its meaning (posterior mass at MAP run-length) — no rename needed there.
4. In `filter_evidence_change_points`, update the threshold check to use `effect_proxy` for PELT and `confidence` for BOCPD.
5. Update the findings document to explain the distinction.
6. Deprecate `confidence` on PELT change-points in a subsequent cleanup.

**Files changed:** `src/forensics/models/analysis.py`, `src/forensics/analysis/changepoint.py`, `src/forensics/analysis/evidence.py`

**Verification:** `uv run pytest tests/ -v -k changepoint`

---

### 1.6 — Adapt BOCPD hazard rate to author corpus size (M-11)

**What:** Instead of a global `bocpd_hazard_rate`, compute a per-author rate based on the author's article count.

**Plan:**
1. Add `bocpd_hazard_auto: bool = False` to `AnalysisConfig`. When True, compute `hazard_rate = 1.0 / (n_articles / bocpd_expected_changes_per_author)` where `bocpd_expected_changes_per_author: int = 3` (default: expect ~3 style shifts over an author's career).
2. Pass the per-author article count into `_changepoints_for_feature`.
3. Document the auto-calibration in config.toml.

**Files changed:** `src/forensics/config/settings.py`, `src/forensics/analysis/changepoint.py`

**Verification:** Verify that for `mediaite` (188 articles) the effective hazard rate is higher than for `tommy-christopher` (8299 articles).

---

### 1.7 — Investigate and document isaac-schorr self-similarity contradiction (M-12)

**What:** The report cites self_similarity_30d d=−3.503 as evidence of AI assistance, but negative d means more diverse writing post-split, which contradicts AI's tendency toward formulaic similarity.

**Plan:**
1. Pull the raw self_similarity_30d time series for isaac-schorr:
   ```bash
   uv run python -c "
   import polars as pl
   df = pl.read_parquet('data/features/isaac-schorr.parquet')
   print(df.select(['timestamp', 'self_similarity_30d']).filter(pl.col('self_similarity_30d').is_not_null()).sort('timestamp').tail(50))
   "
   ```
2. Determine whether the change-point is a real decrease in similarity or an artifact of the self-similarity window filling up (early articles have no peers → None, later articles have many peers → valid similarity scores; this transition looks like a decrease).
3. If it is a fill-up artifact: exclude self_similarity_30d/90d from the confirmatory feature battery for authors with < MIN_PEERS_FOR_SIMILARITY articles in their early career.
4. Update the findings document to remove this finding from isaac-schorr's supporting evidence if it is an artifact.

**Files changed:** `data/reports/AI_USAGE_FINDINGS.md`, possibly `src/forensics/analysis/evidence.py`

---

### 1.8 — Run section sensitivity for all 4 flagged authors (M-14)

**What:** The J5 gate was BORDERLINE-disabled globally, but the 4 flagged authors should be individually tested.

**Exact steps:**
```bash
# Enable section residualization for one author at a time
uv run forensics analyze --author colby-hall \
  --config-override analysis.section_residualize_features=true \
  --exploratory

uv run forensics analyze --author isaac-schorr \
  --config-override analysis.section_residualize_features=true \
  --exploratory

# Repeat for michael-luciano, mediaite-staff
```

If the pipeline doesn't support `--config-override`, add it (see I-02 plan), or temporarily edit `config.toml`, run, then restore.

**Decision rule:** If section-residualized change-points are significantly fewer than raw change-points (>50% reduction in high-confidence CPs), downgrade the verdict for that author.

**Files changed:** `data/analysis/sensitivity/sensitivity_summary.json`, `data/reports/AI_USAGE_FINDINGS.md`

---

### 1.9 — Raise minimum sample size for hypothesis tests (M-15)

**What:** Replace the `n_pre < 2 or n_post < 2` skip threshold with `n_pre < 10 or n_post < 10`.

**Exact change in `statistics.py:307-316`:**
```python
MIN_SEGMENT_N = 10  # add as module-level constant

if n_pre < MIN_SEGMENT_N or n_post < MIN_SEGMENT_N:
    return _skipped_hypothesis_battery(
        feature_name=feature_name,
        author_id=author_id,
        skipped_reason=f"insufficient_n_pre_or_post (min={MIN_SEGMENT_N})",
        ...
    )
```

Make `MIN_SEGMENT_N` configurable via `AnalysisConfig.hypothesis_min_segment_n: int = 10`.

**Files changed:** `src/forensics/analysis/statistics.py`, `src/forensics/config/settings.py`

**Verification:** `uv run pytest tests/unit/ -v -k hypothesis`

---

### 1.10 — Document autocorrelation limitation (M-16)

For v0.4, documenting the limitation is the right scope. Full HAC correction is a separate research task.

**Plan:**
1. Add to `docs/GUARDRAILS.md` under "Known Statistical Limitations":
   > **Serial autocorrelation not modeled:** Consecutive articles by the same author have correlated stylometric features. Welch t and Mann-Whitney tests assume independence; autocorrelation inflates Type I errors. Current mitigation: the BH family-grouping correction partially offsets this within feature families. Full mitigation requires block bootstrap or HAC-corrected standard errors (planned for Phase 17).
2. Add corresponding caveat to `AI_USAGE_FINDINGS.md` caveats section.

**Files changed:** `docs/GUARDRAILS.md`, `data/reports/AI_USAGE_FINDINGS.md`

---

### 1.11 — Create a ground-truth label set (M-17)

**[HUMAN DECISION]** — Requires human reading and judgment.

**Plan:**
1. For each of the 4 flagged authors, identify 5 articles from before and 5 from after the strongest change-point, sorted by confidence × |d|.
2. Read each article and independently assess: "Would a media critic plausibly identify this as AI-assisted?" Record judgment in a CSV.
3. Additionally source 20 known-AI articles from the Ollama baseline corpus.
4. Run the feature pipeline on all 40+ labeled articles; compute precision and recall of the `ai_marker_frequency >= threshold` classifier.
5. Document results in `docs/GROUND_TRUTH_VALIDATION.md`.

**Files changed:** New `data/ground_truth/labels.csv`, new `docs/GROUND_TRUTH_VALIDATION.md`

**Effort:** Medium (2–4 hours of human reading + 1 hour of code)

---

### 1.12 — Document drift-only channel limitations (M-18, M-19)

**Plan:**
1. Add `convergence_drift_only_pb_threshold` to the preregistration lock commentary explaining why it was added post-hoc (see Phase 0.5).
2. Add to `AI_USAGE_FINDINGS.md` Caveats: "Windows marked `passes_via: drift_only` are the weakest evidence tier. The 0.3 Pipeline B threshold was set post-hoc after observing zero convergence windows for 13/14 authors under the original two-gate logic. These windows should be treated as hypothesis-generating, not hypothesis-confirming."
3. For Pipeline A score: cap `confidence × |d|` at 1.0 per-family before averaging, to prevent a single extreme-d CP from saturating the score:
   ```python
   score = min(1.0, float(cp.confidence) * abs(float(cp.effect_size_cohens_d)))
   # instead of applying min(1.0, ...) only to the mean
   ```

**Files changed:** `src/forensics/analysis/convergence.py:198`, `data/reports/AI_USAGE_FINDINGS.md`

---

### 1.13 — Perform spot-check human reading of strongest change-points (M-22, M-17 support)

**[HUMAN DECISION]** — No code required; essential for credibility.

For `mediaite-staff` and `colby-hall` (strongest BH-sig direct-AI signals):
1. Identify the 5 articles immediately before and 5 after each top-3 change-point by date.
2. Read them. Document: does the writing style visibly change? Does it pattern-match known AI output?
3. Record in `data/ground_truth/spot_checks.md`.

Without this, "the algorithm flagged it" is the only evidence for named individuals.

---

## Phase 2 — Data Quality
**Covers:** D-01, D-02, D-03, D-04, D-05, D-06, D-07, D-08, D-09, D-10
**Effort:** Medium (3–5 days)
**Blocked by:** Nothing, but D-01 (simhash fix) requires re-running dedup, which may change article counts.

---

### 2.1 — Improve simhash text normalization (D-01)

**Exact change in `hashing.py:83`:**
```python
import unicodedata, html, re

def _normalize_for_simhash(text: str) -> str:
    text = html.unescape(text)                    # &amp; → &, &nbsp; → space
    text = unicodedata.normalize("NFKC", text)   # smart quotes → straight, em-dash → -
    text = re.sub(r"\s+", " ", text)              # collapse all whitespace
    return text.strip()

def simhash(text: str, hashbits: int = 128) -> int:
    cleaned = _normalize_for_simhash(text)
    grams = _simhash_char_ngrams(cleaned)
    return _simhash_from_grams(grams, hashbits)
```

After this change, re-run dedup: `uv run forensics scrape --phase dedup`

**Verification:** Check that `data/scrape_errors.jsonl` count doesn't grow and that `is_duplicate` counts change (some previously missed duplicates should now be caught).

---

### 2.2 — Normalize all datetimes to UTC at write time (D-02)

**Exact change in `repository.py` `upsert_article`:**
Ensure every `published_date` stored uses UTC-aware ISO strings with explicit `+00:00`:
```python
def _to_utc_isoformat(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()
```
Apply to `published_date`, `modified_date`, `scraped_at`.

**Files changed:** `src/forensics/storage/repository.py`

**Verification:** `uv run pytest tests/test_storage.py -v`; add a test that confirms a naive datetime input produces a UTC-aware output.

---

### 2.3 — Add per-author scraper coverage report (D-03)

**What:** Write a `data/analysis/scraper_coverage.json` after each scrape run.

**Plan:** Add to `crawler.py` a summary at the end of `_ingest_author_posts`:
```python
coverage = {
    author_slug: {
        "attempted": n_attempted,
        "succeeded": n_succeeded,
        "failed": n_failed,
        "coverage_pct": 100 * n_succeeded / n_attempted if n_attempted else None,
    }
    for author_slug, (n_attempted, n_succeeded, n_failed) in per_author_stats.items()
}
write_json_artifact(paths.project_root / "data/analysis/scraper_coverage.json", coverage)
```

**Files changed:** `src/forensics/scraper/crawler.py`

---

### 2.4 — Deduplicate embedding manifest on write (D-05)

**What:** Before appending to `manifest.jsonl`, remove existing records for the same `(author_id, article_id)`.

**Plan:** In `write_embeddings_manifest` (or the relevant writer), read existing records, filter out duplicates for the current author, then write.

**Files changed:** `src/forensics/storage/parquet.py`

---

### 2.5 — Fix `section_from_url` for year-based paths (D-07)

**Exact change in `utils/url.py`:**
```python
import re
_YEAR_PATTERN = re.compile(r"^\d{4}$")

def section_from_url(url: str) -> str:
    # ... existing logic ...
    first_segment = path.split("/")[1]
    if _YEAR_PATTERN.match(first_segment):
        return "uncategorized"   # or try second segment
    return first_segment
```

**Files changed:** `src/forensics/utils/url.py`

**Verification:** `uv run pytest tests/ -k url -v`; manually verify that `/2024/some-article` returns "uncategorized" not "2024".

---

### 2.6 — Add error handling for malformed metadata JSON (D-08)

**Exact change in `repository.py` `_row_to_article`:**
```python
try:
    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
except json.JSONDecodeError:
    logger.warning("Malformed metadata JSON for article %s, using empty dict", row["id"])
    metadata = {}
```

**Files changed:** `src/forensics/storage/repository.py`

---

### 2.7 — Add word count filter at analysis load time (D-10)

**Exact change in `features/pipeline.py` (the extraction loader):**
```python
articles = [a for a in articles if a.word_count >= settings.scraping.min_word_count]
```

This is already applied at scraper time but not re-verified at extraction time if the threshold changes.

---

## Phase 3 — Code Quality / Reproducibility
**Covers:** C-01, C-02, C-03, C-04, C-05, C-06, C-07, C-08, C-09, C-10, C-11, C-12, P-01, P-02, P-03, P-04, P-05
**Effort:** Medium (3–5 days)

---

### 3.1 — Fix sort tie-breaking for same-day articles (C-01) ← reproducibility blocker

**Exact change in `paths.py` `load_feature_frame_for_author`:**
```python
# Add article ID as secondary sort key to break timestamp ties deterministically
lf = lf.sort(["timestamp", "article_id"], descending=[False, False])
```

**Files changed:** `src/forensics/paths.py`

**Verification:** Create a test that builds a DataFrame with two articles at the same timestamp and verifies the sort is stable across multiple calls: `tests/unit/test_sort_determinism.py`

---

### 3.2 — Remove redundant NaN imputation in `detect_pelt` (C-02)

**What:** `_changepoints_for_feature` already imputes before calling `changepoints_from_pelt`, so `detect_pelt`'s own guard at lines 88-89 fires on pre-imputed data. Remove the guard from `detect_pelt` (or add a comment that it only fires for direct callers, not the main path).

**Option A (safer):** Keep the guard in `detect_pelt` for robustness but add a comment. No functional change.
**Option B (cleaner):** Remove the guard from `detect_pelt`, document that callers must pre-impute. Update `_changepoints_for_feature` to document it provides pre-imputed data.

Recommend Option A for now.

**Files changed:** `src/forensics/analysis/changepoint.py:85-89`

---

### 3.3 — Add zero-norm guard to velocity and pairwise distance (C-03, C-04)

**Exact change in `drift.py`:**
```python
# In track_centroid_velocity, replace cosine() call:
from forensics.analysis.drift import _cosine_similarity  # already defined in module

def track_centroid_velocity(centroids: list[tuple[str, np.ndarray]]) -> list[float]:
    velocities: list[float] = []
    for i in range(1, len(centroids)):
        prev_v = np.asarray(centroids[i - 1][1], dtype=np.float64).ravel()
        cur_v = np.asarray(centroids[i][1], dtype=np.float64).ravel()
        d = 1.0 - _cosine_similarity(prev_v, cur_v)  # cosine_distance = 1 - similarity
        velocities.append(d)
    return velocities

# In _pairwise_mean_cosine_distance, replace cosine() call similarly
```

**Files changed:** `src/forensics/analysis/drift.py:225-234, 259-266`

**Verification:** Add test with a zero-vector embedding and verify the function returns 0.0 not NaN.

---

### 3.4 — Make dedup clear-then-mark atomic (C-05)

**What:** Wrap the clear+mark in a single SQLite transaction so a crash leaves the state consistent.

**Exact change in `repository.py`:**
```python
def clear_and_mark_duplicates(self, all_ids: list[str], duplicate_ids: list[str]) -> None:
    """Atomically clear all flags then mark duplicates in one transaction."""
    with self._lock:
        cur = self._conn.cursor()
        cur.execute("BEGIN")
        try:
            cur.executemany("UPDATE articles SET is_duplicate=0 WHERE id=?",
                          [(aid,) for aid in all_ids])
            if duplicate_ids:
                cur.executemany("UPDATE articles SET is_duplicate=1 WHERE id=?",
                              [(did,) for did in duplicate_ids])
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
```

Then update `dedup.py:162-165` to call `repo.clear_and_mark_duplicates(pool_ids, duplicate_ids)`.

**Files changed:** `src/forensics/storage/repository.py`, `src/forensics/scraper/dedup.py`

---

### 3.5 — Add provenance seeds to config_hash (P-02, P-03, P-04)

**What:** Add `lda_random_state`, `bootstrap_seed`, and `umap_random_state` as `include_in_config_hash` fields.

**Exact changes in `settings.py`:**
```python
# In AnalysisConfig:
lda_random_state: int = Field(default=42, include_in_config_hash=True)
bootstrap_seed: int = Field(default=42, include_in_config_hash=True)
umap_random_state: int = Field(default=42, include_in_config_hash=True)
```

Update `content.py` to use `analysis.lda_random_state` instead of the hardcoded 42.
Update `statistics.py` to accept `seed` from settings instead of defaulting to 42.
Update `drift.py:334` to pass `random_state=settings.analysis.umap_random_state`.

**Files changed:** `src/forensics/config/settings.py`, `src/forensics/features/content.py:208`, `src/forensics/analysis/statistics.py:86`, `src/forensics/analysis/drift.py:334`

**Side effect:** Existing Parquets/JSONs will have a mismatched config_hash after this change. Run `uv run forensics analyze --all-authors --exploratory` to regenerate.

---

### 3.6 — Enforce cross-run config_hash consistency in the report stage (P-01)

**What:** Before the report stage renders, verify all author result JSONs share the same `config_hash`. Reject and warn if any are mismatched.

**Plan:** Add to `src/forensics/reporting/` (or `pipeline.py`) a pre-render validation step:
```python
def validate_config_hash_consistency(result_files: list[Path]) -> None:
    hashes = {}
    for p in result_files:
        data = json.loads(p.read_text())
        hashes[p.name] = data.get("config_hash")
    unique = set(hashes.values()) - {None}
    if len(unique) > 1:
        logger.warning(
            "Cross-run config_hash mismatch: %s — report aggregates artifacts "
            "from different pipeline configurations", hashes
        )
```

**Files changed:** `src/forensics/reporting/` or `src/forensics/pipeline.py`

---

### 3.7 — Fix manifest deduplication read (P-05)

**What:** `_archive_embeddings_if_mismatch` should scan the whole manifest, not just the first line.

**Plan:** Read all records, take the set of unique `model_name`/`model_version` pairs, and trigger archive if any differ from the expected.

**Files changed:** `src/forensics/storage/parquet.py`

---

## Phase 4 — Logging / Observability
**Covers:** L-01, L-02, L-03, L-04, L-05, L-06
**Effort:** Small (1 day)

---

### 4.1 — Write per-window convergence component JSON (L-01)

**What:** For each convergence window, capture `peak_signal`, `sim_signal`, `ai_signal`, `pipeline_b_score` as a structured artifact alongside the existing convergence JSON.

**Plan:** In `_score_single_window`, add component signals as fields on `ConvergenceWindow` (or write a sidecar JSON `{slug}_convergence_components.json`).

---

### 4.2 — Warn on empty comparison targets (L-02)

**Exact change in `orchestrator.py` (wherever comparison_report is written):**
```python
if not comparison_report.get("targets"):
    logger.warning(
        "comparison_report is empty (no target authors configured). "
        "Set at least one author role='target' in config.toml and re-run."
    )
```

---

### 4.3 — Warn when AI baseline is expected but missing (L-03)

**Exact change in `drift.py`:**
```python
ai_vecs = load_ai_baseline_embeddings(slug, paths)
if not ai_vecs:
    baseline_dir = paths.ai_baseline_dir(slug)
    if baseline_dir.is_dir() and any(baseline_dir.rglob("*.npy")):
        logger.warning(
            "drift: AI baseline dir exists for %s but load_ai_baseline_embeddings "
            "returned empty — check path layout expected by _iter_ai_baseline_embedding_paths",
            slug,
        )
    else:
        logger.info("drift: no AI baseline embeddings for %s — ai_baseline_similarity will be null", slug)
```

---

### 4.4 — Add stderr exploratory-mode warning (L-06)

**Exact change in `preregistration.py`:**
```python
if preregistration_status == "missing":
    import sys
    print(
        "\n WARNING: EXPLORATORY MODE: preregistration lock is not filed. "
        "No finding from this run is confirmatory. "
        "Run `uv run forensics lock-preregistration` before confirmatory analysis.\n",
        file=sys.stderr,
    )
```

---

## Phase 5 — Testing
**Covers:** T-01, T-02, T-03, T-04, T-05, T-06, T-07
**Effort:** Medium (2–3 days)

---

### 5.1 — Test comparison analysis with a target author (T-01)

**What:** Add `tests/unit/test_comparison_target_controls.py` (may already exist but is incomplete):
```python
def test_comparison_produces_nonempty_targets(tmp_path, settings_with_target_author):
    """comparison_report.json must have non-empty targets when a target author exists."""
    result = run_comparison(settings=settings_with_target_author, ...)
    assert result["targets"], "comparison_report.targets must not be empty"
```

Use a fixture that sets at least one author to `role="target"`.

---

### 5.2 — Test sort determinism for same-day articles (T-02)

**File:** `tests/unit/test_sort_determinism.py`
```python
def test_feature_frame_sort_is_deterministic_with_same_timestamps():
    """Two calls with the same data must produce identical sort order."""
    # Build a DataFrame with 5 articles sharing the same timestamp
    # Run load_feature_frame_for_author twice, assert row order is identical
```

---

### 5.3 — Property test AI marker false positive rate (T-03)

**File:** `tests/unit/test_ai_marker_precision.py`
```python
# Load data/marker_audit_sample.csv (from Phase 1.1)
# Run extract_lexical_features on each article
# Assert ai_marker_frequency > threshold in < 5% of pre-2020 articles
```

---

### 5.4 — Config hash invalidation test (T-04)

**What:** Add to `tests/unit/test_config_hash.py`:
```python
def test_config_hash_changes_when_analysis_param_changes():
    base = AnalysisConfig()
    modified = AnalysisConfig(hypothesis_min_segment_n=15)
    assert compute_model_config_hash(base) != compute_model_config_hash(modified)

def test_config_hash_unchanged_when_non_hash_param_changes():
    base = AnalysisConfig()
    modified = AnalysisConfig(some_non_hash_field=True)
    assert compute_model_config_hash(base) == compute_model_config_hash(modified)
```

---

### 5.5 — Add dedup atomicity test (T-07)

**File:** `tests/unit/test_dedup_atomicity.py`
```python
def test_dedup_leaves_consistent_state_on_simulated_crash(tmp_path):
    """After clear_and_mark_duplicates fails mid-way, no article should have is_duplicate=0
    when it was 1 before (i.e., state rolls back cleanly)."""
```

---

## Phase 6 — Infrastructure / Configuration
**Covers:** I-01, I-02, I-03, I-04, I-05, I-06
**Effort:** Small (1–2 days)

---

### 6.1 — Add scraper settings to config_hash (I-01)

**What:** Add `scraping.min_word_count`, `scraping.excluded_sections`, `scraping.simhash_threshold` as `include_in_config_hash=True` fields (possibly in a new `ScrapingConfig` hash).

**Note:** This will invalidate all existing Parquets since the hash will change. Coordinate with a planned full re-run.

---

### 6.2 — Adaptive convergence window (I-02)

**What:** Add `convergence_window_auto: bool = False` to `AnalysisConfig`. When True, compute window as `max(60, min(180, int(365 / articles_per_day)))` where `articles_per_day` is the author's median daily output. Pass author article count into the convergence scorer.

---

### 6.3 — Derive `AI_BASELINE_EMBEDDING_DIM` from config (I-04)

**Exact change in `drift.py`:**
```python
# Remove hardcoded constant
# AI_BASELINE_EMBEDDING_DIM = 384

def _expected_embedding_dim(settings: ForensicsSettings) -> int:
    return 384  # derive from model name if a mapping exists
```

For now, this is a documentation fix. The real fix is to load one vector and check its dimension.

---

## Phase 7 — Nits
**Covers:** N-01, N-02, N-03, N-04, N-05, N-06
**Effort:** Small (2–4 hours)

---

### 7.1 — Clean up hedge list (N-01, N-02)

Remove "likely," "possibly" from `_HEDGES` and "stay tuned," "we will keep you updated" from `_CLOSING_PATTERNS` only if Phase 1.1 confirms they have high false positive rates. Do not remove before the audit.

### 7.2 — Add UMAP minimum centroid guard (N-03)

```python
if len(all_vectors) < 4:
    logger.warning("UMAP skipped: fewer than 4 data points (%d)", len(all_vectors))
    return {"projections": {}, "ai_projection": None}
```

### 7.3 — Propagate AI marker version to Parquet feature records (N-04)

Add `ai_marker_list_version: str` to `LexicalFeatures` model, populated from `AI_MARKER_LIST_VERSION`. This creates a provenance trail in the Parquet files.

### 7.4 — Fix `run_metadata.json` author field name (N-06)

Rename the `author` field in `run_metadata.json` output to `last_single_author_run` with a comment that it only applies to single-author runs, not the parallel refresh.

---

## Dependency Graph

```
Phase 0 (blockers)
  └─ 0.2 (set target author)
       └─ 0.3 (run comparison)  ← blocked by 0.2
  └─ 0.4 (run baseline)         ← independent, needs Ollama
  └─ 0.1 (preregistration)      ← needs 0.5 (threshold docs) first
  └─ 0.5 (document Fix-F/G)     ← independent
  └─ 0.6 (downgrade verdicts)   ← independent

Phase 1 (methodology)
  └─ 1.1 (marker audit)         ← [HUMAN DECISION] first
       └─ 7.1 (nit cleanup)     ← blocked by 1.1
  └─ 1.3 (external controls)    ← [HUMAN DECISION] first
  └─ 1.7 (isaac-schorr contra.) ← needs raw data read
  └─ 1.8 (section sensitivity)  ← needs 0.2 done
  └─ 1.13 (human spot-check)    ← [HUMAN DECISION] first

Phase 2 (data quality)
  └─ 2.1 (simhash norm)         ← independent; re-runs dedup
  └─ 2.2 (UTC datetimes)        ← independent; re-run scrape
  └─ 2.4 (manifest dedup)       ← independent

Phase 3 (code quality)
  └─ 3.5 (seeds to config_hash) ← requires full re-run after
  └─ 3.1 (sort tie-breaking)    ← blocks T-02
  └─ 3.4 (atomic dedup)         ← blocks T-07

Phase 4 (logging)               ← independent of above
Phase 5 (testing)               ← blocked by 3.1, 3.4
Phase 6 (infrastructure)        ← independent
Phase 7 (nits)                  ← blocked by 1.1
```

---

## Human Decision Checklist

Before Phase 1 can begin in earnest, the following require explicit human decisions:

| Item | Decision Required | Options |
|------|-------------------|---------|
| M-01 / 0.1 | Which thresholds to preregister — original (0.5) or post-hoc (0.3)? | (a) revert + lock; (b) lock current + document as exploratory |
| M-06 / 1.1 | Which of the 16 marker phrases to remove after audit | Audit first, then decide |
| M-08 / 1.3 | Which external publication(s) to add as controls | Editorial + legal judgment |
| M-17 / 1.11 | Who performs the human reading of flagged articles | Journalist / researcher |
| M-22 / 1.13 | Spot-check reading of strongest change-points | Journalist / researcher |
| R-01 / 0.6 | Exact wording of the exploratory-status disclosure | Editorial judgment |

---

## First Concrete Next Step

Run this right now to start:

```bash
cd /Users/johneakin/PyCharmProjects/mediaite-ghostink

# Step 1: Set colby-hall as target (M-04)
# Edit config.toml: change colby-hall role from "control" to "target"
# (manual edit, 30 seconds)

# Step 2: Add exploratory disclosure to findings document (R-01)
# (manual edit, 5 minutes)

# Step 3: Document Fix-F and Fix-G in the amendment file (M-05)
# (manual edit, 10 minutes)

# Step 4: Run the comparison with the new target author (M-03)
uv run forensics analyze --author colby-hall --exploratory

# Step 5: Check if AI baseline dir exists and what it contains
ls -la data/baseline/

# Step 6: If Ollama is running, kick off baseline generation (M-02)
ollama list  # verify model availability
uv run forensics baseline --author colby-hall

# Step 7: File the preregistration lock (M-01)
# (after deciding which thresholds to lock — human decision above)
uv run forensics lock-preregistration
```

Total estimated time for Phase 0: **2–4 hours** (mostly editorial/decision time, not code).
Total estimated time for all phases: **4–6 weeks** of focused work.
