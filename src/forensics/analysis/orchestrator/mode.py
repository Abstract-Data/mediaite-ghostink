"""Confirmatory vs exploratory analysis flags (threaded as one object)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalysisMode:
    """How strictly embedding drift and preregistration gates apply.

    ``exploratory`` relaxes missing lock / thin-embedding failures where the
    pipeline documents permissive behaviour. ``allow_pre_phase16_embeddings``
    additionally permits legacy embedding revisions when paired with
    ``exploratory`` (see :func:`forensics.analysis.drift.validate_embedding_record`).
    """

    exploratory: bool = False
    allow_pre_phase16_embeddings: bool = False

    def run_metadata_subset(self) -> dict[str, bool]:
        """Keys written to ``run_metadata.json`` (stable contract)."""
        return {
            "exploratory": self.exploratory,
            "allow_pre_phase16_embeddings": self.allow_pre_phase16_embeddings,
        }


# Single immutable default for optional parameters (frozen slots).
DEFAULT_ANALYSIS_MODE = AnalysisMode()
