"""Analysis orchestration package (split from legacy module)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from forensics.analysis.orchestrator import comparison as _comparison
from forensics.analysis.orchestrator import parallel as _parallel
from forensics.analysis.orchestrator import per_author as _per_author
from forensics.analysis.orchestrator import runner as _runner
from forensics.analysis.orchestrator import sensitivity as _sensitivity
from forensics.analysis.orchestrator import staleness as _staleness
from forensics.analysis.orchestrator.timings import AnalysisTimings


def _sync_patchable_globals() -> None:
    """Preserve legacy monkeypatch points from the old monolithic module."""
    _per_author.uuid4 = uuid4
    _per_author.datetime = datetime
    _parallel.uuid4 = uuid4
    _staleness.datetime = datetime


def assemble_analysis_result(*args: Any, **kwargs: Any):
    _sync_patchable_globals()
    return _per_author.assemble_analysis_result(*args, **kwargs)


def run_full_analysis(*args: Any, **kwargs: Any):
    _sync_patchable_globals()
    return _runner.run_full_analysis(*args, **kwargs)


def run_parallel_author_refresh(*args: Any, **kwargs: Any):
    _sync_patchable_globals()
    _parallel._resolve_parallel_refresh_workers = _resolve_parallel_refresh_workers
    _parallel._isolated_author_worker = _isolated_author_worker
    _parallel._validate_and_promote_isolated_outputs = _validate_and_promote_isolated_outputs
    return _parallel.run_parallel_author_refresh(*args, **kwargs)


def _run_hypothesis_tests_for_changepoints(*args: Any, **kwargs: Any):
    _per_author._clean_feature_series = _clean_feature_series
    return _per_author._run_hypothesis_tests_for_changepoints(*args, **kwargs)


def _run_section_residualized_sensitivity(*args: Any, **kwargs: Any):
    _sensitivity._run_per_author_analysis = _run_per_author_analysis
    return _sensitivity._run_section_residualized_sensitivity(*args, **kwargs)


run_compare_only = _comparison.run_compare_only
_clean_feature_series = _per_author._clean_feature_series
_run_per_author_analysis = _per_author._run_per_author_analysis
_resolve_targets_and_controls = _comparison._resolve_targets_and_controls
_resolve_max_workers = _parallel._resolve_max_workers
_resolve_parallel_refresh_workers = _parallel._resolve_parallel_refresh_workers
_isolated_author_worker = _parallel._isolated_author_worker
_per_author_worker = _parallel._per_author_worker
_validate_and_promote_isolated_outputs = _parallel._validate_and_promote_isolated_outputs

__all__ = [
    "AnalysisTimings",
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
    "datetime",
    "uuid4",
]
