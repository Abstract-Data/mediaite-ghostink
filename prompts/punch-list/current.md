# mediaite-ghostink — Complete Forensic Punch List

Version: 0.1.0
Status: active
Last Updated: 2026-04-26
Model: claude-sonnet-4-6

---

**Pipeline version:** Phase 16 (post-adversarial-review-remediation)
**Total issues:** 92 across 9 categories

This document enumerates every identified problem with the pipeline's methodology, code, data, infrastructure, reporting, reproducibility, observability, and test coverage. Issues are identified by short-code (e.g. M-01) so the [implementation plan](../implementation-plan/current.md) can reference them directly.

Severity scale: **CRITICAL** → **HIGH** → **MEDIUM** → **LOW** → **NIT**

**Phase 0 status (2026-04-26):** M-01, M-02, M-03, M-04 (verify), M-05, and R-01–R-09 are addressed in-repo (lock, amendment, comparison JSON, drift metric continuity, findings narrative). See [CHANGELOG § Phase 0 closure](CHANGELOG.md) for the ID → artifact map. **All punch IDs (M/C/D/I/R/P/L/T/N):** full remediation index in [`docs/punch-list-closure-index.md`](../../docs/punch-list-closure-index.md). Rows below retain the original audit wording for traceability; where they contradict shipped fixes, the CHANGELOG / artifacts win.

---

## A. Methodology — Forensic / Statistical / Conceptual

**M-01** | **Preregistration lock is an unfilled template** | **CRITICAL**
`data/preregistration/preregistration_lock.json` is `{"locked_at": null}`. Every run uses `--exploratory`. The project's own rules (AGENTS.md, preregistration.py) require a locked preregistration before any finding is confirmatory. The findings document presents "HIGH confidence" verdicts anyway.
_Location: `data/preregistration/preregistration_lock.json`, `src/forensics/preregistration.py`_

**M-02** | **`ai_baseline_similarity` is null for all 14 authors** | **CRITICAL**
The most direct Pipeline B signal — cosine similarity to known-AI-generated control text — was never populated. `load_ai_baseline_embeddings` returns empty for every author because no `.npy` files exist in the expected paths. All findings rest on intra-author drift, not "is this author drifting toward AI-like text."
_Location: `src/forensics/analysis/drift.py:479-489`, `data/baseline/`_

**M-03** | **`comparison_report.json` is `{"targets": {}}` — comparison was never run** | **CRITICAL**
The target-vs-control comparison requires at least one author with `role = "target"` in config.toml. Every author is `role = "control"`. The comparison stage has never executed against this corpus.
_Location: `config.toml`, `src/forensics/analysis/comparison.py`_

**M-04** | **All config.toml authors are `role = "control"`** | **CRITICAL**
AGENTS.md explicitly states `colby-hall` should be `role = "target"`, yet config.toml sets all authors to `"control"`. The comparison analysis stage has never executed against this corpus.
_Location: `config.toml`_

**M-05** | **Post-hoc threshold changes bypass preregistration intent** | **CRITICAL**
`PIPELINE_SCORE_PASS_THRESHOLD` was lowered from 0.5 → 0.3 (Fix-F) and `DRIFT_ONLY_PB_THRESHOLD = 0.3` was added (Fix-G) after observing that the original thresholds produced zero convergence windows for 13 of 14 authors. These are data-driven threshold reductions made after seeing results — exactly what preregistration prevents.
_Location: `src/forensics/analysis/convergence.py:25-41`_

**M-06** | **AI marker list includes unremarkable journalism vocabulary** | **HIGH**
"arguably," "navigate," "underscores," "serves as a," "represents a significant" are standard political journalism phrases. 11 of michael-luciano's 45 "AI marker" increases and 10 of colby-hall's 21 pre-date ChatGPT — direct evidence the list fires on natural style, not AI adoption.
_Location: `src/forensics/features/lexical.py:68-85`_

**M-07** | **`mediaite-staff` finding is confounded by multi-author byline** | **HIGH**
Bigram entropy d=+4.68 for a pooled byline grows with staff size and composition changes: more diverse writers → more diverse n-grams. This confound is acknowledged in the findings document but the finding is still presented as Rank 1 evidence.
_Location: `data/reports/AI_USAGE_FINDINGS.md:94-95`_

