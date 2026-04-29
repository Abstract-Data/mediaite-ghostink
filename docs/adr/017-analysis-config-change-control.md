# ADR-017: AnalysisConfig field growth and compat module ownership

## Status

Accepted — 2026-04-27

## Context

`AnalysisConfig` and nested sub-models feed preregistration, `config_hash` on
analysis artifacts, and `compute_model_config_hash` / nested hash walks
(ADR-016). Ad-hoc leaf fields risk silent hash drift, duplicated flat-key
routing, and unclear review ownership.

## Decision

1. **Change control:** New **top-level** leaves on `AnalysisConfig`, new nested
   fields on any sub-model that participate in provenance hashing, or any change
   to flat TOML key routing / `_GROUP_ATTRS` membership requires an **ADR update**
   (this document or ADR-016) before merge, plus golden updates in
   `tests/unit/test_config_hash.py` when the digest is intended to move.

2. **Compat ownership:** Legacy flat `[analysis]` lifting and
   `_FLAT_TO_GROUP` / `_GROUP_ATTRS` live in `src/forensics/config/compat_analysis.py`.
   `analysis_settings.py` imports from compat; provenance continues to use
   `AnalysisConfig` from `analysis_settings`.

3. **No `HashableField` annotation for now:** A custom Pydantic annotation was
   evaluated and deferred: it could interact unexpectedly with `model_dump` and
   the recursive hash payload builder. Governance above plus compat isolation
   satisfy maintainability without risking hash stability (correctness over
   convenience).

## Consequences

- **Deprecation (2026-04-29):** loading `config.toml` with legacy flat `[analysis]`
  keys (lifted via `_lift_flat_analysis_dict`) emits a **one-time per process**
  `WARNING` directing operators toward nested tables such as `[analysis.pelt]`.
  Removal of the lift path is gated on a future release after the warning window.
- Flat-key table edits happen in one module; reviewers watch compat + hash tests.
- Optional fields like `ContentLdaConfig` knobs remain grouped there; moving
  fields across sub-models remains a **hash-visible** change needing ADR-016
   alignment.

## References

- ADR-016 (`016-analysis-config-nesting.md`)
- `src/forensics/config/compat_analysis.py`
- `src/forensics/config/analysis_settings.py`
- `src/forensics/utils/provenance.py`
