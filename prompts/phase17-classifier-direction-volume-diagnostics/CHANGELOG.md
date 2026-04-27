# Changelog — phase17-classifier-direction-volume-diagnostics

All notable changes to this prompt family are documented here.
Entries are append-only per the prompt-library immutability contract.

## v0.1.0 — 2026-04-27

**Model:** claude-opus-4-7
**Status:** active
**Eval impact:** not yet measured (Phase 17 not yet executed)

Initial Phase 17 prompt covering three additive diagnostic surfaces on
top of the Apr 27 2026 post-Phase-15 classifier:

1. New `src/forensics/analysis/direction_priors.py` module codifying the
   `AI_TYPICAL_DIRECTION` mapping (16 features with documented priors,
   `hedging_frequency` explicitly None) and the `direction_from_d`
   helper.
2. New `DirectionConcordance` and `VolumeRampFlag` StrEnums plus
   `classify_direction_concordance` and `compute_volume_ramp_flag`
   library functions in `src/forensics/models/report.py`. Existing
   `FindingStrength` semantics unchanged.
3. New `direction`, `volume_flag`, `dir_match`, `dir_oppose`,
   `volume_ratio` columns in §11.3 of `notebooks/09_full_report.ipynb`,
   plus a new §11.3.1 markdown subsection explaining the diagnostic
   and a §11.4 recommendation to lock the new thresholds in
   pre-registration before any confirmatory run.

Motivation: the Apr 27 in-session review showed that the 8 MODERATE
authors in the post-Phase-15 §11.3 table all show stylometric shift in
the *opposite* direction from the AI-typical pattern, with corpus
volume ramps of 12×–276× between baseline and post window. The
classifier and report had no way to surface this distinction. Phase 17
adds the diagnostics; pre-registration is responsible for locking the
thresholds.

Out-of-scope items recorded in the prompt to prevent re-litigation:
pre-registration lock, changes to `FindingStrength` semantics,
filtering of authors based on the new diagnostics, Phase 9 / Phase 10
expansion, target-vs-control bias audit.

Definition-of-done captured in the prompt.