**M-08** | **Control group is internal to Mediaite** | **HIGH**
All 12 authors are at the same outlet. Shared editorial changes (new CMS, house-style rules, copy-desk policy) produce outlet-wide coordinated shifts that are indistinguishable from individual AI adoption without an external control group.
_Location: `config.toml` (no external-control authors configured)_

**M-09** | **BH correction is per-author, not cross-investigation** | **HIGH**
FDR is controlled within each author's test battery. With 14 authors × ~11,000 tests each, the investigation-level false-discovery rate is uncontrolled. A second BH pass across all authors' best p-values is needed.
_Location: `src/forensics/analysis/statistics.py:439-462`_

**M-10** | **PELT "confidence" is a monotone transform of effect size, not a statistical confidence** | **HIGH**
`_pelt_confidence_from_effect` returns `|d|/(|d|+1)` — this is bounded in [0,1] but is definitionally the same information as Cohen's d. Labeling it "confidence" implies a probabilistic interpretation it does not have.
_Location: `src/forensics/analysis/changepoint.py:386-388`_

**M-11** | **BOCPD hazard rate 1/250 is not adapted to author corpus size** | **HIGH**
The hazard prior encodes "expected one change every 250 articles." For `mediaite` (188 total articles) the expected change is outside the corpus. For `tommy-christopher` (8,299 articles) this produces ~33 expected change-points. Neither extreme is validated.
_Location: `src/forensics/analysis/changepoint.py:332`, `config.toml`_

**M-12** | **isaac-schorr's strongest corroborating signal is directionally inconsistent** | **HIGH**
The report cites `self_similarity_30d` d=−3.503 (BH p≈4e-10) as evidence of AI assistance. Negative d means POST-split articles are MORE diverse in TF-IDF space than PRE-split. AI models produce more formulaically similar text, not more diverse — this finding contradicts the hypothesis.
_Location: `data/reports/AI_USAGE_FINDINGS.md:109`_

**M-13** | **Pre-registered split date (Nov 1 2022) predates the strongest evidence cited** | **MEDIUM**
The most compelling individual finding (isaac-schorr: 29 of 31 increases post-Dec 2023) keys on a date 13 months after the pre-registered split. Using a different temporal anchor to identify the best evidence is exploratory, not confirmatory.
_Location: `data/preregistration/preregistration_lock.json`, `data/reports/AI_USAGE_FINDINGS.md`_

**M-14** | **Section residualization skipped for the 4 flagged authors** | **MEDIUM**
J5 gate returned BORDERLINE and was disabled globally. But colby-hall almost certainly covers specific sections disproportionately; section-driven style changes are the most plausible alternative to AI for his formula_opening_score pattern. Section sensitivity analysis was run only for ken-meyer (who was not flagged).
_Location: `data/analysis/sensitivity/sensitivity_summary.json`, `config.toml`_

**M-15** | **Minimum sample size for hypothesis tests is n=2** | **MEDIUM**
`run_hypothesis_tests` skips when `n_pre < 2 or n_post < 2`. Welch's t-test with n=2 per group has 1 degree of freedom and near-zero power; resulting p-values are unreliable.
_Location: `src/forensics/analysis/statistics.py:307-316`_

**M-16** | **Serial autocorrelation in consecutive articles is not modeled** | **MEDIUM**
An author's stylometric features on adjacent articles are serially correlated. Welch t and Mann-Whitney assume independence. Autocorrelation inflates Type I errors. No HAC correction or block bootstrap is applied.
_Location: `src/forensics/analysis/statistics.py:320, 341`_

**M-17** | **No ground truth labels exist anywhere in the corpus** | **MEDIUM**
Not one article is labeled AI-generated or human-written. Precision, recall, and false positive rate of the pipeline are entirely unknown on real journalism data.

**M-18** | **Convergence drift-only channel (Fix-G) has an extremely low bar** | **MEDIUM**
`passes_drift_only = pipeline_b_score >= 0.3` — Pipeline B scores can reach 0.3 with modest centroid velocity variation that has nothing to do with AI. This channel was added post-hoc specifically to avoid zero convergence windows for 13/14 authors.
_Location: `src/forensics/analysis/convergence.py:510`_

**M-19** | **Pipeline A score is clipped mean of unbounded `confidence × |d|` values** | **MEDIUM**
`confidence × |d|` can exceed 1.0 when |d| > 1. Clipping to [0,1] means a single extreme-effect-size CP saturates the family score, overstating convergence.
_Location: `src/forensics/analysis/convergence.py:209`_

