"""Analysis orchestration package (split from legacy module).

Monkeypatch contract
--------------------
Tests may replace the following names on *this package module only*
(``forensics.analysis.orchestrator.<symbol>``). :func:`_sync_patchable_globals`
re-binds them into submodules that would otherwise resolve stale references
from their own module globals:

- ``uuid4``, ``datetime``, ``_clean_feature_series``, ``_run_per_author_analysis``,
  ``_resolve_parallel_refresh_workers``, ``_isolated_author_worker``,
  ``_validate_and_promote_isolated_outputs``.

Any other symbol must be patched on its defining submodule (for example
``forensics.analysis.orchestrator.comparison``), not here.
"""

from __future__ import annotations

from datetime import datetime  # noqa: F401 — re-exported for monkeypatch + _PATCH_TARGETS
from types import ModuleType
from typing import Any
from uuid import uuid4  # noqa: F401 — re-exported for monkeypatch + _PATCH_TARGETS

from forensics.analysis.orchestrator import comparison as _comparison
from forensics.analysis.orchestrator import parallel as _parallel
from forensics.analysis.orchestrator import per_author as _per_author
from forensics.analysis.orchestrator import runner as _runner
from forensics.analysis.orchestrator import sensitivity as _sensitivity
from forensics.analysis.orchestrator import staleness as _staleness
from forensics.analysis.orchestrator.mode import DEFAULT_ANALYSIS_MODE, AnalysisMode
from forensics.analysis.orchestrator.timings import AnalysisTimings

_clean_feature_series = _per_author._clean_feature_series
_run_per_author_analysis = _per_author._run_per_author_analysis
_resolve_targets_and_controls = _comparison._resolve_targets_and_controls
_resolve_max_workers = _parallel._resolve_max_workers
_resolve_parallel_refresh_workers = _parallel._resolve_parallel_refresh_workers
_isolated_author_worker = _parallel._isolated_author_worker
_per_author_worker = _parallel._per_author_worker
_validate_and_promote_isolated_outputs = _parallel._validate_and_promote_isolated_outputs

_PATCH_TARGETS: dict[str, tuple[ModuleType, ...]] = {
    "uuid4": (_per_author, _parallel, _staleness),
    "datetime": (_per_author, _parallel, _staleness),
    "_clean_feature_series": (_per_author,),
    "_run_per_author_analysis": (_parallel, _sensitivity),
    "_resolve_parallel_refresh_workers": (_parallel,),
    "_isolated_author_worker": (_parallel,),
    "_validate_and_promote_isolated_outputs": (_parallel,),
}


def _sync_patchable_globals() -> None:
    for name, modules in _PATCH_TARGETS.items():
        value = globals()[name]
        for module in modules:
            setattr(module, name, value)


def assemble_analysis_result(*args: Any, **kwargs: Any):
    _sync_patchable_globals()
    return _per_author.assemble_analysis_result(*args, **kwargs)


def run_full_analysis(*args: Any, **kwargs: Any):
    _sync_patchable_globals()
    return _runner.run_full_analysis(*args, **kwargs)


def run_parallel_author_refresh(*args: Any, **kwargs: Any):
    _sync_patchable_globals()
    return _parallel.run_parallel_author_refresh(*args, **kwargs)


def _run_hypothesis_tests_for_changepoints(*args: Any, **kwargs: Any):
    _sync_patchable_globals()
    return _per_author._run_hypothesis_tests_for_changepoints(*args, **kwargs)


def _run_section_residualized_sensitivity(*args: Any, **kwargs: Any):
    _sync_patchable_globals()
    return _sensitivity._run_section_residualized_sensitivity(*args, **kwargs)


run_compare_only = _comparison.run_compare_only

__all__ = [
    "AnalysisMode",
    "AnalysisTimings",
    "DEFAULT_ANALYSIS_MODE",
    "assemble_analysis_result",
    "run_compare_only",
    "run_full_analysis",
    "run_parallel_author_refresh",
    "_clean_feature_series",
    "_run_hypothesis_tests_for_changepoints",
    "_run_per_author_analysis",
    "_run_section_residualized_sensitivity",
    "_resolve_targets_and_controls",
    "_resolve_max_workers",
    "_resolve_parallel_refresh_workers",
    "_isolated_author_worker",
    "_per_author_worker",
    "_validate_and_promote_isolated_outputs",
]

_sync_patchable_globals()
