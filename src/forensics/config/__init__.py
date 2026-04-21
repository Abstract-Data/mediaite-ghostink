"""Configuration: TOML + environment-backed settings."""

from forensics.config.settings import (
    AnalysisConfig,
    AuthorConfig,
    BaselineConfig,
    ChainOfCustodyConfig,
    ForensicsSettings,
    ProbabilityConfig,
    ReportConfig,
    ScrapingConfig,
    get_project_root,
    get_settings,
)


class _SettingsProxy:
    """Notebook-friendly alias: ``from forensics.config import settings``."""

    __slots__ = ()

    def __getattr__(self, name: str):
        return getattr(get_settings(), name)


settings = _SettingsProxy()

__all__ = [
    "AnalysisConfig",
    "AuthorConfig",
    "BaselineConfig",
    "ChainOfCustodyConfig",
    "ForensicsSettings",
    "ProbabilityConfig",
    "ReportConfig",
    "ScrapingConfig",
    "get_project_root",
    "get_settings",
    "settings",
]