**M-20** | **No external validation of AI marker phrase effectiveness** | **MEDIUM**
`AI_MARKER_LIST_VERSION = "0.1.0"`. No precision/recall numbers from a labeled corpus exist anywhere. The list has never been tested against actual AI-generated vs human-written news journalism.
_Location: `src/forensics/features/lexical.py:11`_

**M-21** | **`formula_opening/closing` patterns fire on standard news attribution language** | **MEDIUM**
"according to reports," "as * reported," "time will tell," "stay tuned," "we will keep you updated" are common in breaking news coverage without any AI involvement.
_Location: `src/forensics/features/content.py:136-148`_

**M-22** | **Observational design with no causal identification strategy** | **MEDIUM**
No instrument, no natural experiment, no difference-in-differences setup. Alternative explanations (beat change, editorial formatting, syndicated content, copy-desk voice standardization) cannot be ruled out by the pipeline.

**M-23** | **PELT penalty base value has no documented calibration** | **LOW**
`pelt_penalty` is tuned empirically. No calibration report publishes the false positive rate at the current penalty setting against synthetic null data.
_Location: `config.toml`, `data/provenance/apr24_rbf_profile.txt`_

---

## B. Code Quality — Bugs, Brittleness, Reproducibility

**C-01** | **Polars sort tie-breaking is non-deterministic for same-day articles** | **HIGH**
`timestamps_from_frame` sorts by `timestamp`; WordPress articles published the same day without sub-day resolution sort arbitrarily. PELT/BOCPD results are not bit-reproducible.
_Location: `src/forensics/utils/datetime.py:34-40`, `src/forensics/analysis/changepoint.py:613`_

**C-02** | **PELT NaN imputation applied twice** | **MEDIUM**
`detect_pelt` (line 88-89) has its own `np.nan_to_num` guard. `_changepoints_for_feature` (line 521-522) also applies `np.nan_to_num` before calling `changepoints_from_pelt`. PELT receives pre-imputed values but `detect_pelt` imputes again, which is redundant.
_Location: `src/forensics/analysis/changepoint.py:88-89, 521-522`_

**C-03** | **`track_centroid_velocity` calls `scipy.spatial.distance.cosine` without zero-norm guard** | **MEDIUM**
The module-level helper `_cosine_similarity` has a zero-norm guard but isn't used in this path. A month where all articles produce zero embeddings would produce NaN velocity. The downstream `isfinite` check fixes the symptom but not the root cause.
_Location: `src/forensics/analysis/drift.py:225-234`_

**C-04** | **`_pairwise_mean_cosine_distance` has the same zero-norm issue** | **MEDIUM**
Line 263 calls `cosine()` directly without checking norms; the `isfinite` filter silently drops those pairs rather than surfacing the root cause.
_Location: `src/forensics/analysis/drift.py:259-266`_

**C-05** | **`deduplicate_articles` non-atomic clear-then-mark** | **MEDIUM**
`clear_duplicate_flags(pool_ids)` then `mark_duplicates(duplicate_ids)` — a crash between these two operations leaves the entire corpus un-deduplicated with no detection mechanism.
_Location: `src/forensics/scraper/dedup.py:162-165`_

**C-06** | **Analysis stage opens SQLite `Repository` directly** | **MEDIUM**
`changepoint.py`, `drift.py`, and `comparison.py` all open `Repository` contexts. The analyze stage should read only from Parquet/JSON artifacts per the stage-boundary contract in AGENTS.md.
_Location: `src/forensics/analysis/changepoint.py:694`, `src/forensics/analysis/drift.py:440`_

**C-07** | **`_cohens_d_meta` duplicates arithmetic from `cohens_d`** | **LOW**
The private helper calls `cohens_d(a, b)` then recomputes `pooled_std` with identical formulas to determine degeneracy. The duplication risks the two paths diverging on edge cases.
_Location: `src/forensics/analysis/statistics.py:148-179`_

**C-08** | **`ConvergenceWindow` legacy construction catches `(TypeError, ValueError)` broadly** | **LOW**
The fallback path at line 538-548 swallows legitimate validation errors from malformed input under the guise of "pre-Unit-4 compatibility."
_Location: `src/forensics/analysis/convergence.py:525-548`_

