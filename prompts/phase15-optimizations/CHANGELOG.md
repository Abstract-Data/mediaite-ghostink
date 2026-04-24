# Changelog — Phase 15: Sensitivity, Signal Fidelity & Large-Author Performance

## [0.3.0] — 2026-04-24

**Model:** claude-opus-4-7
**Status:** active
**Bump reason:** MINOR — new Phase F0 (PELT kernel swap) added as the
single highest-leverage performance step; A4 promoted from optional to
required; J5 gate quantified; G1 status corrected to reflect that
PR #60 has landed. Backward-compatible across all Phase A–J content.

### Added

- **Phase F0 — PELT RBF → L2 kernel swap (1 step, 30 min):** profile
  evidence from isaac-schorr's run showed `costrbf.error` consumes
  **99.2% of analysis wall-clock** across 3M+ calls. BOCPD is 0.7%;
  bootstrap and all other phases combined are < 0.1%. One-line change
  from `model="rbf"` to `model="l2"` in `detect_pelt`, exposed as a
  `pelt_cost_model: Literal["l2", "l1", "rbf"] = "l2"` settings knob.
  Expected: 100–500× throughput on the PELT phase. Methodologically
  aligned with Phase C1's KS drop — the full analytical stack now
  focuses on mean/location shifts consistently.
- **Fast-path workflow:** documented five-step path (snapshot RBF CPs →
  land F0.1 → rerun 14 authors → diff pre/post → ship) that gets a
  complete dataset ahead of full Phase 15 rollout.
- **Reference-author snapshot diff** as the F0 validation artifact:
  before landing, snapshot one completed author's RBF CPs; after,
  diff CP count, mean-timestamp, and any qualitatively-relevant gains
  or losses. Pause if L2 loses > 20% of high-|d| RBF CPs.

### Updated

- **A4 (Student-t predictive) promoted** from optional to "ship directly
  after A2 lands." Rationale: A2's MAP-reset rule over a miscalibrated
  σ²-frozen predictive still limits BOCPD sensitivity. Student-t is
  the principled fix and we are already in the file.
- **G1 status corrected:** PR #60 has already merged per-author
  `ProcessPoolExecutor` parallelism to `main`. Phase 15's remaining
  G1 responsibility is the byte-identical-artifact parity test (H2)
  and documentation (I1, I2), not the implementation.
- **J5 gate quantified:** enable residualization iff
  (a) ≥ 3 feature families show section main effect MANOVA/K–W
  p < 0.01, AND (b) max off-diagonal inter-section cosine distance
  > 0.3. Previously "meaningful off-diagonal entries" — now an
  explicit two-part numeric gate recorded in `section_profile_report.md`.
- **Execution-order diagram** updated to place F0 ahead of everything
  as a fast-path, and to mark G1 as landed.
- **Effort table:** 36 steps / 24–34h → 37 steps / 22–32h (F0 added
  at 30min, G1 deducted as landed).
- **Finding → step mapping** adds a row for the 99.2%-RBF profile
  finding; G1 row flipped to "LANDED (PR #60)".
- **Definition of Done** adds two F0-specific gates: snapshot diff
  recorded in HANDOFF.md; 14-author rerun completes in ≤ 30 min.
- **Risk mitigation** adds an F0 entry covering the semantic shift
  (full-distribution → mean-shift), the 20%-high-|d|-loss tripwire,
  and the `pelt_cost_model` knob for A/B with RBF.

### Credits

- RBF-kernel profile and diagnosis: reviewer feedback on v0.2.0
  (Apr 24 2026). v0.1.0/v0.2.0's perf plan focused on bootstrap
  vectorization and parallelism, missing the 99.2%-dominant O(n²) RBF
  kernel. v0.3.0 corrects that.

## [0.2.0] — 2026-04-24

**Model:** claude-opus-4-7
**Status:** active
**Bump reason:** MINOR — new Phase J added (section-tag enrichment and
section-conditioned analysis). Backward-compatible: all Phase A–I steps
unchanged. Mission, execution order, effort table, finding → step
mapping, and Definition of Done updated to integrate the new phase.

### Added

- **Phase J — Section tags & conditioning (7 steps):** addresses the
  Apr 24 2026 article-tag audit which found the `metadata` JSON column
  is populated for only 11 of 77,862 articles (a consequence of
  `bulk_fetch_mode = true`), but the URL first-path-segment is a
  reliable section tag at 100% coverage (`media`, `politics`, `opinion`,
  `analysis`, `sponsored`, `partner-content`, `crosspost`, `columnists`,
  `premium`, `uk`, `crime`, `lawcrime`, `election-*`, `uncategorized`).
- **J1:** derive `section` column from URL at feature-extraction time;
  new `section_from_url` helper; SQLite view `articles_with_section`.
- **J2:** exclude `sponsored`, `partner-content`, `crosspost` from
  stylometric analysis by default; `--include-advertorial` CLI flag;
  `excluded_articles.csv` audit trail.
- **J3:** newsroom-wide section-level descriptive report — per-section
  centroids, inter-section cosine distance matrix, per-feature MANOVA /
  Kruskal–Wallis table, human-readable `section_profile_report.md`.
  Gates J5.
