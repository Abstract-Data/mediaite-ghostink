"""Deprecated re-export for :class:`~forensics.paths.AnalysisArtifactPaths`.

The canonical definition is :mod:`forensics.paths`.

.. deprecated:: Run 11 (RF-SMELL-002)
   Import ``AnalysisArtifactPaths`` from ``forensics.paths``. This module remains
   a thin shim for external notebooks and legacy code; it may be removed after
   a deprecation window (mirror :mod:`forensics.analysis.utils` re-export policy).

"""

from __future__ import annotations

from forensics.paths import AnalysisArtifactPaths

__all__ = ["AnalysisArtifactPaths"]
