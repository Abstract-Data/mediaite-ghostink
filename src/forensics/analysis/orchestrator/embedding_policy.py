"""Shared policy for when embedding drift failures should abort analysis."""

from __future__ import annotations

from forensics.analysis.drift import EmbeddingDriftInputsError, EmbeddingRevisionGateError
from forensics.analysis.orchestrator.mode import AnalysisMode


def embedding_fail_should_propagate(mode: AnalysisMode, exc: BaseException) -> bool:
    """Confirmatory runs surface embedding drift failures instead of swallowing them."""
    return (not mode.exploratory) and isinstance(
        exc,
        (EmbeddingDriftInputsError, EmbeddingRevisionGateError),
    )
