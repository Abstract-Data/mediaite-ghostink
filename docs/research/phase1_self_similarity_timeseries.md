# Self-similarity time series — directional caveat (M-12 / M-13)

## Issue

Negative Cohen's *d* on rolling `self_similarity_30d` (post-split more *diverse*
than pre-split in TF–IDF peer space) is **not** prima facie evidence of AI
adoption when AI-like writing is often *more* self-similar. The signal can flip
sign for benign reasons.

## Mechanism (fill-up artefact)

`self_similarity_*` features intentionally return `None` until at least
`MIN_PEERS_FOR_SIMILARITY` usable prior peers exist (`content.py`). Early-career
windows therefore lack scores; once the peer window fills, the series steps
from missing values into dense, lower-variance cosine similarities. A
change-point on that transition can reflect **peer-window maturation**, not a
regime shift in prose quality.

## Operational guidance

- Treat large negative *d* on `self_similarity_30d` / `self_similarity_90d` as
  **ambiguous** unless peer coverage is stable across the split.
- For confirmatory narratives, prefer features whose definitions do not depend
  on a growing peer reservoir, or gate self-similarity tests on minimum career
  length / peer counts.

This note satisfies Phase 1 methodology item M-12 (documented conclusion in-repo).
M-13 (split-date vs strongest post-hoc anchor) remains an editorial disclosure
in preregistration amendments and report caveats.