**C-09** | **`ProcessPoolExecutor` on macOS uses `spawn` context without explicit declaration** | **LOW**
Each of the 3 worker processes reimports the full forensics package (spaCy, sentence-transformers, ruptures). On non-macOS systems `fork` may be used, which is unsafe with these libraries. No explicit context manager ensures consistent behavior.
_Location: `src/forensics/analysis/orchestrator.py`_

**C-10** | **`content.py` fallback `cfg = analysis or AnalysisConfig()`** | **LOW**
When `analysis=None`, a new `AnalysisConfig()` with default settings is used. Callers that pass `None` silently get different LDA parameters than the configured pipeline.
_Location: `src/forensics/features/content.py:226`_

**C-11** | **LRU cache in `content.py` is process-scoped** | **LOW**
With `ProcessPoolExecutor`, each worker gets an empty `_self_similarity_cache`; cross-author cache benefits are lost in the parallel execution path.
_Location: `src/forensics/features/content.py:27-28`_

**C-12** | **`_recent_peer_texts` is O(n²) per author** | **LOW**
For each article at index `i`, iterates all prior articles in the time window. For an 8,000-article author this is tens of millions of comparisons total.
_Location: `src/forensics/features/content.py` (peer-window construction)_

---

## C. Data / Corpus Issues

**D-01** | **Simhash text normalization too minimal** | **HIGH**
`simhash()` only replaces `\n` with space. Smart quotes (', '), em-dashes (—), HTML entities (`&amp;`, `&nbsp;`), and multiple-whitespace sequences produce different fingerprints for the same article re-scraped with slightly different HTML parsing, causing missed near-duplicates.
_Location: `src/forensics/utils/hashing.py:83`_

**D-02** | **Mixed timezone-aware and naive datetimes in the same corpus** | **MEDIUM**
`parse_wp_datetime` stores WordPress dates as UTC-aware; `parse_datetime` default leaves naive datetimes naive. If any articles were inserted via direct SQL or older scraper versions, datetime comparisons within the same author's feature frame could fail silently or reorder articles incorrectly.
_Location: `src/forensics/utils/datetime.py:10-31`_

**D-03** | **Scraper coverage is unaudited in any report** | **MEDIUM**
`data/scrape_errors.jsonl` is 111KB but no finding document reports per-author coverage rates. If errors cluster on specific authors, their feature time series have gaps that bias change-point detection.
_Location: `data/scrape_errors.jsonl`, `data/reports/AI_USAGE_FINDINGS.md`_

**D-04** | **`content_hash` uses SHA-256 but simhash migrated to xxhash** | **MEDIUM**
`content_hash` (article identity) uses SHA-256; `simhash` (near-duplicate) switched to xxhash. Any pre-migration `dedup_simhash` column values stored in SQLite are incompatible with the live algorithm but no migration recomputes them.
_Location: `src/forensics/utils/hashing.py:10-12, 69`_

**D-05** | **Embedding manifest is append-only with no deduplication** | **MEDIUM**
If feature extraction is re-run, new records are appended to `manifest.jsonl`. Duplicate `(author_id, article_id)` entries will cause the drift stage to double-load embeddings without warning.
_Location: `src/forensics/storage/parquet.py`_

**D-06** | **`articles.jsonl` and SQLite are not locked in sync** | **LOW**
The 262MB JSONL export is a snapshot from a prior run. If subsequent scrapes added articles to SQLite, downstream tools reading the JSONL get a stale corpus; no pipeline step detects or warns about this drift.
_Location: `data/articles.jsonl`, `src/forensics/storage/export.py`_

**D-07** | **`section_from_url` returns year strings for year-based URL paths** | **LOW**
URLs like `/2024/some-article` produce section tag "2024". These appear in the Kruskal-Wallis section diagnostics, polluting the section-distinctiveness analysis.
_Location: `src/forensics/utils/url.py`_

**D-08** | **`metadata` column is unstructured JSON with no error handling** | **LOW**
`_row_to_article` calls `json.loads()` on raw metadata; malformed JSON from the WordPress API raises `JSONDecodeError` and halts the entire author batch read.
_Location: `src/forensics/storage/repository.py` (`_row_to_article`)_

**D-09** | **No re-scrape / freshness policy for the corpus** | **LOW**
Articles scraped in 2023-2024 may have been corrected, updated, or deleted on the live site. The corpus is a static snapshot with no staleness detection or partial refresh mechanism.

