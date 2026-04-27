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

# Supported change-point backends (hash-participating; typos must fail validation).
ChangepointMethod = Literal["pelt", "bocpd", "chow", "cusum"]

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
    bulk_fetch_mode: bool = Field(False, json_schema_extra={"include_in_config_hash": True})
    retry_backoff_seconds: float = 5.0
    # ``deduplicate_articles`` Hamming threshold (0 = disable near-dup collapse).
    simhash_threshold: int = Field(
        default=3,
        ge=0,
        le=64,
        json_schema_extra={"include_in_config_hash": True},
    )
    # Inclusive calendar years for ``wp/v2/posts``; both unset = full history.
    post_year_min: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        json_schema_extra={"include_in_config_hash": True},
    )
    post_year_max: int | None = Field(
        default=None,
        ge=1900,
        le=2100,
        json_schema_extra={"include_in_config_hash": True},
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


class AnalysisConfig(BaseModel):
    rolling_windows: list[int] = Field(default_factory=lambda: [30, 90])
    significance_threshold: float = Field(0.05, json_schema_extra={"include_in_config_hash": True})
    multiple_comparison_method: Literal["bonferroni", "benjamini_hochberg"] = Field(
        "benjamini_hochberg",
        json_schema_extra={"include_in_config_hash": True},
    )
    # Bootstrap replicates (preregistered; larger N tightens Monte Carlo error).
    bootstrap_iterations: int = Field(
        1000,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    # Min articles per pre/post segment around a CP for hypothesis tests.
    min_articles_for_period: int = Field(
        5,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # Human-readable bundle label (not HF revision).
    embedding_model_version: str = "v2.0"
    # HF ``revision=`` for ``SentenceTransformer``; must match locked embeddings.
    embedding_model_revision: str = Field(
        "main",
        json_schema_extra={"include_in_config_hash": True},
    )
    changepoint_methods: list[ChangepointMethod] = Field(
        default_factory=lambda: ["pelt", "bocpd"],
        json_schema_extra={"include_in_config_hash": True},
    )
    effect_size_threshold: float = Field(0.2, json_schema_extra={"include_in_config_hash": True})
    # PELT λ × per-feature std (J6). L1 + λ≈5 → ~3–8 breaks/continuous feature; sparse AI → BOCPD.
    pelt_penalty: float = Field(
        5.0,
        gt=0.0,
        json_schema_extra={"include_in_config_hash": True},
    )
    # PELT cost: L1 mean-shift (J6); L2 under-fired on sparse AI markers vs L1.
    pelt_cost_model: Literal["l2", "l1", "rbf"] = Field(
        "l1", json_schema_extra={"include_in_config_hash": True}
    )
    # BOCPD hazard h ∈ (0,1]; expected run length ∝ 1/h.
    bocpd_hazard_rate: float = Field(
        1 / 250.0,
        gt=0.0,
        le=1.0,
        json_schema_extra={"include_in_config_hash": True},
    )
    # M-11 — when True, override ``bocpd_hazard_rate`` with ~expected_changes/n_articles.
    bocpd_hazard_auto: bool = Field(False, json_schema_extra={"include_in_config_hash": True})
    bocpd_expected_changes_per_author: int = Field(
        3, ge=1, json_schema_extra={"include_in_config_hash": True}
    )
    # BOCPD mode: default ``map_reset``; ``p_r0_legacy`` = pre–Phase 15 A ``P(r=0)`` (GUARDRAILS).
    bocpd_detection_mode: Literal["p_r0_legacy", "map_reset"] = Field(
        "map_reset", json_schema_extra={"include_in_config_hash": True}
    )
    bocpd_map_drop_ratio: float = Field(
        0.5,
        gt=0.0,
        le=1.0,
        json_schema_extra={"include_in_config_hash": True},
    )
    bocpd_min_run_length: int = Field(5, ge=1, json_schema_extra={"include_in_config_hash": True})
    # Post-process MAP-reset stream only (not hashed).
    bocpd_reset_cooldown: int = Field(3, ge=0)
    bocpd_merge_window: int = Field(2, ge=0)
    # Student-t BOCPD likelihood (NIG).
    bocpd_student_t: bool = Field(True, json_schema_extra={"include_in_config_hash": True})
    baseline_embedding_count: int = 20
    # I-03 — optional counts for manual baseline-curve sensitivity sweeps (empty = off).
    baseline_embedding_count_sensitivity: list[int] = Field(default_factory=list)
    convergence_window_days: int = Field(
        90,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    # Derive convergence window from cadence (bounded min/max).
    convergence_window_adaptive: bool = Field(
        False,
        json_schema_extra={"include_in_config_hash": True},
    )
    convergence_window_days_min: int = Field(
        30,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    convergence_window_days_max: int = Field(
        180,
        ge=1,
        json_schema_extra={"include_in_config_hash": True},
    )
    # Family-level ratio gate (B3); default 0.50 vs raw-feature count.
    convergence_min_feature_ratio: float = Field(
        0.50,
        ge=0.0,
        le=1.0,
        json_schema_extra={"include_in_config_hash": True},
    )
    # CP list for convergence: raw vs section-adjusted (J5).
    convergence_cp_source: Literal["raw", "section_adjusted"] = Field(
        "section_adjusted",
        json_schema_extra={"include_in_config_hash": True},
    )
    # Drift-only path when pipeline_b ≥ this (Fix-G); 1.0+ effectively disables.
    convergence_drift_only_pb_threshold: float = Field(
        0.3,
        ge=0.0,
        le=1.0,
        json_schema_extra={"include_in_config_hash": True},
    )
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
    # Rolling-window LDA for topic_diversity_score.
    content_lda_n_components: int = 10
    content_lda_max_peer_documents: int = 48
    content_lda_max_iter: int = 15
    content_lda_max_features: int = 2000
    content_lda_max_df: float = 0.95
    content_lda_max_chars_per_document: int = 96_000
    content_lda_random_state: int = Field(42, json_schema_extra={"include_in_config_hash": True})
    drift_umap_random_state: int = Field(42, json_schema_extra={"include_in_config_hash": True})
    hypothesis_bootstrap_seed: int = Field(42, json_schema_extra={"include_in_config_hash": True})
    embedding_vector_dim: int = Field(384, ge=1, json_schema_extra={"include_in_config_hash": True})
    # Analyze-time min word count (0 = off).
    analysis_min_word_count: int = Field(0, ge=0)
    # BH grouping: per-author vs per-feature-family (C).
    fdr_grouping: Literal["author", "family"] = Field(
        "family", json_schema_extra={"include_in_config_hash": True}
    )
    # Optional second BH pass across authors (M-09).
    enable_cross_author_correction: bool = Field(
        False, json_schema_extra={"include_in_config_hash": True}
    )
    # Min finite obs per segment for Welch / MW (M-15).
    hypothesis_min_segment_n: int = Field(
        10,
        ge=2,
        json_schema_extra={"include_in_config_hash": True},
    )
    # KS tests (correlated with MW here); default off → fewer tests per CP (C1).
    enable_ks_test: bool = Field(False, json_schema_extra={"include_in_config_hash": True})
    # Pipeline B scoring: legacy (v0.14) vs percentile (E).
    pipeline_b_mode: Literal["legacy", "percentile"] = Field(
        "legacy", json_schema_extra={"include_in_config_hash": True}
    )
    # Section one-hot residualization before CPD (J5).
    section_residualize_features: bool = Field(
        False, json_schema_extra={"include_in_config_hash": True}
    )
    # Section diagnostic gates (not hashed).
    section_min_articles: int = Field(50, ge=1)
    min_articles_per_section_for_residualize: int = Field(10, ge=1)
    # Parallelism (wall-clock only; not hashed).
    max_workers: int | None = None
    feature_workers: int = 1


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
    excluded_sections: frozenset[str] = Field(
        default_factory=lambda: frozenset({"sponsored", "partner-content", "crosspost"})
    )


class FeaturesConfig(BaseModel):
    """Phase 15 — feature-store schema contract."""

    # Bump when Parquet schema adds required columns (loader enforces ≥ this).
    feature_parquet_schema_version: int = Field(
        2, ge=1, json_schema_extra={"include_in_config_hash": True}
    )
    # Sections dropped at extract time; keep aligned with ``SurveyConfig`` (J2).
    excluded_sections: frozenset[str] = Field(
        default_factory=lambda: frozenset({"sponsored", "partner-content", "crosspost"})
    )


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

    @model_validator(mode="after")
    def _excluded_sections_match_survey(self) -> ForensicsSettings:
        """``features.excluded_sections`` must equal ``survey.excluded_sections``."""
        if self.features.excluded_sections != self.survey.excluded_sections:
            msg = (
                "features.excluded_sections must equal survey.excluded_sections "
                f"(features={sorted(self.features.excluded_sections)!r}, "
                f"survey={sorted(self.survey.excluded_sections)!r}). "
                "Align both [features] and [survey] tables in config.toml."
            )
            raise ValueError(msg)
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def db_path(self) -> Path:
        """Default SQLite corpus path under the project root."""
        return get_project_root() / DEFAULT_DB_RELATIVE

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
