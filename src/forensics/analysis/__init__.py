"""Analysis package: change-point, drift, convergence, statistics, orchestration.

Barrel re-exports are limited to high-level orchestration; other entrypoints
live in submodules (``drift``, ``changepoint``, …). ``__all__`` is exhaustive.
"""

from forensics.analysis.orchestrator import assemble_analysis_result, run_full_analysis

__all__ = ["assemble_analysis_result", "run_full_analysis"]