**D-10** | **Word count filter applied at extraction but not at analysis** | **LOW**
Articles just above the 50-word threshold still get feature vectors. `ai_marker_frequency` normalized by sentence count can be wildly inflated for 3-sentence articles that pass the filter.
_Location: `src/forensics/features/pipeline.py`_

---

## D. Configuration / Infrastructure Issues

**I-01** | **`config_hash` does not cover scraper settings** | **MEDIUM**
If scraper parameters change (e.g., excluded sections, word count filter) between runs, existing feature Parquets are not invalidated. The hash only covers `AnalysisConfig` fields.
_Location: `src/forensics/config/fingerprint.py`_

**I-02** | **`convergence_window_days = 90` is not calibrated to posting frequency** | **MEDIUM**
For a low-volume author a 90-day window contains very few articles; for `tommy-christopher` (8,299 articles) the same window spans hundreds. Window length should scale to articles/day.
_Location: `config.toml`_

**I-03** | **`baseline_embedding_count = 20` is not sensitivity-tested** | **LOW**
The Pipeline B baseline is the centroid of the first 20 articles. For authors whose first 20 articles span years of career development, this may not represent a stable "pre-AI" baseline.
_Location: `config.toml`, `src/forensics/analysis/drift.py:243`_

**I-04** | **`AI_BASELINE_EMBEDDING_DIM = 384` is hardcoded** | **LOW**
If the embedding model changes, this constant needs manual updating rather than being derived from the configured model.
_Location: `src/forensics/analysis/drift.py:37`_

**I-05** | **No disk space check before long-running pipeline stages** | **LOW**
Writing NPZ, Parquet, and JSON for 12+ authors with large embedding matrices (~75MB per author) can fill disks without warning.

**I-06** | **No pipeline-level idempotency check for partial reruns** | **LOW**
Re-running after a crash overwrites already-completed author artifacts without verifying they were complete. A partial result from a crashed run is indistinguishable from a complete one.

---

## E. Documentation / Reporting Issues

**R-01** | **"HIGH confidence" verdict directly contradicts `preregistration_status: "missing"`** | **CRITICAL**
The findings table header is "AI-ASSISTED — HIGH confidence." The `run_metadata.json` says "analysis is exploratory, not confirmatory." These directly contradict each other.
_Location: `data/reports/AI_USAGE_FINDINGS.md:86`, `data/analysis/run_metadata.json`_

**R-02** | **`comparison_report.json` is listed as a data source but is empty** | **HIGH**
The "Files this report draws on" section cites `comparison_report.json`, which contains `{"targets": {}}`. The report implies comparison analysis was performed when it was not.
_Location: `data/reports/AI_USAGE_FINDINGS.md:167-171`_

**R-03** | **Report claims 14 authors analyzed; latest run refreshed only 12** | **MEDIUM**
`run_metadata.json` shows 12 authors in the parallel refresh. `mediaite` and `mediaite-staff` result files are from an earlier run with a different `config_hash`.
_Location: `data/reports/AI_USAGE_FINDINGS.md:6`_

**R-04** | **Section residualization skip is not disclosed in the findings document** | **MEDIUM**
The BORDERLINE J5 gate decision (and its implication that section-coverage confounds are untested) is buried in `section_profile_report.md`, not mentioned in `AI_USAGE_FINDINGS.md`.
_Location: `data/reports/AI_USAGE_FINDINGS.md`, `data/analysis/section_profile_report.md`_

**R-05** | **`mediaite-staff` and named individuals ranked in the same table without methodology caveat** | **MEDIUM**
Aggregate bylines and individual authors are methodologically different populations. Mixing them in a single ranked table without a disclosure is misleading.
_Location: `data/reports/AI_USAGE_FINDINGS.md:26-41`_

**R-06** | **Bigram_entropy d=+4.68 presented as primary evidence despite acknowledged confound** | **MEDIUM**
The report notes "more diverse n-grams than a single human author" (consistent with multi-author pooling) but still cites this as the top signal and uses it to justify a HIGH confidence verdict.
_Location: `data/reports/AI_USAGE_FINDINGS.md:92-96`_

**R-07** | **`AI_MARKER_LIST_VERSION = "0.1.0"` is never disclosed in any report** | **MEDIUM**
The marker list has a version number suggesting it is under development, but no report documents what changed between versions or that a version concept exists.
_Location: `src/forensics/features/lexical.py:11`_

