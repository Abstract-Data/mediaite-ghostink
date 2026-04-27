# Pre-Registration Amendment — Phase 15

Version: 1.0
Date filed: 2026-04-24
Author(s): _maintainer sign-off pending_
Status: DRAFT — awaiting author-approval sign-off

## Context

Phase 15 rewrites several signal-detection rules and introduces a section-tag
dimension into the analysis pipeline. Every material change invalidates the
existing `data/preregistration/preregistration_lock.json` by design
(`compute_model_config_hash` re-hashes with the new enumerated fields). This
amendment lists the revised hypothesis space so the post-Phase-15 runs remain
confirmatory rather than exploratory.

## Amended Hypothesis Space

The confirmatory hypotheses below supersede any pre-existing hypotheses whose
detection rules have changed semantically in Phase 15. Exploratory analyses
(notebooks 00, 02, 05–07 drill-downs, section-profile diagnostics) remain
exploratory.

### H1 — Change-point surfacing under Phase-15 BOCPD (Phase A)

**Claim:** Under the MAP-run-length-reset detection rule with Student-t
predictive (`bocpd_detection_mode = "map_reset"`, `bocpd_student_t = true`)
the synthetic reference fixture `[0]*50 + [5]*50 + N(0, 1)` emits exactly one
change-point within ±3 timesteps of index 50.

**Test:** `tests/unit/test_bocpd_semantics.py::test_map_reset_detects_mean_shift`
(landed in Phase A).

**Decision rule:** Failure to detect is an implementation bug; >1 detection
or a detection ≥ ±3 steps from the true break is a calibration failure.

### H2 — Feature-family convergence threshold (Phase B)

**Claim:** With `convergence_min_feature_ratio = 0.50` interpreted against
the 6-family registry (`forensics.analysis.feature_families.FAMILY_COUNT`),
the four known-interesting reference windows listed in the plan
(david-gilmour 2025-12, jennifer-bowers-bahney 2026-03, isaac-schorr
2025-10, sarah-rumpf 2025-11) all clear the family-level ratio.

**Note (issue #5, 2026-04-24):** the registry was reduced from 8 → 6
families to remove the structural 6/8 = 0.75 ceiling that affected
89.8 % of windows in the post-Phase-15 full-analysis run. Two
single-member families (`voice` and `paragraph_shape`) were folded into
the related multi-member families `ai_markers` and `sentence_structure`
respectively. The threshold (0.50) is unchanged, but the denominator
moved from 8 → 6, so the new requirement is "≥ 3 of 6 families" instead
of "≥ 4 of 8 families".

**Test:** `tests/unit/test_convergence.py::test_reference_windows_pass_family_threshold`
(landed in Phase B).

### H3 — Per-family BH correction (Phase C)

**Claim:** Applying BH per feature family yields strictly more significant
tests than per-author BH on a synthetic fixture with correlated-feature
structure. Across the 10 corpus authors, at least five authors have ≥ 1
FDR-significant test under per-family BH.

**Test:** `tests/unit/test_per_family_fdr.py` (landed in Phase C).

### H4 — Shared-byline qualification gate (Phase D)

**Claim:** With `survey.exclude_shared_bylines = true` both `mediaite-staff`
and `mediaite` appear in the `disqualified` list with reason
`shared_byline (<matched-rule>)`. At least one currently-qualifying author
slug continues to qualify (shared-byline filter is not over-broad).

**Test:** `tests/unit/test_shared_byline.py::test_shared_byline_excludes_outlet_prefixed_slugs`
(landed in Phase D).

### H5 — Section-tag coverage (Phase J1)

**Claim:** After the Phase J1 feature-parquet migration, 100 % of rows in
every per-author feature parquet have a non-empty, lowercase `section` value
derived from the URL path. The ~400 advertorial/syndicated rows are listed
in `data/survey/excluded_articles.csv`.

**Test:** `tests/unit/test_section_extraction.py::test_section_coverage_is_total`
(landed in Phase J1).

### H6 — Section-conditioned drift is distinct from stylistic drift (Phase J5, conditional)

**Claim:** A synthetic signal with zero stylistic drift but a section-mix
shift mid-series emits a change-point under the unadjusted pipeline and no
change-point under the section-adjusted pipeline
(`convergence_cp_source = "section_adjusted"`, `section_residualize_features
= true`).

**Test:** `tests/unit/test_section_residualize.py::test_section_adjusted_removes_mix_confound`
(landed in Phase J5 only if the J3 diagnostic gate passes).

### H7 — Parallelism byte-identity (Phase G)

**Claim:** `run_full_analysis` with `max_workers = 1` and
`max_workers = os.cpu_count()` produces byte-identical per-author JSON
artifacts on a 3-author fixture corpus.

**Test:** `tests/integration/test_parallel_parity.py` (landed in Phase H2).

## Non-Registered Analyses

- The section-profile newsroom-wide descriptive (J3) is exploratory — its
  output feeds the J5 gate decision but is itself published as a descriptive
  report, not a hypothesis test.
- Per-author × per-section contrast tests (J6) are descriptive evidence to
  annotate author narratives; decision rules stay exploratory so the author
  can report contrast magnitudes without an FDR budget.

## Config-Hash Boundary

Every pre-Phase-15 `config_hash` is treated as incompatible with every
post-Phase-15 `config_hash` by construction (see
`src/forensics/utils/provenance.py::compute_model_config_hash` and the
newly enumerated fields). Analysts MUST NOT pool cached artifacts across
the boundary; see `docs/GUARDRAILS.md` (Phase-15 Sign: "Do not mix pre-
and post-Phase-15 artifacts in one analysis run").

## Author-Approval Sign-Off

The confirmatory claims above are frozen once the sign-off block is
completed. Any subsequent edit to H1–H7 requires a new amendment file
(increment the filename suffix and reference the superseded entry).

- Maintainer name: _____________________________
- GitHub handle:    _____________________________
- Signed (ISO-8601): _____________________________
- SHA of Phase-15 Unit 1 PR: _____________________________

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
