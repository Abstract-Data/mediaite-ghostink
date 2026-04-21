"""Typed configuration loaded from config.toml with FORENSICS_* env overrides."""

from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd()


def get_project_root() -> Path:
    """Directory containing pyproject.toml (used for default data/ paths)."""
    return _project_root()


def _config_toml_path() -> Path:
    override = os.environ.get("FORENSICS_CONFIG_FILE")
    if override:
        return Path(override).expanduser().resolve()
    return _project_root() / "config.toml"


class AuthorConfig(BaseModel):
    name: str
    slug: str
    outlet: str = "mediaite.com"
    role: Literal["target", "control"]
    archive_url: str
    baseline_start: date
    baseline_end: date


class ScrapingConfig(BaseModel):
    rate_limit_seconds: float = 2.0
    rate_limit_jitter: float = 0.5
    respect_robots_txt: bool = True
    user_agent: str = "AI-Writing-Forensics/1.0 (research)"
    max_concurrent: int = 3
    max_retries: int = 3
    retry_backoff_seconds: float = 5.0


class AnalysisConfig(BaseModel):
    rolling_windows: list[int] = Field(default_factory=lambda: [30, 90])
    significance_threshold: float = 0.05
    multiple_comparison_method: Literal["bonferroni", "benjamini_hochberg"] = "benjamini_hochberg"
    bootstrap_iterations: int = 1000
    min_articles_for_period: int = 5
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_model_version: str = "v2.0"
    changepoint_methods: list[str] = Field(default_factory=lambda: ["pelt", "bocpd"])
    effect_size_threshold: float = 0.5


class ReportConfig(BaseModel):
    title: str = "Writing Forensics Analysis"
    output_format: Literal["html", "pdf", "both"] = "both"
    include_sections: list[str] = Field(default_factory=list)
    chart_theme: Literal["plotly_white", "forensics"] = "forensics"
    cloudflare_deploy: bool = False

    @field_validator("include_sections")
    @classmethod
    def _sections_known(cls, v: list[str]) -> list[str]:
        allowed = {
            "executive",
            "methodology",
            "evidence",
            "controls",
            "appendix",
        }
        bad = [s for s in v if s not in allowed]
        if bad:
            msg = f"Unknown report sections: {bad}; allowed={sorted(allowed)}"
            raise ValueError(msg)
        return v


class ForensicsSettings(BaseSettings):
    """Application settings: TOML first, then environment variable overrides."""

    model_config = SettingsConfigDict(env_prefix="FORENSICS_", env_nested_delimiter="__")

    authors: list[AuthorConfig]
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def db_path(self) -> Path:
        """Default SQLite corpus path under the project root."""
        return _project_root() / "data" / "articles.db"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            TomlConfigSettingsSource(settings_cls, _config_toml_path()),
            env_settings,
        )


@lru_cache(maxsize=1)
def get_settings() -> ForensicsSettings:
    """Load settings from config.toml (or FORENSICS_CONFIG_FILE) with env overrides."""
    return ForensicsSettings()
