# Phase 17: Classifier Direction Concordance & Volume-Ramp Diagnostics

Version: 0.1.0
Status: active
Last Updated: 2026-04-27
Model: claude-opus-4-7

---

## Mission

Surface — both in the classifier and in the rendered report — the
distinction between "stylometric shift in the AI-typical direction" and
"stylometric shift caused by corpus-volume ramp / beat change / editor
swap." The Apr 27 2026 post-Phase-15 review showed that the §11.3 finding
ladder, even after window-feature scoping and the tightened MODERATE bar,
still buckets together author-windows whose underlying signal pattern is
qualitatively different.

Specifically:

- **The single STRONG author** (`colby-hall`, window 2026-03-17 →
  2026-06-15) has a signal pattern that points in the AI-typical
  direction on every measured feature (`self_similarity_30d` d=+4.66,
  `formula_opening_score` d=+0.89), with stable-or-declining article
  volume (n_post / n_pre = 0.44×) inside the LLM-availability era.
- **All eight MODERATE authors** have signal patterns that overwhelmingly
  point in the *opposite* direction from the AI-typical pattern (12 of
  13 directional features oppose the prior), with corpus-volume ramps
  ranging from 12× to 276× between baseline and post window, and
  windows clustered in 2021–2023 (largely pre-LLM-era for journalism).

The classifier currently has no way to distinguish these two regimes; it
treats "feature changed by ≥3 sig tests with ≥1 strong test" as
equivalent regardless of direction or volume context. The report has no
column or visual that exposes the distinction either. As a result, a
casual reader of §11.3 sees "1 STRONG, 8 MODERATE" and may infer "8
reporters showing some AI signal" when the honest reading is "8
reporters showing a corpus-expansion artifact in the wrong direction
to be AI-driven."

This phase adds three artifacts (one library module, one classifier
extension, one report column + section) so the distinction is visible to
the classifier and to the reader, *without* changing the existing
STRONG/MODERATE/WEAK semantics in a backward-incompatible way. The
direction concordance is exposed as a separate ordered tier
("DIRECTION_AI", "DIRECTION_MIXED", "DIRECTION_NON_AI", "DIRECTION_NA")
and a volume-ramp flag is exposed as a separate boolean. Both feed the
report; neither overwrites `FindingStrength`.

**Baseline (pre-Phase-17):**

- `classify_finding_strength` reads only `len(significant_tests)` and
  `len(strong_tests)` — no direction information, no volume context.
  The classifier cannot distinguish a +d=4.66 self-similarity shift from
  a −d=3.34 self-similarity shift; both count identically.
- The §11.3 table in `notebooks/09_full_report.ipynb` shows
  `pa, pb, window_start, window_end, n_families, n_sig` for each
  author. There is no column for direction concordance, no column for
  pre/post volume ratio, and no column for the era of the window.
- `data/analysis/{slug}_result.json` contains, per
  `hypothesis_tests` entry, signed `effect_size_cohens_d` plus
  `n_pre`/`n_post`. The information is on disk; nothing reads it for
  the report.
- AI-direction priors for each feature are not codified anywhere in the
  codebase. The Apr 27 conversation enumerated them inline; the
  registry needs to be promoted to a module.

**Scope:**

1. New module `src/forensics/analysis/direction_priors.py` with the
   `AI_TYPICAL_DIRECTION` mapping and helper utilities.
2. New library function `classify_direction_concordance` in
   `src/forensics/models/report.py` that returns a `DirectionConcordance`
   StrEnum (parallel to `FindingStrength`, not a replacement).
3. New library function `compute_volume_ramp_flag` in the same module
   returning a `VolumeRampFlag` StrEnum.
4. Extend the §11.3 table in `notebooks/09_full_report.ipynb` to add
   four new columns: `dir_match`, `dir_oppose`, `dir_concordance`,
   `volume_ratio`, `volume_flag`. Sort key changes to put STRONG first,
   then MODERATE sorted by direction concordance, then volume flag.
5. New §11.3.1 markdown subsection in the same notebook explaining the
   direction-and-volume diagnostic, including a per-author breakdown
   table for the 8 MODERATE authors so the reader can see the
   confounds explicitly.
6. Unit tests for the three new public symbols (`AI_TYPICAL_DIRECTION`
   coverage, `classify_direction_concordance` boundary cases,
   `compute_volume_ramp_flag` boundary cases). Existing
   `classify_finding_strength` tests stay green (function is unchanged).
