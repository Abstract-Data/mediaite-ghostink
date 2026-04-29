"""Configuration loading and Phase 16 F analysis-hash smoke checks."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from forensics.config import get_settings
from forensics.config.analysis_settings import AnalysisConfig, apply_flat_analysis_overrides
from forensics.config.settings import (
    AuthorConfig,
    FeaturesConfig,
    ForensicsSettings,
    SurveyConfig,
)
from forensics.utils.provenance import compute_analysis_config_hash


def _minimal_author() -> AuthorConfig:
    return AuthorConfig(
        name="Fixture Author",
        slug="fixture-author",
        outlet="mediaite.com",
        role="target",
        archive_url="https://www.mediaite.com/author/fixture-author/",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
    )


_HASH_SMOKE_FIELDS: list[tuple[str, Any]] = [
    ("pelt_penalty", 99.0),
    ("bocpd_hazard_rate", 0.05),
    ("min_articles_for_period", 99),
    ("embedding_model_revision", "0000000000000000000000000000000000000000"),
    ("changepoint_methods", ["cusum"]),
    ("enable_ks_test", True),
]


def test_get_settings_from_fixture(settings) -> None:
    assert len(settings.authors) == 1
    assert settings.authors[0].slug == "fixture-author"
    assert settings.scraping.max_retries == 3


def test_canonical_config_has_exactly_one_target_colby_hall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository ``config.toml`` must declare Colby Hall as the sole study target."""
    canonical = Path(__file__).resolve().parents[2] / "config.toml"
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(canonical))
    get_settings.cache_clear()
    try:
        loaded = get_settings()
        targets = [a for a in loaded.authors if a.role == "target"]
        assert len(targets) == 1
        assert targets[0].slug == "colby-hall"
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(("field", "alt"), _HASH_SMOKE_FIELDS)
def test_compute_analysis_config_hash_changes_for_hash_knob(
    settings,
    field: str,
    alt: Any,
) -> None:
    """Each listed analysis field must invalidate :func:`compute_analysis_config_hash`."""
    base_hash = compute_analysis_config_hash(settings)
    new_analysis = apply_flat_analysis_overrides(settings.analysis, **{field: alt})
    tweaked = settings.model_copy(update={"analysis": new_analysis})
    assert compute_analysis_config_hash(tweaked) != base_hash


def test_changepoint_methods_rejects_typo() -> None:
    with pytest.raises(ValidationError):
        AnalysisConfig(changepoint_methods=["typo"])


def test_excluded_sections_coherence_defaults(settings) -> None:
    """Default survey/features excluded_sections stay in sync (fixture uses TOML defaults)."""
    assert settings.features.excluded_sections == settings.survey.excluded_sections


def test_excluded_sections_coherence_explicit_match() -> None:
    sections = frozenset({"sponsored", "partner-content"})
    ForensicsSettings(
        authors=[_minimal_author()],
        survey=SurveyConfig(excluded_sections=sections),
        features=FeaturesConfig(excluded_sections=sections),
    )


def test_excluded_sections_survey_wins_over_features_mismatch() -> None:
    """Survey is canonical; features.excluded_sections is overwritten to match."""
    settings = ForensicsSettings(
        authors=[_minimal_author()],
        survey=SurveyConfig(excluded_sections=frozenset({"crosspost"})),
        features=FeaturesConfig(excluded_sections=frozenset({"sponsored"})),
    )
    assert settings.survey.excluded_sections == frozenset({"crosspost"})
    assert settings.features.excluded_sections == settings.survey.excluded_sections
