"""Typed configuration loaded from config.toml with FORENSICS_* env overrides."""

from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from forensics.config.analysis_settings import (
    AnalysisConfig,
    BocpdConfig,
    ContentLdaConfig,
    ConvergenceConfig,
    EmbeddingStackConfig,
    HypothesisConfig,
    PeltConfig,
)
from forensics.config.constants import CONFIG_HASH_EXTRA, DEFAULT_EXCLUDED_SECTIONS

# Canonical relative location of the SQLite corpus under the project root.
# Single source of truth for all modules that resolve the DB path.
DEFAULT_DB_RELATIVE = Path("data") / "articles.db"


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
    # Bulk metadata: pull ``content.rendered`` (100 posts/request); ``fetch_articles`` no-ops.
    bulk_fetch_mode: bool = Field(False, json_schema_extra=CONFIG_HASH_EXTRA)
    retry_backoff_seconds: float = 5.0
    # ``deduplicate_articles`` Hamming threshold (0 = disable near-dup collapse).
    simhash_threshold: int = Field(
        default=3,
        ge=0,
        le=64,
        json_schema_extra=CONFIG_HASH_EXTRA,
    )
    # Inclusive calendar years for ``wp/v2/posts``; both unset = full history.
    post_year_min: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        json_schema_extra=CONFIG_HASH_EXTRA,
    )
    post_year_max: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        json_schema_extra=CONFIG_HASH_EXTRA,
    )

    @model_validator(mode="after")
    def _post_year_range_consistent(self) -> ScrapingConfig:
        has_min = self.post_year_min is not None
        has_max = self.post_year_max is not None
        if has_min ^ has_max:
            msg = "post_year_min and post_year_max must both be set or both omitted"
            raise ValueError(msg)
        if has_min and has_max and self.post_year_max < self.post_year_min:
            msg = "post_year_max must be >= post_year_min"
            raise ValueError(msg)
        return self


class SurveyConfig(BaseModel):
    """Configuration for blind newsroom-wide survey mode (Phase 12 §1)."""

    min_articles: int = 50
    min_span_days: int = 730
    min_words_per_article: int = 200
    min_articles_per_year: float = 12.0
    require_recent_activity: bool = True
    recent_activity_days: int = 180
    # Drop shared byline accounts from survey cohort by default (D).
    exclude_shared_bylines: bool = True
    # Sections excluded from survey baselines (J2); mirror ``FeaturesConfig``.
    excluded_sections: frozenset[str] = Field(default=DEFAULT_EXCLUDED_SECTIONS)


class FeaturesConfig(BaseModel):
    """Phase 15 — feature-store schema contract."""

    # Bump when Parquet schema adds required columns (loader enforces ≥ this).
    feature_parquet_schema_version: int = Field(2, ge=1, json_schema_extra=CONFIG_HASH_EXTRA)
    # Sections dropped at extract time — always mirrored from ``SurveyConfig`` (J2)
    # by :meth:`ForensicsSettings._mirror_survey_excluded_sections_to_features`.
    excluded_sections: frozenset[str] = Field(default=DEFAULT_EXCLUDED_SECTIONS)


class ProbabilityConfig(BaseModel):
    """Phase 9 — token-level probability feature settings."""

    reference_model: str = "gpt2"
    reference_model_revision: str = "e7da7f2"
    binoculars_model_base: str = "tiiuae/falcon-7b"
    binoculars_model_instruct: str = "tiiuae/falcon-7b-instruct"
    binoculars_enabled: bool = False
    max_sequence_length: int = 1024
    sliding_window_stride: int = 512
    batch_size: int = 16
    device: Literal["auto", "cpu", "cuda"] = "auto"
    low_ppl_threshold: float = 20.0


class BaselineConfig(BaseModel):
    """Phase 10 — AI baseline generation via local Ollama models."""

    ollama_base_url: str = "http://localhost:11434"
    models: list[str] = Field(default_factory=lambda: ["llama3.1:8b", "mistral:7b", "gemma2:9b"])
    temperatures: list[float] = Field(default_factory=lambda: [0.0, 0.8])
    articles_per_cell: int = 30
    max_tokens: int = 1500
    request_timeout: float = 120.0


class ChainOfCustodyConfig(BaseModel):
    """Phase 10 — chain-of-custody enforcement flags."""

    verify_corpus_hash: bool = True
    verify_raw_archives: bool = True
    log_all_generations: bool = True


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


def _get_survey_excluded_sections(survey: object) -> list[str] | None:
    """Return ``excluded_sections`` from a survey dict or ``SurveyConfig``, else ``None``."""
    if isinstance(survey, dict):
        return survey.get("excluded_sections")  # type: ignore[return-value]
    if isinstance(survey, SurveyConfig):
        return survey.excluded_sections
    return None


def _patch_features_excluded_sections(
    data: dict[str, object],
    features: object,
    sections: list[str],
) -> dict[str, object]:
    """Return *data* with ``features.excluded_sections`` replaced by *sections*."""
    if features is None:
        return {**data, "features": {"excluded_sections": sections}}
    if isinstance(features, dict):
        return {**data, "features": {**features, "excluded_sections": sections}}
    if isinstance(features, FeaturesConfig):
        return {**data, "features": features.model_copy(update={"excluded_sections": sections})}
    return data


class ForensicsSettings(BaseSettings):
    """Application settings: TOML first, then environment variable overrides."""

    model_config = SettingsConfigDict(env_prefix="FORENSICS_", env_nested_delimiter="__")

    authors: list[AuthorConfig]
    spacy_model: str = Field(
        default="en_core_web_md",
        description="spaCy pipeline for extract + preflight (single source of truth).",
    )
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    survey: SurveyConfig = Field(default_factory=SurveyConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    probability: ProbabilityConfig = Field(default_factory=ProbabilityConfig)
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)
    chain_of_custody: ChainOfCustodyConfig = Field(default_factory=ChainOfCustodyConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)

    @model_validator(mode="before")
    @classmethod
    def _mirror_survey_excluded_sections_to_features_before(cls, data: object) -> object:
        """``survey.excluded_sections`` is canonical (J2); copy into ``features`` before init."""
        if not isinstance(data, dict):
            return data
        survey = data.get("survey")
        if survey is None:
            return data
        sections = _get_survey_excluded_sections(survey)
        if sections is None:
            return data
        return _patch_features_excluded_sections(data, data.get("features"), sections)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def db_path(self) -> Path:
        """Default SQLite corpus path under the project root."""
        return get_project_root() / DEFAULT_DB_RELATIVE

    # Incremental migration (RF-SMELL-001): prefer these over deep ``settings.analysis.*`` chains.
    @property
    def pelt(self) -> PeltConfig:
        return self.analysis.pelt

    @property
    def bocpd(self) -> BocpdConfig:
        return self.analysis.bocpd

    @property
    def convergence(self) -> ConvergenceConfig:
        return self.analysis.convergence

    @property
    def content_lda(self) -> ContentLdaConfig:
        return self.analysis.content_lda

    @property
    def hypothesis(self) -> HypothesisConfig:
        return self.analysis.hypothesis

    @property
    def embedding(self) -> EmbeddingStackConfig:
        return self.analysis.embedding

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
    """Load TOML + env (``FORENSICS_*``). Clear with ``get_settings.cache_clear()`` in tests."""
    return ForensicsSettings()
