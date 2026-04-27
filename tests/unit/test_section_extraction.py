"""Phase 15 Step J1 — section column derivation from article URL.

Tests the regex helper :func:`forensics.utils.url.section_from_url` plus the
end-to-end wiring through the assembler / parquet writer.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from forensics.features.assembler import build_feature_vector_from_extractors
from forensics.models.article import Article
from forensics.models.features import FeatureVector
from forensics.storage.parquet import scan_features, write_features
from forensics.utils.url import section_from_url

# --- Regression-pin: real-shaped Mediaite URLs locked to expected sections. -----
# If a future URL-shape change drops one of these, J1's WARNING log line fires
# in production AND this list flags the regression in CI.
_REGRESSION_URLS: tuple[tuple[str, str], ...] = (
    ("https://www.mediaite.com/2024/05/15/year-segment-story/", "unknown"),
    ("https://www.mediaite.com/politics/some-slug-here/", "politics"),
    ("https://mediaite.com/media/breaking-news/", "media"),
    ("https://www.mediaite.com/opinion/the-take/", "opinion"),
    ("https://www.mediaite.com/analysis/why-it-matters/", "analysis"),
    ("https://www.mediaite.com/sponsored/branded-piece/", "sponsored"),
    ("https://www.mediaite.com/partner-content/co-marketing/", "partner-content"),
    ("https://www.mediaite.com/crosspost/syndicated-article/", "crosspost"),
    ("https://www.mediaite.com/columnists/regular-byline/", "columnists"),
    ("https://www.mediaite.com/premium/exclusive-story/", "premium"),
    ("https://www.mediaite.com/tv/cable-news-clip/", "tv"),
    ("http://www.mediaite.com/politics/lower-case-protocol/", "politics"),
    ("HTTPS://WWW.MEDIAITE.COM/Media/Mixed-Case/", "media"),
)


def test_section_from_url_happy_path_with_www() -> None:
    assert section_from_url("https://www.mediaite.com/politics/some-slug/") == "politics"


def test_section_from_url_happy_path_without_www() -> None:
    assert section_from_url("https://mediaite.com/media/some-slug/") == "media"


def test_section_from_url_handles_empty_and_none() -> None:
    """Empty or None input must NOT raise; both yield ``"unknown"``."""
    assert section_from_url("") == "unknown"
    assert section_from_url(None) == "unknown"  # type: ignore[arg-type]


def test_section_from_url_unknown_for_non_matching() -> None:
    # Off-domain, no path segment, query-only — all fall through to "unknown".
    assert section_from_url("https://www.example.com/politics/foo/") == "unknown"
    assert section_from_url("https://www.mediaite.com/") == "unknown"
    assert section_from_url("not a url") == "unknown"


def test_section_from_url_lowercases_section() -> None:
    """The regex is case-insensitive; the returned section is always lower-case."""
    assert section_from_url("HTTPS://WWW.MEDIAITE.COM/POLITICS/foo/") == "politics"


@pytest.mark.parametrize(("url", "expected"), _REGRESSION_URLS)
def test_section_from_url_regression_pins(url: str, expected: str) -> None:
    """Lock real-shaped Mediaite URLs to their expected sections (D-07 year-only path)."""
    assert section_from_url(url) == expected


# ---------------------------------------------------------------------------
# Assembler / parquet integration
# ---------------------------------------------------------------------------


def _empty_extractor_dicts() -> dict[str, dict[str, object]]:
    """Build per-family extractor dicts with default scalars (one place to maintain)."""
    return {
        "lex": {},
        "struct": {},
        "cont": {},
        "prod": {},
        "read": {},
        "pos": {
            "pos_bigram_top30": {},
            "clause_initial_entropy": 0.0,
            "clause_initial_top10": {},
            "dep_depth_mean": 0.0,
            "dep_depth_std": 0.0,
            "dep_depth_max": 0.0,
        },
    }


def _make_article(url: str) -> Article:
    return Article(
        id="art-1",
        author_id="auth-1",
        url=url,
        title="t",
        published_date=datetime(2024, 6, 1, tzinfo=UTC),
        clean_text="placeholder body",
        word_count=2,
    )


def test_assembler_populates_section_from_article_url() -> None:
    article = _make_article("https://www.mediaite.com/politics/the-vote/")
    fv = build_feature_vector_from_extractors(article, **_empty_extractor_dicts())
    assert fv.section == "politics"


def test_assembler_warns_on_unknown_section(caplog: pytest.LogCaptureFixture) -> None:
    """Off-section URLs surface a WARNING line per the J1 spec."""
    # Use a non-matching path so the regex falls through and the WARN fires.
    article = _make_article("https://www.mediaite.com/")
    with caplog.at_level(logging.WARNING, logger="forensics.features.assembler"):
        fv = build_feature_vector_from_extractors(article, **_empty_extractor_dicts())
    assert fv.section == "unknown"
    assert any("section_from_url returned 'unknown'" in rec.message for rec in caplog.records), (
        "expected a WARNING when section falls through to 'unknown'"
    )


def test_write_features_emits_section_column(tmp_path: Path) -> None:
    """Parquet schema written by the feature pipeline must include ``section: pl.Utf8``."""
    fv = FeatureVector(
        article_id="x1",
        author_id="auth-x",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        section="politics",
    )
    path = tmp_path / "features.parquet"
    write_features([fv], path)

    df = scan_features(path).collect()
    assert "section" in df.columns
    assert df.schema["section"] == pl.Utf8
    assert df.row(0, named=True)["section"] == "politics"


def test_feature_vector_default_section_is_unknown() -> None:
    """Legacy callers that omit ``section`` get a safe ``"unknown"`` default."""
    fv = FeatureVector(
        article_id="x",
        author_id="a",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert fv.section == "unknown"


# ---------------------------------------------------------------------------
# Migration script verification — legacy v1 parquet → v2 with section column
# ---------------------------------------------------------------------------


def test_migration_derives_section_from_legacy_url_column(tmp_path: Path) -> None:
    """The Phase-15 migration must populate ``section`` via :func:`section_from_url`.

    Pre-J1 parquets do not have ``section``; if they carry a ``url`` column the
    migration applies the same regex helper to back-fill it.
    """
    import importlib

    mig = importlib.import_module("forensics.storage.migrations.002_feature_parquet_section")

    legacy = tmp_path / "legacy.parquet"
    pl.DataFrame(
        {
            "article_id": ["a1", "a2", "a3"],
            "author_id": ["u", "u", "u"],
            "timestamp": [
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 2, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
            ],
            "url": [
                "https://www.mediaite.com/politics/foo/",
                "https://mediaite.com/media/bar/",
                "https://www.example.com/no-match/",
            ],
        }
    ).write_parquet(legacy)

    migrated = mig.migrate_feature_parquet(legacy)
    assert migrated is True

    df = pl.read_parquet(legacy)
    assert "section" in df.columns
    assert df.schema["section"] == pl.Utf8
    assert df["section"].to_list() == ["politics", "media", "unknown"]
