# ADR-016: Nested `AnalysisConfig` with flat TOML and stable analysis hash

## Status

Accepted — 2026-04-27

## Context

`AnalysisConfig` had grown into a large flat `BaseModel` (~40+ fields), mixing
changepoint, BOCPD, convergence, LDA, hypothesis-testing, and embedding knobs.
Operators and `config.toml` already use a **flat** `[analysis]` table.

Preregistration locks, `data/analysis/*_result.json` `config_hash`, and
`compute_model_config_hash(settings.analysis)` must stay **bit-for-bit stable**
for the same effective settings unless we intentionally version and document
a bump.

## Decision

1. **Decompose** `AnalysisConfig` into nested Pydantic sub-models:
   `PeltConfig`, `BocpdConfig`, `ConvergenceConfig`, `ContentLdaConfig`,
   `HypothesisConfig`, `EmbeddingStackConfig`, plus top-level operational
   fields (`rolling_windows`, `max_workers`, etc.).

2. **Flat TOML compatibility**: `AnalysisConfig` uses
   `model_validator(mode="before")` (`_lift_flat_analysis_dict`) to move legacy
   flat `[analysis]` keys into the appropriate sub-dict before validation, so
   existing `config.toml` files load unchanged.

3. **Stable analysis hash**: `compute_model_config_hash` special-cases
   `AnalysisConfig`: it walks nested models and builds the **same flat JSON
   object** (leaf keys identical to the pre-refactor field names) before
   `json.dumps(..., sort_keys=True)`. Preregistration snapshot keys are updated
   to read through the nested attributes but emit the **same** JSON keys as
   before.

4. **Environment variables**: nested settings use the usual
   `FORENSICS_<SECTION>__<SUB>__<FIELD>` pattern, e.g.
   `FORENSICS_ANALYSIS__CONVERGENCE__CONVERGENCE_USE_PERMUTATION` instead of the
   former flat `FORENSICS_ANALYSIS__CONVERGENCE_USE_PERMUTATION`.

5. **Tests**: `tests/unit/test_config_hash.py` pins the leaf hash field set via
   `analysis_config_hash_field_names()` and a **golden** 16-char hash for
   default `AnalysisConfig()`.

## Consequences

- Call sites use explicit paths (`settings.analysis.hypothesis.significance_threshold`).
- `apply_flat_analysis_overrides` supports tests and one-off scripts that still
  think in flat field names.
- Operators migrating env overrides must add the sub-model segment in the key.

## References

- `src/forensics/config/analysis_settings.py`
- `src/forensics/utils/provenance.py` (`_build_recursive_hash_payload`,
  `analysis_config_hash_field_names`)
- `tests/unit/test_config_hash.py` (`test_default_analysis_config_model_hash_golden`)