7. HANDOFF.md block, RUNBOOK.md update with new diagnostic columns,
   GUARDRAILS.md sign if any new failure pattern is hit.

**Out of scope:**

- Changing the existing STRONG/MODERATE/WEAK semantics. The new
  diagnostics are additive.
- Pre-registration lock. The choice of direction priors and volume-ramp
  threshold should be ratified (or revised) in pre-registration before
  any confirmatory run, not in this phase.
- Automatic re-rendering of the PDF. The notebook patches land here;
  re-render is a separate operator action documented in RUNBOOK.

---

## Source Review

- Apr 27 2026 inline forensics review (this conversation):
  per-author direction-of-effect table for the 8 MODERATE authors plus
  Colby Hall, showing 0/1, 0/2, 0/3, 1/2 AI-direction concordance for
  controls vs. 2/2 for Colby Hall, with volume-ramp ratios of 12× to
  276× for the controls vs. 0.44× for Colby Hall.
- `src/forensics/models/report.py` (Phase 17 baseline state, post-Apr 27
  patch): `classify_finding_strength` now uses
  `≥3 sig AND ≥1 strong` for MODERATE, with window-scoped
  `hypothesis_tests` recommended in the docstring. No direction
  awareness.
- `notebooks/09_full_report.ipynb` cell `cell-strength-code` (Phase 17
  baseline): per-author loop already does window-feature scoping and
  per-target editorial_vs_author_signal lookup. Adding the direction
  and volume columns is a strict extension.
- `data/analysis/colby-hall_result.json`,
  `data/analysis/{ahmad-austin, charlie-nash, isaac-schorr,
  jennifer-bowers-bahney, joe-depaolo, sarah-rumpf, tommy-christopher,
  zachary-leeman}_result.json`: ground-truth fixtures exercising the
  full direction/volume signal range for unit tests.
- Supersedes: nothing. Builds on the Apr 27 in-session patches to
  `models/report.py` (MODERATE bar tighten + docstring rewrite) and
  `notebooks/09_full_report.ipynb` (per-target eva lookup +
  window-feature scoping).

---

## Guiding Principles

1. **Additive, not replacement.** Existing `FindingStrength` semantics
   stay. New diagnostics live in parallel enums + columns. A reader
   should be able to read just the strength tier (legacy interpretation)
   or strength + direction + volume (Phase 17 interpretation) and
   neither view should be misleading.
2. **Direction priors are auditable.** The `AI_TYPICAL_DIRECTION`
   mapping must live in code, not in a markdown cell, so it has a git
   history and a single source of truth. Any feature with no documented
   AI-typical direction is `None` and the concordance check skips it
   (counts as "no prior" in the breakdown, not as a match or oppose).
