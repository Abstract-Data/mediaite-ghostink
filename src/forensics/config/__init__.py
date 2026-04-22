"""Configuration: TOML + environment-backed settings."""

import warnings

from forensics.config.settings import (
    AnalysisConfig,
    AuthorConfig,
    ForensicsSettings,
    ReportConfig,
    ScrapingConfig,
    get_project_root,
    get_settings,
)

_SETTINGS_PROXY_WARNED = False


class _SettingsProxy:
    """Deprecated notebook alias; use :func:`get_settings` instead."""

    __slots__ = ()

    def __getattr__(self, name: str):
        global _SETTINGS_PROXY_WARNED
        if not _SETTINGS_PROXY_WARNED:
            warnings.warn(
                "`from forensics.config import settings` is deprecated; use "
                "`from forensics.config import get_settings` and call `get_settings()` "
                "(assign to a local name, e.g. `settings = get_settings()`).",
                DeprecationWarning,
                stacklevel=2,
            )
            _SETTINGS_PROXY_WARNED = True
        return getattr(get_settings(), name)


settings = _SettingsProxy()

__all__ = [
    "AnalysisConfig",
    "AuthorConfig",
    "ForensicsSettings",
    "ReportConfig",
    "ScrapingConfig",
    "get_project_root",
    "get_settings",
    "settings",
]
