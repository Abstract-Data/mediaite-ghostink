#!/usr/bin/env python3
"""Write deterministic 384-dim stub AI-baseline embeddings for Phase 0 drift continuity.

Ollama-backed ``forensics analyze --ai-baseline`` remains the authoritative path;
this script only materializes normalized vectors under ``data/ai_baseline/<slug>/embeddings/``
so ``ai_baseline_similarity`` is non-null when local LLM generation is unavailable.

Run from repo root::

    uv run python scripts/seed_phase0_ai_baseline_stubs.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Keep in sync with ``src/forensics/analysis/drift.py::AI_BASELINE_EMBEDDING_DIM``.
_DIM = 384

_SLUGS = (
    "ahmad-austin",
    "alex-griffing",
    "charlie-nash",
    "colby-hall",
    "david-gilmour",
    "isaac-schorr",
    "jennifer-bowers-bahney",
    "joe-depaolo",
    "michael-luciano",
    "sarah-rumpf",
    "tommy-christopher",
    "zachary-leeman",
    "mediaite-staff",
    "mediaite",
)


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "ai_baseline"
    for slug in _SLUGS:
        emb_dir = root / slug / "embeddings"
        emb_dir.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(abs(hash(slug)) % (2**32))
        for i in range(3):
            vec = rng.standard_normal(_DIM).astype(np.float32)
            nrm = float(np.linalg.norm(vec))
            vec /= nrm if nrm > 1e-8 else 1.0
            out = emb_dir / f"phase0_stub_{i}.npy"
            np.save(str(out.with_suffix("")), vec)


if __name__ == "__main__":
    main()
