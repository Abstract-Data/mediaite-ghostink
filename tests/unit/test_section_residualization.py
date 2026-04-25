"""Section residualization helper tests."""

from __future__ import annotations

import polars as pl

from forensics.analysis.section_residualization import residualize_features_by_section


def test_residualize_features_by_section_uses_url_sections() -> None:
    df = pl.DataFrame(
        {
            "url": [
                "https://www.mediaite.com/news/a/",
                "https://www.mediaite.com/news/b/",
                "https://www.mediaite.com/tv/c/",
                "https://www.mediaite.com/tv/d/",
            ],
            "ttr": [1.0, 3.0, 10.0, 12.0],
        }
    )

    result = residualize_features_by_section(
        df,
        feature_columns=["ttr"],
        min_articles_per_section=2,
    )

    assert result.get_column("section").to_list() == ["news", "news", "tv", "tv"]
    assert result.get_column("ttr").to_list() == [5.5, 7.5, 5.5, 7.5]


def test_residualize_features_by_section_skips_without_enough_sections() -> None:
    df = pl.DataFrame(
        {
            "section": ["news", "news", "tv"],
            "ttr": [1.0, 3.0, 10.0],
        }
    )

    result = residualize_features_by_section(
        df,
        feature_columns=["ttr"],
        min_articles_per_section=2,
    )

    assert result.get_column("ttr").to_list() == [1.0, 3.0, 10.0]