- **J4:** per-author section-mix-over-time chart wired into reporting —
  the single most important confound-check visual for the final
  narrative.
- **J5 (conditional on J3):** OLS residualization of stylometric
  features against one-hot section design matrix before PELT/BOCPD;
  emits both adjusted and unadjusted change-points; gated behind
  `section_residualize_features` config flag.
- **J6:** per-author pairwise Welch + Mann–Whitney section-contrast
  tests ("does this author's opinion register differ from their
  politics register?") with per-family BH correction.
- **J7:** CLI subcommands `forensics analyze section-profile` and
  `forensics analyze section-contrast [--author <slug>]`; new
  `--residualize-sections` flag on `analyze all`.

### Updated

- Mission statement extends from three goals to four (adds tag
  enrichment and section-conditioned analysis).
- Source review adds the Apr 24 article-tag audit.
- Baseline documents the `bulk_fetch_mode` metadata gap and the URL-
  section-tag inventory.
- Execution-order diagram slots Phase J between E and F (J5 must run
  before A's BOCPD if residualization is enabled).
- Effort table: 9 phases / 29 steps / 20–28 hours → 10 phases / 36
  steps / 24–34 hours.
- Finding → step mapping adds four new rows (tags/enrichment,
  differentiate-by-tag, section-mix confound, per-author × per-tag).
- Definition of Done adds five new gates: 100% section coverage,
  advertorial exclusion CSV, section_profile_report.md decision on J5,
  section-mix chart in every narrative, section-mix-only synthetic
  fixture passes residualizer test, at least one author with
  significant section contrasts OR documented finding that the outlet
  writes all sections identically.
- Risk mitigation expands to cover J2 (qualification-drop-out),
  J5 (degenerate one-section case), J6 (test count × BH honesty).

## [0.1.0] — 2026-04-24

**Model:** claude-opus-4-7
**Status:** active

### Added

- 9-phase (A–I) implementation plan covering the five findings from the
  Apr 24 2026 run-8 sensitivity review plus six performance targets for
  large-author analysis.
- **Phase A — BOCPD detection rule:** rewrite `detect_bocpd` to emit
  change-points on MAP run-length reset rather than thresholding
  `P(r_t = 0)`. The latter is algebraically pinned to the hazard rate
  under constant-hazard A&M and cannot fire regardless of σ² tuning or
  prior choice. Student-t predictive upgrade gated behind a flag.
- **Phase B — Feature families:** new `FEATURE_FAMILIES` registry groups
  the 23 stylometric features into ~8 independent axes. Convergence
  ratio computed over families, not raw features. Default
  `convergence_min_feature_ratio` drops 0.60 → 0.50. Analysis config-hash
  bumped to invalidate pre-Phase-15 artifacts.
- **Phase C — FDR density:** drop KS from the default test battery
  (correlated with Welch + MW); apply BH per feature-family rather than
  per-author globally to reclaim power without breaking independence
  assumptions.
- **Phase D — Shared bylines:** new frozen `is_shared_byline` field on
  `Author`. Heuristic combines outlet-prefix slug, shared-token slug,
  and multi-byline name patterns. Excluded by default from survey
  qualification; `--include-shared-bylines` CLI flag preserves
  auditability.
- **Phase E — Pipeline B:** DEBUG-level component logging in
  `_score_single_window`; loud warnings in `load_drift_summary` when
  drift artifacts are missing despite embeddings existing on disk;
  conditional signal recalibration (percentile-based `peak_signal`,
  baseline-scale-anchored `sim_signal`) only if diagnostics confirm a
  math-floor issue rather than an I/O failure.
- **Phase F — Easy perf wins:** vectorize `bootstrap_ci` (1 NumPy call
  replacing a 200-iter Python loop); cache per-feature series in
  `_run_hypothesis_tests_for_changepoints`; early-exit on constant signals
  in PELT/BOCPD.
- **Phase G — Parallelism:** `ProcessPoolExecutor`-backed per-author
  parallelism in `run_full_analysis` (each worker opens its own
  Repository; artifacts must be byte-identical to serial-mode baseline);
  optional `ThreadPoolExecutor` per-feature parallelism inside
  `analyze_author_feature_changepoints` (opt-in, default off); embedding
  I/O audit to confirm batch-`npz` vs legacy `.npy` layout on big-N
  authors.
- **Phase H — Tests:** reference-fixture regression tests for every
  signal change (BOCPD synthetic mean-shift, feature-family registry,
  per-family FDR, shared-byline heuristic); end-to-end parity test for
  serial-vs-parallel artifact equality; `fail_under` bump to 68+ (target
  70).
- **Phase I — Docs:** `ARCHITECTURE.md` updates (MAP-reset BOCPD, feature
  families, parallelism topology); `RUNBOOK.md` updates (new CLI flags,
  DEBUG-log commands); new GUARDRAILS Sign for constant-hazard BOCPD;
  HANDOFF block with before/after wall-clock on mediaite-staff (target
  ≥ 5× end-to-end improvement) and before/after counts of FDR-significant
  tests and surfaced convergence windows.
