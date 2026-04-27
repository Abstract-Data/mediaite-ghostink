# Mediaite AI-Writing Forensics — Cross-Author Findings Report

**Generated:** 2026-04-26 (narrative refresh; primary quantitative run remains 2026-04-24)
**Pipeline run (narrative baseline):** `5d0fd46a-1949-41e0-b88b-e742e244d1cc` (completed 2026-04-24 20:12 UTC)
**Corpus hash:** `a2dd2579990b`
**Authors with persisted artifacts in `data/analysis/`:** 14 (12 configured individuals in `config.toml` + 2 byline-aggregates: `mediaite`, `mediaite-staff`)

---

## Executive Summary

> **Status: EXPLORATORY — NOT CONFIRMATORY**
>
> A preregistration lock is on disk (`data/preregistration/preregistration_lock.json`, `preregistration_status: "ok"` on confirmatory-mode runs). Post-hoc convergence threshold edits (**Fix-F** and **Fix-G**) are documented as **exploratory only** in `data/preregistration/amendment_phase15.md`; they are not independent, prospectively preregistered choices. `data/analysis/comparison_report.json` is now populated for the configured target (`colby-hall`) versus controls. `ai_baseline_similarity` in `*_drift.json` is **non-null** after a Phase 0 continuity pass: run `uv run python scripts/seed_phase0_ai_baseline_stubs.py` (ignored under `data/ai_baseline/`) then refresh drift per `docs/RUNBOOK.md`. Stub vectors are **not** model-generated text; treat the metric as a mechanical cosine-to-centroid readout until Ollama-backed baseline generation completes.
>
> See [punch-list](../../prompts/punch-list/current.md) for the broader remediation backlog. Do not present any row below as a confirmed forensic outcome.

Of the 14 authors/bylines with analysis artifacts, **`mediaite-staff`** shows the strongest **exploratory** multi-method signal (pooled byline — see table caveat). **Three named writers — `isaac-schorr`, `michael-luciano`, and `colby-hall` — show moderate exploratory signals**, with caveats below. **`alex-griffing`** shows a weak, isolated signal. The remaining nine rows are interpreted as no clear adoption pattern in this exploratory pass; several show the opposite pattern (decrease in AI markers over time).

These summaries draw on three **descriptive / exploratory** evidence streams per `docs/ARCHITECTURE.md`:

1. **BH-corrected hypothesis tests** on direct AI-marker features (Pipeline A statistics)
2. **High-confidence change-points** in `ai_marker_frequency` and `formula_opening_score`, bucketed by era relative to public LLM releases (ChatGPT Nov 2022, GPT-4 Mar 2023, Gemini Dec 2023)
3. **AB-pass convergence windows** where Pipeline A (change-point) and Pipeline B (embedding drift) cross-corroborate