3. **Pre-registration discipline.** This phase introduces *exploratory*
   diagnostic columns. The exact thresholds (e.g. "volume ramp >5× is
   suspicious", "direction concordance ≥50% supports AI reading") must
   be flagged as exploratory in the report and locked in
   `data/preregistration/preregistration_lock.json` before any
   confirmatory run. The notebook markdown must say so explicitly.
4. **TDD for the new library symbols.** Each of the three new public
   functions lands with tests before the notebook reads from it.
5. **Respect stage boundaries.** This is a report-stage / models-stage
   change only. No edits to `src/forensics/scraper/`,
   `src/forensics/features/`, or `src/forensics/analysis/` pipeline
   modules. The new `direction_priors.py` is a pure-data module with
   no runtime dependency on any pipeline stage.
6. **Use `uv run` for every Python command.** Never bare `python` or
   `pip`.
7. **Update HANDOFF.md** at the end of the phase. Include the
   verification commands run and a one-paragraph summary noting the
   exploratory status of the new thresholds.
8. **Follow GUARDRAILS Signs.** Check `docs/GUARDRAILS.md` before
   modifying any file. If a new footgun is discovered (likely candidate:
   "n_pre or n_post can be None for skipped/degenerate tests; volume
   ratio computation must guard against division by zero"), append a
   Sign.

---

## Implementation Plan

### Phase A: AI-Direction Priors Registry (library, 1 hour)

The mapping of "which direction of feature shift is AI-typical" needs
a single source of truth in code, not scattered across docstrings or
notebook markdown.

#### Step A1: Create the priors module
**Risk:** LOW
**Files:** `src/forensics/analysis/direction_priors.py` (new)
**What:** Define `AI_TYPICAL_DIRECTION: dict[str, Literal["increase", "decrease"]]`
mapping each known stylometric feature to its AI-typical change
direction. Initial mapping (audit before commit):

```python
"""Empirical AI-direction priors for stylometric features.

Each entry records the direction in which a feature shift is
*consistent with* known LLM stylistic biases. Sources:
- Phase 9 perplexity literature (lower PPL = more LLM-typical).
- Phase 7 convergence design notes.
- The GPTZero / OriginalityAI / Binoculars feature-priority dossiers.
- Internal Apr 27 2026 review of LLM output corpora.

A `None` value means "we have no documented prior" — concordance
checks skip these features. This is intentional: we never want to
fabricate a direction for a feature without evidence.

This file should be reviewed before pre-registration lock; any
threshold or directional claim derived from it is exploratory until
the lock exists.
"""
from __future__ import annotations

from typing import Literal

Direction = Literal["increase", "decrease"]

AI_TYPICAL_DIRECTION: dict[str, Direction | None] = {
    # AI marker phrases ("delve", "in conclusion", "it's important to note")
    "ai_marker_frequency": "increase",
    "formula_opening_score": "increase",
    # Readability / formality (LLMs trend toward formal, complex prose)
    "coleman_liau": "increase",
    "gunning_fog": "increase",
    "flesch_kincaid": "increase",
    # Lexical diversity (LLMs use more common phrasing)
    "bigram_entropy": "decrease",
    "trigram_entropy": "decrease",
    "ttr": "decrease",
    "lexical_diversity": "decrease",
    # Sentence-length variation (LLMs more uniform)
    "sent_length_std": "decrease",
    "sent_length_skewness": "decrease",
    "sent_length_mean": "increase",
    # Self-similarity (LLM-assisted corpora are more internally repetitive)
    "self_similarity_30d": "increase",
    "self_similarity_90d": "increase",
    # Function-word / connector frequency
    "conjunction_freq": "increase",
    "hedging_frequency": None,  # mixed evidence — leave undocumented
}


def direction_from_d(cohens_d: float | None) -> Direction | None:
    """Map a signed Cohen's d to 'increase' / 'decrease' / None."""
    if cohens_d is None:
        return None
    try:
        if not (cohens_d == cohens_d):  # NaN check
            return None
    except TypeError:
        return None
    if cohens_d > 0:
        return "increase"
    if cohens_d < 0:
        return "decrease"
    return None
```

**Validation:**
```bash
uv run python -c "from forensics.analysis.direction_priors import AI_TYPICAL_DIRECTION, direction_from_d; print(len(AI_TYPICAL_DIRECTION)); print(direction_from_d(1.0))"
```

#### Step A2: Unit tests for the priors module
**Risk:** LOW
**Files:** `tests/unit/test_direction_priors.py` (new)
**What:** Test (a) every key in `AI_TYPICAL_DIRECTION` is a known
feature column or explicitly justified, (b) `direction_from_d`
handles None, NaN, positive, negative, and zero correctly,
(c) keys form a subset of (or superset of) the known feature list
in `src/forensics/features/`. The "audit-against-feature-list" test
locks in the contract that adding a new feature requires either
adding a prior or explicitly marking it `None`.
**Validation:** `uv run pytest tests/unit/test_direction_priors.py -v`

---

### Phase B: Direction Concordance & Volume Ramp Library Functions (library, 2 hours)

#### Step B1: DirectionConcordance enum + `classify_direction_concordance`
**Risk:** LOW
**Files:** `src/forensics/models/report.py` (extend)
**What:** Add a new `DirectionConcordance` StrEnum and a function
that takes a `ConvergenceWindow`, the window-scoped
`HypothesisTest` list, and returns a `DirectionConcordance` plus a
breakdown dict. Proposed shape:

```python
class DirectionConcordance(StrEnum):
    AI = "direction_ai"          # >=50% of features with priors match AI-typical
    MIXED = "direction_mixed"    # >0% but <50% match
    NON_AI = "direction_non_ai"  # 0% match (and >=1 feature has a prior)
    NA = "direction_na"          # 0 features have priors


@dataclass(frozen=True)
class DirectionBreakdown:
    n_match: int
    n_oppose: int
    n_no_prior: int
    matched_features: tuple[str, ...]
    opposed_features: tuple[str, ...]


def classify_direction_concordance(
    convergence_window: ConvergenceWindow,
    window_hypothesis_tests: list[HypothesisTest],
) -> tuple[DirectionConcordance, DirectionBreakdown]:
    """Score how many of the window's features moved in the AI-typical
    direction. Callers MUST pre-scope the test list to the window's
    features_converging (same convention as classify_finding_strength).
    """
    ...
```

The match logic: for each unique `feature_name` in the test list,
pick the strongest test (largest |d|) for that feature, derive the
direction from its sign, look up the AI prior. If the prior is
`None`, count as `n_no_prior`. Otherwise count as match or oppose.

Threshold rationale (must be documented as exploratory in the
docstring): the 50% match cutoff for AI vs. MIXED reflects the
intuition that if at least half of the priors-having features point
the AI direction, the *pattern* is AI-consistent. This threshold
must be locked in pre-registration before any confirmatory run.

**Validation:** `uv run pytest tests/unit/test_direction_concordance.py -v`

#### Step B2: VolumeRampFlag enum + `compute_volume_ramp_flag`
**Risk:** LOW
**Files:** `src/forensics/models/report.py` (extend)
**What:** Add the volume-ramp diagnostic. Hypothesis tests carry
`n_pre` and `n_post` (the same value across all tests for a given
author/window pair). Compute `volume_ratio = n_post / n_pre` and
classify:

```python
class VolumeRampFlag(StrEnum):
    STABLE = "volume_stable"        # ratio in [0.5, 2.0]
    GROWTH = "volume_growth"        # ratio in (2.0, 5.0]
    RAMP = "volume_ramp"            # ratio > 5.0  (likely confound)
    DECLINE = "volume_decline"      # ratio < 0.5
    UNKNOWN = "volume_unknown"      # n_pre or n_post missing/zero


def compute_volume_ramp_flag(
    window_hypothesis_tests: list[HypothesisTest],
) -> tuple[VolumeRampFlag, float | None]:
    """Return (flag, volume_ratio_or_None).

    Reads n_pre / n_post from the first non-degenerate test in the list.
    n_post / n_pre > 5 is the threshold above which a corpus-expansion
    confound becomes the more parsimonious explanation for any detected
    stylometric shift. This threshold is exploratory; lock in
    pre-registration before any confirmatory run.
    """
    ...
```

Edge cases the unit tests must cover:
- `n_pre = 0` → UNKNOWN (avoid div-by-zero)
- `n_pre = None` → UNKNOWN
- All tests `degenerate=True` → UNKNOWN (no usable n_pre/n_post)
- Mix of `n_pre` values across tests → use first non-None,
  non-zero pair (warn in docstring; pipeline currently emits
  consistent values per author/window)

**Validation:** `uv run pytest tests/unit/test_volume_ramp_flag.py -v`

#### Step B3: Re-export from `forensics.models`
**Risk:** LOW
**Files:** `src/forensics/models/__init__.py`
**What:** Add `DirectionConcordance`, `DirectionBreakdown`,
`VolumeRampFlag`, `classify_direction_concordance`,
`compute_volume_ramp_flag` to the `__all__` and re-export.
**Validation:** `uv run python -c "from forensics.models import DirectionConcordance, VolumeRampFlag; print(list(DirectionConcordance), list(VolumeRampFlag))"`

---

### Phase C: Notebook §11.3 Extension (report, 1.5 hours)

#### Step C1: Patch `cell-strength-code` to compute and display the new columns
**Risk:** MEDIUM (notebook JSON edits — use the same Python-script
round-trip pattern used in the Apr 27 patches; do not edit the
.ipynb with a text editor)
**Files:** `notebooks/09_full_report.ipynb` (cell `cell-strength-code`)
**What:** After the existing `classify_finding_strength` call, add:

```python
from forensics.models.report import (
    classify_direction_concordance,
    compute_volume_ramp_flag,
)

direction, breakdown = classify_direction_concordance(best, window_tests)
volume_flag, volume_ratio = compute_volume_ramp_flag(window_tests)
```

Append to each row:
```python
"direction": str(direction),
"dir_match": breakdown.n_match,
"dir_oppose": breakdown.n_oppose,
"dir_no_prior": breakdown.n_no_prior,
"volume_flag": str(volume_flag),
"volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
```

Update the `display(strength_df)` sort and column selection to show:
`slug, strength, direction, volume_flag, pa, pb, window_start, window_end, n_families, dir_match, dir_oppose, n_sig, volume_ratio`.

Sort key: `(strength_rank, direction_rank, volume_flag_rank, -pb)` so
STRONG / DIRECTION_AI / VOLUME_STABLE rows surface first.

**Validation:** Re-render notebook locally:
```bash
uv run jupyter nbconvert --to notebook --execute \
    notebooks/09_full_report.ipynb \
    --output /tmp/09_full_report_check.ipynb
```
Inspect the rendered table to confirm Colby Hall is sorted first
with `direction=direction_ai, volume_flag=volume_decline` and the
8 ex-MODERATE authors show `direction=direction_non_ai`,
`volume_flag=volume_ramp`.

#### Step C2: Add a §11.3.1 markdown subsection
**Risk:** LOW
**Files:** `notebooks/09_full_report.ipynb` (new markdown cell after
`cell-strength-md`, id `cell-direction-md`)
**What:** A short narrative explaining what `direction` and
`volume_flag` mean and why they matter for interpreting MODERATE
findings. Include the per-author breakdown that emerged from the
Apr 27 review (Colby Hall: 2/2 AI-direction match, volume 0.44×;
8 MODERATE authors: 1 of 13 features match AI direction, volume
ramps 12×–276×). Mark explicitly that the 50% direction threshold
and 5× volume threshold are exploratory.

#### Step C3: Update `cell-recommendations` to reference the new diagnostic
**Risk:** LOW
**Files:** `notebooks/09_full_report.ipynb` (cell `cell-recommendations`)
**What:** Add a new recommendation:

> **Lock the direction-priors registry and the 5× volume-ramp
> threshold in pre-registration before any external publication.**
> The Phase 17 diagnostic columns (`direction`, `volume_flag`) are
> exploratory until the priors and thresholds are committed in
> `data/preregistration/preregistration_lock.json`.

**Validation:** Re-render the PDF and inspect §11.3 + §11.3.1 +
§11.4. Check that no existing claims are contradicted.

---

### Phase D: Tests, Docs, HANDOFF (verification, 1 hour)

#### Step D1: End-to-end test against fixtures
**Risk:** LOW
**Files:** `tests/integration/test_phase17_classification.py` (new)
**What:** Use the existing `data/analysis/{slug}_result.json` files
as fixtures. For each of the 8 MODERATE authors plus Colby Hall,
assert:
- `classify_direction_concordance` returns the expected
  `DirectionConcordance` value.
- `compute_volume_ramp_flag` returns the expected `VolumeRampFlag`.
- The full per-author row (strength, direction, volume_flag, pa, pb)
  matches the canonical Apr 27 verdicts.

This pins the current behavior so future analysis-config changes
are surfaced as test diffs, not silent semantic drifts.
**Validation:** `uv run pytest tests/integration/test_phase17_classification.py -v`

#### Step D2: RUNBOOK update
**Risk:** LOW
**Files:** `docs/RUNBOOK.md`
**What:** Add a section "Phase 17 diagnostic columns" under the
report troubleshooting heading. Document:
- What `direction_ai`/`direction_non_ai`/`direction_mixed`/`direction_na` mean.
- What `volume_ramp` flag means and when it indicates a confound.
- How to override the volume-ramp threshold for sensitivity
  analysis (env var or CLI flag if added later — leave a TODO if
  not in scope here).

#### Step D3: HANDOFF block
**Risk:** LOW
**Files:** `HANDOFF.md`
**What:** Append the standard completion block per CLAUDE.md
contract. Include:
- Status: Phase 17 complete.
- Files changed: list above.
- Decisions: directionality priors initial set, 50% concordance
  threshold, 5× volume ramp threshold (all flagged exploratory).
- Unresolved: pre-registration lock for the three new thresholds;
  PDF re-render is a separate operator action.
- Verification commands run and their result summary.

#### Step D4: GUARDRAILS sign (conditional)
**Risk:** LOW
**Files:** `docs/GUARDRAILS.md`
**What:** If during the implementation a footgun is discovered
(e.g. `n_pre` is sometimes 0 when all baseline tests are
degenerate; or some authors have no n_pre / n_post fields at all),
append an Agent-Learned Sign documenting the pattern and the
defensive code added.

---

## Validation & Verification

Before considering the phase complete:

```bash
# Library tests
uv run pytest tests/unit/test_direction_priors.py -v
uv run pytest tests/unit/test_direction_concordance.py -v
uv run pytest tests/unit/test_volume_ramp_flag.py -v

# Integration tests
uv run pytest tests/integration/test_phase17_classification.py -v

# Full test suite (no regressions)
uv run pytest tests/ -v

# Coverage
uv run pytest tests/ -v --cov=src --cov-report=term-missing

# Lint + format
uv run ruff check .
uv run ruff format --check .

# Notebook re-render smoke test
uv run jupyter nbconvert --to notebook --execute \
    notebooks/09_full_report.ipynb \
    --output /tmp/09_full_report_check.ipynb

# Optional: full report build
uv run forensics report --format pdf
```

Acceptance:
- All new tests pass.
- No existing tests regress.
- Notebook re-renders cleanly.
- Re-rendered §11.3 table shows Colby Hall as STRONG with
  `direction=direction_ai`, `volume_flag=volume_decline`.
- Re-rendered §11.3 table shows the 8 ex-MODERATE authors with
  `direction=direction_non_ai` (or MIXED in the case of
  isaac-schorr) and `volume_flag=volume_ramp`.
- §11.3.1 markdown is present and self-contained.
- §11.4 contains the new pre-registration recommendation.
- HANDOFF.md, RUNBOOK.md updated.

---

## Out-of-Scope (Explicit)

To prevent re-litigation in future phases:

- **Pre-registration lock** for the new thresholds. Phase 17 lands
  the diagnostics; locking is a separate human decision.
- **Changing existing `FindingStrength` semantics.** STRONG/MODERATE/
  WEAK/NONE stay exactly as Phase-16-A patched them.
- **Removing or downgrading any author from the report based on the
  new diagnostics.** The classifier still classifies every author by
  the existing rules; the new columns inform interpretation, not
  filtering.
- **Phase 9 (token-probability) integration.** Pipeline C is still
  the planned third evidence stream and remains untouched here.
- **Multi-model AI baseline (Phase 10) expansion.** Single-model
  Llama 3.2 baseline stays the current state.
- **Bias audit of target-vs-control framing.** The structural
  asymmetry of `editorial_vs_author_signal` (only target authors get
  one) is a known design choice, not a Phase 17 bug to fix.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Direction priors are wrong for a feature | M | M | Mark uncertain priors as `None`; require pre-reg lock before claiming priors are validated |
| 50% concordance / 5× volume thresholds are arbitrary | M | M | Document exploratory status in three places (docstring, notebook §11.3.1, §11.4 recommendation) |
| Notebook JSON edit corrupts the file | L | H | Use Python-script round-trip pattern, not text editor; round-trip through `json.loads`/`json.dumps` to validate after every write |
| n_pre/n_post pulled from wrong test in heterogeneous list | L | M | Document in `compute_volume_ramp_flag` docstring + cover with unit test |
| Future feature additions silently miss a prior | L | L | Audit test in `test_direction_priors.py` fails on uncovered features |
| Re-rendered report contradicts existing §11.1 narrative | L | M | §11.3.1 markdown should reference the §11.1 caveats explicitly |

---

## Definition of Done

- [ ] `src/forensics/analysis/direction_priors.py` exists with
      `AI_TYPICAL_DIRECTION` mapping and `direction_from_d` helper.
- [ ] `src/forensics/models/report.py` exports `DirectionConcordance`,
      `DirectionBreakdown`, `VolumeRampFlag`,
      `classify_direction_concordance`, `compute_volume_ramp_flag`.
- [ ] All new public symbols re-exported from `forensics.models`.
- [ ] Unit tests for the three new public functions land green.
- [ ] Integration test pinning Apr 27 verdicts lands green.
- [ ] `notebooks/09_full_report.ipynb` cell `cell-strength-code`
      computes and displays the new columns.
- [ ] New cell `cell-direction-md` (§11.3.1) explains the diagnostic.
- [ ] `cell-recommendations` includes the new pre-reg recommendation.
- [ ] Notebook re-renders cleanly via nbconvert smoke test.
- [ ] `docs/RUNBOOK.md` has the Phase 17 section.
- [ ] `HANDOFF.md` has a Phase 17 completion block.
- [ ] Full test suite passes with no regressions.
- [ ] `uv run ruff check .` and `uv run ruff format --check .` clean.
- [ ] No `FindingStrength` semantics changed; existing
      `classify_finding_strength` callers unaffected.
