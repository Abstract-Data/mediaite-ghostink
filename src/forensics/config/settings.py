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
    # When True, the metadata phase also pulls `content.rendered` (100 posts per
    # request) and writes body text inline, so `fetch_articles` no-ops. Trades
    # per-article OG/ld+json metadata for ~100× fewer requests.
    bulk_fetch_mode: bool = False
    retry_backoff_seconds: float = 5.0
    # Hamming-distance threshold passed to ``deduplicate_articles``.
    # Lower is stricter; 0 disables near-duplicate collapsing entirely.
    simhash_threshold: int = Field(default=3, ge=0, le=64)
    # Inclusive calendar-year window for WordPress ``wp/v2/posts`` queries
    # (``after`` / ``before``). Both unset = no date filter (full history).
    post_year_min: int | None = Field(default=None, ge=1900, le=2100)
    post_year_max: int | None = Field(default=None, ge=1900, le=2100)

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
    pelt_penalty: float = 3.0
    bocpd_hazard_rate: float = 1 / 250.0
    bocpd_threshold: float = 0.5
    baseline_embedding_count: int = 20
    convergence_window_days: int = 90
    convergence_min_feature_ratio: float = 0.6
    convergence_perplexity_drop_ratio: float = 0.92
    convergence_burstiness_drop_ratio: float = 0.94
    # Empirical null for convergence windows (logged only; does not change windows).
    convergence_use_permutation: bool = False
    convergence_permutation_iterations: int = Field(default=1000, ge=10, le=50_000)
    convergence_permutation_seed: int = 42
    intra_variance_pairwise_max: int = 20
    ai_baseline_llm_temperature: float = 0.7
    feature_extraction_max_failure_ratio: float = 0.25
    lda_num_topics: int = 20
    lda_n_keywords: int = 10
    # Phase 4 content `topic_diversity_score` (per-article LDA on a rolling window).
    content_lda_n_components: int = 10
    content_lda_max_peer_documents: int = 48
    content_lda_max_iter: int = 15
    content_lda_max_features: int = 2000
    content_lda_max_df: float = 0.95
    content_lda_max_chars_per_document: int = 96_000


class SurveyConfig(BaseModel):
    """Configuration for blind newsroom-wide survey mode (Phase 12 §1)."""

    min_articles: int = 50
    min_span_days: int = 730
    min_words_per_article: int = 200
    min_articles_per_year: float = 12.0
    require_recent_activity: bool = True
    recent_activity_days: int = 180


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


class ForensicsSettings(BaseSettings):
    """Application settings: TOML first, then environment variable overrides."""

    model_config = SettingsConfigDict(env_prefix="FORENSICS_", env_nested_delimiter="__")

    authors: list[AuthorConfig]
    spacy_model: str = Field(
        default="en_core_web_md",
        description=(
            "spaCy pipeline name used for feature extraction and preflight validation. "
            "Keep both in sync by reading this single field."
        ),
    )
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    survey: SurveyConfig = Field(default_factory=SurveyConfig)
    probability: ProbabilityConfig = Field(default_factory=ProbabilityConfig)
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)
    chain_of_custody: ChainOfCustodyConfig = Field(default_factory=ChainOfCustodyConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def db_path(self) -> Path:
        """Default SQLite corpus path under the project root."""
        return _project_root() / DEFAULT_DB_RELATIVE

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
    """Load settings from config.toml (or FORENSICS_CONFIG_FILE) with env overrides.

    This is the supported global accessor. Prefer it over the deprecated
    ``forensics.config.settings`` proxy object (``from forensics.config import settings``),
    which exists only for backward compatibility in notebooks and scripts.

    Tests may clear the cache via ``get_settings.cache_clear()`` before changing
    ``FORENSICS_*`` environment variables or ``FORENSICS_CONFIG_FILE``.
    """
    return ForensicsSettings()