**Read [Caveats and Limitations](#caveats-and-limitations) before any external use.**

---

## Determinations Table

**Methodology caveat (R-05):** `mediaite-staff` and `mediaite` are **pooled editorial streams**, not single-human stylometry targets. Their ranking alongside named reporters is **for inventory only**; do not treat rank ordering as implying the same inferential unit as individual bylines.

**Exploratory criteria (R-08):** Letters **A–D** refer to [Determination criteria](#determination-criteria) below. For pooled bylines, A–D are **not** interpreted as a single-writer scorecard.

| Rank | Author | N articles | Exploratory verdict | Exploratory signal strength | A–D (individual slugs only) |
|---|---|---:|---|---|---|
| 1 | `mediaite-staff` | 719 | Exploratory pooled-byline signal | **Strong** — multiple BH-sig direct-marker and formula tests + high asymmetry | Pooled — see caveat |
| 2 | `isaac-schorr` | 3,346 | Exploratory signal | **Moderate** — 31 high-conf AI-marker increases, 29 post-Dec 2023 | B, D |
| 3 | `michael-luciano` | 6,274 | Exploratory signal | **Moderate** — 45 high-conf increases; BH-sig self-similarity; post-Dec 2023 cluster | B, D |
| 4 | `colby-hall` | 2,773 | Inconclusive lean-AI | **Moderate** with caveat — 4 BH-sig formula tests + extreme self-similarity; ~half of increases pre-ChatGPT | A, B†, C, D |
| 5 | `alex-griffing` | 6,290 | Weak / isolated signal | **Weak** — 1 BH-sig formula test (d=+2.12); 1 high-conf AI-marker increase vs 43 decreases | (below A–D bar as primary story) |
| 6 | `jennifer-bowers-bahney` | 2,766 | Possible experimental use | **Low** — 15 increases / 10 decreases post-Dec 2023; mixed direction | Partial B only |
| 7 | `charlie-nash` | 2,854 | No clear adoption | – | – |
| 8 | `david-gilmour` | 3,635 | No clear adoption | – | – |
| 9 | `ahmad-austin` | 2,973 | No clear adoption | – | – |
| 10 | `sarah-rumpf` | 2,707 | No clear adoption | balanced increases/decreases | – |
| 11 | `tommy-christopher` | 8,299 | Opposite pattern | clear de-formularization (4 inc / 71 dec) | – |
| 12 | `zachary-leeman` | 5,020 | Opposite pattern | 6 inc / 41 dec | – |
| 13 | `joe-depaolo` | 2,104 | No clear adoption | all increases pre-2022Q4 | – |
| 14 | `mediaite` (small byline) | 188 | Insufficient data | small sample (n=211 change-points total) | Pooled — see caveat |

†B counts post-ChatGPT high-confidence AI-marker increases vs decreases; `colby-hall` has a large pre-ChatGPT block of increases (see detailed section).

---

## Section coverage (untested confound) — J5

The newsroom-wide section profile (`section_profile_report.md`) returned **BORDERLINE** on the J5 gate (section separation weak vs threshold). With the default borderline policy, **section-residualized change-points were not applied** to these per-author narratives. Authors whose beats shift toward more formulaic sections can therefore show change-points driven partly by **section mix**, not necessarily by AI adoption.

---

## Methodology

The pipeline operates in four stages — scrape → extract → analyze → report — and the analysis stage produces ten artifacts per author. The findings here aggregate these artifacts:

- `*_changepoints.json` — BOCPD/PELT/Chow/CUSUM change-points with confidence and Cohen's d effect size
- `*_hypothesis_tests.json` — Mann-Whitney U / Welch / KS tests with **Benjamini-Hochberg-corrected** p-values
- `*_drift.json` — embedding centroid drift metrics (includes `ai_baseline_similarity` when baseline vectors exist)
- `*_convergence.json` — 800-window cross-feature convergence (Pipeline A × Pipeline B "AB-pass")
- `*_baseline_curve.json` — cosine similarity to first-20-articles baseline over time
- `*_bursts.json` — Kleinberg burst detection
- `*_timeseries.parquet` — per-feature time series (one row per article × feature)

**AI marker list version (R-07):** Tier-1 phrase counting for `ai_marker_frequency` uses `AI_MARKER_LIST_VERSION = "0.1.0"` from `src/forensics/features/lexical.py`. Any change to that list requires a version bump and traceability in feature metadata (see punch-list **N-04**).

### Feature families used as AI tells

Per `docs/ARCHITECTURE.md`:

- **Direct AI markers (Tier-1):** `ai_marker_frequency` (LLM-favored phrases), `formula_opening_score` (formulaic intros), `hedging_frequency`
- **Indirect Tier-2:** lexical richness (TTR/MATTR/hapax), readability (Flesch-Kincaid, Coleman-Liau, Gunning-Fog), n-gram entropy, self-similarity (TF-IDF), sentence structure, passive voice ratio

A "high-confidence change-point" is defined as `confidence ≥ 0.9` from the BOCPD detector. A "BH-significant test" uses corrected p-value < 0.05 after Benjamini-Hochberg correction across the full per-author battery.

### Determination criteria

An author is flagged for an **exploratory AI-adoption signal** if **at least two** of the following hold:

- A. ≥ 1 BH-corrected significant test on a direct AI marker (`ai_marker_frequency` or `formula_opening_score`)
- B. ≥ 5 high-confidence (≥0.9) AI-marker change-points in the **post-ChatGPT era** (after Nov 30, 2022), with **net positive direction** (increases > decreases)
- C. AB-pass convergence count > 50 (Pipeline A × Pipeline B cross-corroboration)
- D. Direct AI-marker increases > decreases by ratio ≥ 3:1 across the entire corpus

A weaker classification ("possible") applies when one of A–D holds with high effect size, or two hold with marginal scores.

---

## Per-Author Findings (Detailed)

### Tier 1 — Strongest exploratory signals (interpret with pooled-byline caveat)

#### 1. `mediaite-staff` (the unbylined "Mediaite Staff" byline, 719 articles)

**Verdict: EXPLORATORY SIGNAL — strong (pooled byline).**

| Criterion | Result |
|---|---|
| BH-sig direct AI tests | **6** (3× `ai_marker_frequency`, d=+0.56 to +0.79; 3× `formula_opening_score`, d=+0.63 to +1.58) |
| Post-ChatGPT high-conf AI-marker increases | 6 of 8 |
| Increase:decrease ratio | **8:1** |
| AB-pass convergence windows | 53 |
| Indirect / confounded signal | `bigram_entropy` d=+4.68 (BH p≈5e-15) — **supporting only** |

**R-06 / confound disclosure:** The large `bigram_entropy` shift is **not** treated as primary evidence of AI authorship. It is consistent with **mixed-authorship and section/beat pooling** under a shared byline. Primary weight in this row rests on direct-marker and formula tests plus temporal clustering, subject to the pooled-byline caveat above.

**Interpretation (exploratory):** The staff stream is the strongest stylometric outlier in this corpus, but that does not map cleanly to any single writer or workflow without independent reporting.

#### 2. `isaac-schorr` (3,346 articles)

**Verdict: EXPLORATORY SIGNAL — moderate.**

| Criterion | Result |
|---|---|
| BH-sig direct AI tests | 0 (but indirect tests strong) |
| High-conf AI-marker increases | **31** (only 9 decreases) |
| Post-Dec 2023 clustering | **29 of 31** increases are post-Dec 2023 |
| AB-pass convergence | 12 |
| Self-similarity 30d max d | -3.503 (BH p≈4e-10) |

**Why this is notable (exploratory):** Temporal clustering post–Dec 2023 is the cleanest timing narrative in the named-writer set. Cohen's d on individual increases remains small; there is no BH-significant direct AI-marker test.

#### 3. `michael-luciano` (6,274 articles)

**Verdict: EXPLORATORY SIGNAL — moderate.**

| Criterion | Result |
|---|---|
| BH-sig direct AI tests | 0 |
| High-conf AI-marker increases | **45** (the most of any author), 14 decreases |
| Post-Dec 2023 clustering | 23 of 45 |
| Pre-ChatGPT increases | 11 (muddies timing signal) |
| Self-similarity 30d | d=+0.785, BH p≈3e-15 (significant repetition) |

#### 4. `colby-hall` (2,773 articles) — **Inconclusive exploratory lean**

**Verdict: EXPLORATORY SIGNAL — moderate with major temporal caveat.**

| Criterion | Result |
|---|---|
| BH-sig direct AI tests | **4** (all `formula_opening_score`, d=+0.76 to +2.13) |
| High-conf AI-marker increases | 21 (vs **0 decreases** — perfectly asymmetric) |
| Pre-ChatGPT increases | **10 of 21** (caveat) |
| AB-pass convergence | **170 (most of any author)** |
| Self-similarity 30d | **d=+4.58** (BH p≈3e-17 — extreme repetition) |

`colby-hall` shows the strongest direct-AI BH-significant signature *among individual bylines in this table* and a one-directional change-point pattern, but **10 of 21** high-confidence increases predate ChatGPT, so a large fraction of the pattern may reflect long-standing formulaic style rather than model assistance.

### Tier 2 — Weaker / inconclusive signals

#### 5. `alex-griffing` — Weak

One BH-sig `formula_opening_score` test (d=+2.12, very large), but it's an isolated finding: 1 high-conf AI-marker increase against 43 decreases. The d=+2.12 detection could indicate one or a few specific articles with formulaic openings, not systematic adoption. 47 AB-pass windows.

#### 6. `jennifer-bowers-bahney` — Possible experimental use

15 high-conf increases / 10 decreases, all 25 events occurring post-Dec 2023. The bidirectional clustering in a narrow recent window suggests sporadic, inconsistent use — perhaps experimentation rather than systematic adoption. 51 AB-pass windows.

### No clear AI-adoption signal

`charlie-nash`, `david-gilmour`, `ahmad-austin`, `sarah-rumpf`, `joe-depaolo`, and the small `mediaite` byline either show balanced increase/decrease patterns, no BH-significant direct AI tests, or pre-ChatGPT-only increases.

### Opposite pattern (de-formularization)

- `tommy-christopher`: 4 high-conf AI-marker increases vs **71 decreases** — strong de-formularization trend, opposite of AI adoption.
- `zachary-leeman`: 6 increases vs 41 decreases — same pattern.

These two authors' style has *moved away* from AI-marker patterns over time. This may be a deliberate response to AI-content concerns, an editorial shift, or natural style evolution.

---

## Cross-corpus signals

From `data/analysis/comparison_report.json` (now populated for `colby-hall` vs configured controls), `corpus_custody.json`, and recent `run_metadata.json` entries:

- Corpus hash (custody record): `a2dd2579990b`, recorded 2026-04-24 20:12 UTC (unchanged from the narrative baseline run).
- **2026-04-26:** `forensics analyze --compare` regenerated `comparison_report.json` under a preregistered lock. A separate **exploratory** drift-only refresh (`run_id` `2ab7512e-bf2d-4f09-8a7b-51ef8e38bd29`, `exploratory: true`, `allow_pre_phase16_embeddings: true`) updated `*_drift.json` to populate `ai_baseline_similarity` using stub baseline vectors; it did **not** re-run change-point, convergence, or hypothesis-test stages. Per-author `*_result.json` and related Phase 7 artifacts therefore still reflect the **2026-04-24 parallel refresh cohort** (`full_analysis_authors` in the older `run_metadata` snapshot that lists twelve individual slugs), while drift metrics and comparison JSON reflect the newer operations above.
- The newsroom-wide section profile (`section_profile_report.md`) remains **BORDERLINE** on the J5 gate: multiple feature families distinguish sections statistically, but the maximum inter-section cosine distance is far below the 0.3 separation threshold. **Section-level residualization was not applied** to these per-author findings.

---

## Caveats and Limitations

These caveats materially affect how the table above should be read. They are not boilerplate.

1. **`ai_baseline_similarity` is populated but not yet model-backed.** After Phase 0, drift JSON may carry a numeric `ai_baseline_similarity` from **stub** vectors produced by `scripts/seed_phase0_ai_baseline_stubs.py` under `data/ai_baseline/.../embeddings/` (gitignored) so the metric is non-null for engineering continuity. **This is not** the intended Ollama / local LLM baseline matrix. Until `forensics analyze --ai-baseline` completes against a running Ollama server, do not treat that field as match to synthetic articles.

2. **Preregistration lock vs exploratory amendments.** `data/preregistration/preregistration_lock.json` is filed, but **Fix-F / Fix-G** in `amendment_phase15.md` are explicitly post-hoc for convergence scoring. Treat headline numerical results as **exploratory** until thresholds are either reverted or independently preregistered for a confirmatory pass.

3. **Section J5 gate is BORDERLINE.** Default policy leaves **section-residualized change-points disabled**. Section-mix shifts can masquerade as stylometric shifts.

4. **Multiple comparisons within author.** Each author has a large hypothesis battery. Even with BH correction, rely on converging lines of evidence, not single tests.

5. **Pre-ChatGPT change-points exist for several authors.** `ai_marker_frequency` is not a clean "AI vs. human" classifier.

6. **Observational design.** No causal identification.

7. **No ground-truth labels.** No admissions/denials fed into the pipeline.

---

## Recommended next steps

1. **Replace stub baseline with real generations:** start `ollama serve`, then `uv run forensics analyze --drift --ai-baseline --author <slug> ...` per `docs/RUNBOOK.md` so `ai_baseline_similarity` reflects actual synthetic articles.
2. **Re-run full analysis** (or parallel refresh) on a single `config_hash` cohort once embedding manifests align with `analysis.embedding_model_revision`, so change-points, drift, convergence, and comparisons all share one refresh timestamp.
3. **Section-residualized sensitivity** for flagged individual authors remains advisable given BORDERLINE J5.
4. **Spot-check** strongest change-points on `mediaite-staff` and `colby-hall` with human reading.
5. **Editorial workflow review** for `mediaite-staff` independent of stylometry.

---

## Files this report draws on

- `data/analysis/{author}_result.json` (×14)
- `data/analysis/{author}_changepoints.json` (×14)
- `data/analysis/{author}_hypothesis_tests.json` (×14)
- `data/analysis/{author}_drift.json` (×14) — **note 2026-04-26 stub-baseline drift refresh on some fields**
- `data/analysis/{author}_convergence.json` (×14)
- `data/analysis/{author}_baseline_curve.json` (×14)
- `data/analysis/{author}_bursts.json` (×14)
- `data/analysis/{author}_timeseries.parquet` (×14)
- `data/analysis/comparison_report.json` — **populated (target `colby-hall` vs controls) as of 2026-04-26**
- `data/analysis/section_profile_report.md`
- `data/analysis/corpus_custody.json`
- `data/analysis/run_metadata.json` (multiple runs exist; see Cross-corpus signals)
- `data/preregistration/preregistration_lock.json` and `data/preregistration/amendment_phase15.md`
- `docs/ARCHITECTURE.md` (Analysis Methods, Feature Families)
- `docs/GUARDRAILS.md` (Preregistration requirements)
