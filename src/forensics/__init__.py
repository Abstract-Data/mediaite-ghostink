"""Mediaite forensics pipeline package.

The root namespace intentionally re-exports only :mod:`forensics.config` helpers
for library-style use. Pipeline stages live in subpackages (``scraper``,
``features``, ``analysis``, …); import concrete modules from those packages
rather than expecting a deep barrel on ``forensics``.
"""

from forensics.config import ForensicsSettings, get_settings

# Bumped automatically by release-please on every release PR merge.
# x-release-please-version
__version__ = "0.1.0"

__all__ = ["ForensicsSettings", "__version__", "get_settings"]
