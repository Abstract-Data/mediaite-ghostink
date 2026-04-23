"""Re-export shim — ``AnalysisArtifactPaths`` now lives in :mod:`forensics.paths`.

Kept so that existing imports (including external notebooks and the test suite)
continue to work without edits. New code should import from ``forensics.paths``
directly; cross-stage consumers in ``features/`` already do.
"""

from __future__ import annotations

from forensics.paths import AnalysisArtifactPaths

__all__ = ["AnalysisArtifactPaths"]
