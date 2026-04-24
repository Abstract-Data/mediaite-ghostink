# Phase 15 Settings Audit

Every knob introduced or repurposed by Phase 15. Ordered by owning phase;
each row also records whether the field participates in the analysis
config-hash (and therefore invalidates cached artifacts when flipped).

The authoritative list of hash-participating fields lives on
``AnalysisConfig`` / ``FeaturesConfig`` in
``src/forensics/config/settings.py`` — the fields decorated with
``json_schema_extra={"include_in_config_hash": True}``. The unit test
``tests/unit/test_config_hash.py`` pins both directions of the
inclusion/exclusion boundary.

## Analysis + Features

| Knob | Phase | Default | In hash? | Rationale / rollback |
|---|---|---|---|---|
| `analysis.pelt_cost_model` | F0 | `"l2"` | yes | O(n) mean-shift cost replaces O(n²) RBF kernel. Rollback: set `"rbf"` for comparison runs. |
| `analysis.bocpd_detection_mode` | A | `"map_reset"` | yes | Legacy `p_r0_legacy` thresholded a quantity that is algebraically pinned to the hazard rate. Rollback: `"p_r0_legacy"` (A/B only). |
| `analysis.bocpd_map_drop_ratio` | A | `0.5` | yes | MAP-run-length drop fraction that triggers a change-point. Lowering increases sensitivity. |
| `analysis.bocpd_min_run_length` | A | `5` | yes | Ignore warm-up resets below this run length. |
| `analysis.bocpd_reset_cooldown` | A | `3` | no | Post-detection cooldown in timesteps. Tuning this knob does not change detection *semantics*, only the emitted stream density. |
| `analysis.bocpd_merge_window` | A | `2` | no | Merge window for adjacent MAP-resets. Same rationale as cooldown. |
| `analysis.bocpd_student_t` | A4 | `true` | yes | Student-t posterior predictive via Normal-Inverse-Gamma conjugate (Murphy 2007 §7.6). Rollback: `false` reverts to fixed-σ² Normal predictive. |
| `analysis.convergence_min_feature_ratio` | B3 | `0.50` | yes | Reinterpreted against the 8-family registry; drop from `0.60` (23 raw features) to `0.50` (4-of-8 independent axes). |
| `analysis.convergence_cp_source` | J5 | `"section_adjusted"` | yes | Which CP list feeds convergence. `"raw"` reverts to pooled-section CPs. |
| `analysis.fdr_grouping` | C | `"family"` | yes | Apply BH per feature family rather than per author. `"author"` reverts to pre-Phase-15. |
| `analysis.pipeline_b_mode` | E | `"legacy"` | yes | Pipeline B scoring. `"percentile"` becomes default only if E1 confirms a math-floor; until then `"legacy"` preserves v0.14 output. |
| `analysis.section_residualize_features` | J5 | `false` | yes | OLS residualization against one-hot sections before CPD. Gated behind the J3 diagnostic. |
| `analysis.section_min_articles` | J | `50` | no | Minimum article count for section-level descriptive. Threshold only. |
| `analysis.min_articles_per_section_for_residualize` | J5 | `10` | no | Degenerate-OLS guard. Threshold only. |
| `analysis.max_workers` | G | `null` (→ `os.cpu_count()-1`) | no | Wall-clock only; does not change outputs. |
| `analysis.feature_workers` | G | `1` | no | Wall-clock only. |
| `features.feature_parquet_schema_version` | 0.3 | `2` | yes | Readers refuse older parquets; run `forensics features migrate` to upgrade. |

## Survey

| Knob | Phase | Default | In hash? | Rationale |
|---|---|---|---|---|
| `survey.exclude_shared_bylines` | D | `true` | no | Survey-stage qualification gate. Does not affect analysis-stage config hash. Override via CLI: `--include-shared-bylines`. |
| `survey.excluded_sections` | J2 | `{"sponsored", "partner-content", "crosspost"}` | no | Advertorial / syndicated sections omitted from stylometry. Override via CLI: `--include-advertorial`. |

## Fields that DO participate in the hash (authoritative list)

From ``AnalysisConfig``:

- `pelt_cost_model`
- `bocpd_detection_mode`
- `bocpd_map_drop_ratio`
- `bocpd_min_run_length`
- `bocpd_student_t`
- `convergence_min_feature_ratio`
- `convergence_cp_source`
- `fdr_grouping`
- `pipeline_b_mode`
- `section_residualize_features`
- `changepoint_methods`
- `bootstrap_iterations`
- `significance_threshold`
- `effect_size_threshold`
- `multiple_comparison_method`

From ``FeaturesConfig``:

- `feature_parquet_schema_version`

Any new signal-bearing knob must be added here AND to
``tests/unit/test_config_hash.py`` AND decorated with
``json_schema_extra={"include_in_config_hash": True}``. The hash test is
the hard gate — it will fail if the three places drift.

## Rollback Matrix

Flipping any hash-included knob invalidates every on-disk artifact
produced with the previous value. The rollback procedure is:

1. Revert the `config.toml` knob to the previous default.
2. Delete `data/analysis/*.json` (or move them aside under a
   `_pre_phase15/` subdirectory) so the next `forensics analyze` run
   re-computes.
3. Re-run `forensics analyze` (or `forensics all`) to regenerate.

Flipping any non-hash knob (threshold / workers / cooldown) is safe — the
cache is still valid.

## Related references

- `config.toml` — inline per-knob phase-ownership comments.
- `docs/ARCHITECTURE.md` §Analysis Methods — semantic reference for each
  detection rule.
- `docs/GUARDRAILS.md` Agent-Learned Signs — the Phase-15 BOCPD ``P(r=0)``
  Sign, the `metadata`-column-empty Sign, and the pre/post-Phase-15
  artifact-mixing Sign.
- `data/preregistration/amendment_phase15.md` — the confirmatory
  hypothesis list that references these knobs.