**R-08** | **Per-author determination criteria (A–D) are not shown per row in the verdict table** | **LOW**
The criteria (A: BH-sig direct test, B: ≥5 post-ChatGPT increases, C: AB-pass > 50, D: ratio ≥ 3:1) are defined once but never displayed per-author; readers cannot verify verdicts from the table alone.
_Location: `data/reports/AI_USAGE_FINDINGS.md:26-41`_

**R-09** | **"Cross-corpus signals" section is inaccurate about the most recent run** | **LOW**
"The most recent run was scoped to `zachary-leeman`" is wrong; `run_metadata.json` shows the most recent run was the 12-author parallel refresh.
_Location: `data/reports/AI_USAGE_FINDINGS.md:169`_

---

## F. Reproducibility / Provenance Gaps

**P-01** | **Per-author result files span multiple distinct pipeline runs with different config hashes** | **HIGH**
The report aggregates `mediaite`/`mediaite-staff` artifacts (April 24 run) with 12 other authors (April 26 parallel refresh). These runs had different `config_hash` values. The report stage should reject mismatched hashes but does not enforce this cross-run.
_Location: `data/analysis/run_metadata.json`, `src/forensics/reporting/`_

**P-02** | **LDA `random_state=42` is not part of the `config_hash`** | **MEDIUM**
The seed is hardcoded in `content.py:208` rather than drawn from config. Changing it won't invalidate Parquet files that used the old seed.
_Location: `src/forensics/features/content.py:208`, `src/forensics/config/fingerprint.py`_

**P-03** | **Bootstrap CI seed (42) is not in `config_hash`** | **MEDIUM**
`bootstrap_ci` defaults to `seed=42`. The seed is not a config parameter and not part of the hash; stored CI values in hypothesis test JSONs are silently invalidated if the seed changes.
_Location: `src/forensics/analysis/statistics.py:86`_

**P-04** | **UMAP `random_state=42` is not in `config_hash`** | **LOW**
UMAP projections would change if the seed changed, but cached `_umap.json` files would not be invalidated.
_Location: `src/forensics/analysis/drift.py:334`_

**P-05** | **`_archive_embeddings_if_mismatch` reads only the first line of `manifest.jsonl`** | **LOW**
A partially rewritten manifest with a correct first line but stale later entries won't be detected; the mismatch check passes while later entries reference wrong embeddings.
_Location: `src/forensics/storage/parquet.py`_

---

## G. Logging / Observability Gaps

**L-01** | **No structured artifact capturing per-window convergence components** | **MEDIUM**
The `peak_signal`, `sim_signal`, `ai_signal` values per convergence window are logged at DEBUG only. There is no JSON artifact storing these per-window intermediate scores, making post-hoc diagnosis require log replay.
_Location: `src/forensics/analysis/convergence.py:492-500`_

**L-02** | **No warning when `comparison_report.json` produces empty targets** | **MEDIUM**
The orchestrator writes `{"targets": {}}` without any WARNING that comparison analysis ran but produced no results.
_Location: `src/forensics/analysis/orchestrator.py`_

**L-03** | **No warning when AI baseline embeddings are expected but empty** | **MEDIUM**
`compute_author_drift_pipeline` silently proceeds with `ai_conv = None` when `load_ai_baseline_embeddings` returns empty, with no log warning distinguishing "no baseline corpus" from "baseline exists but failed to load."
_Location: `src/forensics/analysis/drift.py:699-700`_

**L-04** | **Scraper produces no per-author coverage summary artifact** | **LOW**
Total articles attempted vs. successfully scraped is not summarized per author in any artifact; `scrape_errors.jsonl` requires manual parsing to get per-author failure rates.
_Location: `src/forensics/scraper/crawler.py`_

**L-05** | **NaN imputation count per feature per author is not logged in a structured artifact** | **LOW**
`_changepoints_for_feature` imputes NaN to median but neither logs the count nor writes it to any artifact; imputation-heavy authors are silent.
_Location: `src/forensics/analysis/changepoint.py:521-522`_

**L-06** | **`preregistration_status: "missing"` produces no stderr warning** | **LOW**
The status is written to `run_metadata.json` but the operator sees no visible terminal warning that findings are exploratory only.
_Location: `src/forensics/preregistration.py`_

---

## H. Testing Gaps

**T-01** | **No regression test for `comparison_report.json` being non-empty when targets exist** | **HIGH**
The comparison path can silently produce empty output; no test exercises it with at least one target author.
_Location: `tests/unit/test_comparison_target_controls.py` (likely incomplete)_

