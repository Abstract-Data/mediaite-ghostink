"""Recoverable worker-loop errors for parallel analysis (P3-SEC-001 / RF-DRY-002)."""

from __future__ import annotations

import json
from typing import Final

from forensics.analysis.drift import EmbeddingDriftInputsError, EmbeddingRevisionGateError
from forensics.analysis.orchestrator.embedding_policy import embedding_fail_should_propagate
from forensics.analysis.orchestrator.mode import AnalysisMode

_WORKER_RECOVERABLE_CORE: tuple[type[BaseException], ...] = (
    ArithmeticError,
    EOFError,
    json.JSONDecodeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    EmbeddingDriftInputsError,
    EmbeddingRevisionGateError,
)

try:
    import polars.exceptions as _pl_exc

    _POLARS_EXC: tuple[type[BaseException], ...] = (
        _pl_exc.ComputeError,
        _pl_exc.NoDataError,
        _pl_exc.SchemaError,
    )
except ImportError:
    _POLARS_EXC = ()

WORKER_RECOVERABLE_ERRORS: Final[tuple[type[BaseException], ...]] = (
    _WORKER_RECOVERABLE_CORE + _POLARS_EXC
)

_COMPARISON_ITERATION_RECOVERABLE: tuple[type[BaseException], ...] = (
    ValueError,
    OSError,
    EmbeddingDriftInputsError,
)


def parallel_worker_exception_is_recoverable(mode: AnalysisMode, exc: BaseException) -> bool:
    """True when a process-pool worker failure should be logged and skipped."""
    if embedding_fail_should_propagate(mode, exc):
        return False
    return isinstance(exc, WORKER_RECOVERABLE_ERRORS)


def comparison_iteration_exception_is_recoverable(mode: AnalysisMode, exc: BaseException) -> bool:
    """Match historical ``_iter_compare_targets`` catch tuple + embedding propagation."""
    if embedding_fail_should_propagate(mode, exc):
        return False
    return isinstance(exc, _COMPARISON_ITERATION_RECOVERABLE)