**T-02** | **No test verifying PELT/BOCPD output is deterministic for same-day articles** | **MEDIUM**
No test constructs a fixture with duplicate timestamps and verifies identical output across two runs.

**T-03** | **No property test for AI marker false positive rate on pre-2020 journalism** | **MEDIUM**
`test_lexical_hypothesis.py` uses `hypothesis`-generated text, not realistic journalism fixtures. The false positive rate of the 16-phrase marker list on real pre-AI news articles is untested.
_Location: `tests/test_features.py`, `tests/unit/`_

**T-04** | **No test verifying `config_hash` changes when a relevant parameter is modified** | **MEDIUM**
The hash invalidation mechanism is critical to forensic reproducibility, but no test confirms that adding a new `include_in_config_hash` field changes the hash, or that hash mismatches are correctly rejected at the report stage.
_Location: `tests/unit/test_config_hash.py`_

**T-05** | **77.78% coverage; new analysis modules have unknown individual per-module coverage** | **MEDIUM**
`analysis/section_mix.py`, `section_contrast.py`, `permutation.py`, `era.py` are recent additions. Per-module coverage is not broken out in CI output.

**T-06** | **No adversarial/fuzz test for HTML parsing producing zero-word-count articles** | **LOW**
`scraper/parser.py` processes arbitrary third-party HTML. No property test verifies it doesn't produce empty `clean_text` strings that pass the word count filter.
_Location: `tests/test_scraper.py`_

**T-07** | **No test for non-atomic dedup clear-then-mark interruption** | **LOW**
`deduplicate_articles` clears all flags then re-marks duplicates. No test verifies the database state is detectable as corrupted if interrupted between these two operations.
_Location: `tests/test_dedup_banding.py`_

---

## I. Miscellaneous / Nits

**N-01** | **`_hedges` includes "likely" and "possibly"** | **LOW**
These are standard journalism hedges present in every article about unconfirmed reports; including them in a forensic AI marker list adds systematic noise.
_Location: `src/forensics/features/content.py:155-166`_

**N-02** | **`_CLOSING_PATTERNS` fire on breaking-news language** | **LOW**
"stay tuned," "we will keep you updated" are common in live-coverage posts and have nothing to do with AI generation.
_Location: `src/forensics/features/content.py:144-148`_

**N-03** | **UMAP 2D projection for authors with < 4 monthly centroids is meaningless** | **LOW**
No minimum threshold exists; UMAP with 2–3 points produces degenerate or misleading visualizations without raising.
_Location: `src/forensics/analysis/drift.py:355-380`_

**N-04** | **`AI_MARKER_LIST_VERSION` not propagated to Parquet feature records** | **NIT**
If the marker list is updated, old Parquets become incompatible with new ones but there's no version tag in the schema to detect it.
_Location: `src/forensics/features/lexical.py:11`_

**N-05** | **`DriftScores.velocity_acceleration_ratio` imports at property call time** | **NIT**
Every access triggers a module-level import lookup, adding unnecessary overhead in hot rendering paths.
_Location: `src/forensics/models/analysis.py`_

**N-06** | **`run_metadata.json` `author` field contains "tom-durante"** | **NIT**
The single-author field captures the last author processed, which is irrelevant when the parallel refresh processed 12 authors. Misleading key name.
_Location: `data/analysis/run_metadata.json`_

---

## Top 5 to Fix Before Any Public Claim

These five are the minimum before any finding can be called anything other than preliminary:

1. **M-01** — File `uv run forensics lock-preregistration` to create a real lock file. No confirmatory analysis without this.
2. **M-02** — Run `uv run forensics baseline` against the generated Ollama corpus to populate `ai_baseline_similarity`.
3. **M-04 → M-03** — Set `colby-hall.role = "target"` in config.toml, then run comparison analysis to produce a non-empty `comparison_report.json`.
4. **M-05** — Document Fix-F and Fix-G threshold changes as exploratory post-hoc adjustments in `data/preregistration/amendment_phase15.md` and the findings document. Do not present findings using these thresholds as confirmatory.
5. **R-01** — Change "AI-ASSISTED — HIGH confidence" and all confidence-level verdict headers in `AI_USAGE_FINDINGS.md` to "EXPLORATORY SIGNAL" with the preregistration caveat as the first visible disclosure.
