"""Era classification tests for AI-marker change-points."""

from __future__ import annotations

from datetime import UTC, datetime

from forensics.analysis.era import classify_ai_marker_era
from forensics.models.analysis import ChangePoint


def _cp(feature: str, timestamp: datetime) -> ChangePoint:
    return ChangePoint(
        feature_name=feature,
        author_id="author-1",
        timestamp=timestamp,
        confidence=0.95,
        method="pelt",
        effect_size_cohens_d=0.8,
        direction="increase",
    )


def test_ai_marker_era_boundaries() -> None:
    result = classify_ai_marker_era(
        [
            _cp("ai_marker_frequency", datetime(2022, 10, 31, tzinfo=UTC)),
            _cp("ai_marker_frequency", datetime(2022, 11, 1, tzinfo=UTC)),
            _cp("ai_marker_frequency", datetime(2023, 3, 1, tzinfo=UTC)),
            _cp("ai_marker_frequency", datetime(2024, 1, 1, tzinfo=UTC)),
            _cp("ttr", datetime(2024, 1, 1, tzinfo=UTC)),
        ]
    )

    assert result.ai_marker_change_points_by_era == {
        "pre_nov_2022": 1,
        "nov_2022_to_mar_2023": 1,
        "mar_2023_to_dec_2023": 1,
        "post_dec_2023": 1,
    }
    assert result.total_ai_marker_change_points == 4
    assert result.dominant_era == "pre_nov_2022"


def test_ai_marker_era_empty_when_no_marker_events() -> None:
    result = classify_ai_marker_era([_cp("ttr", datetime(2024, 1, 1, tzinfo=UTC))])

    assert result.total_ai_marker_change_points == 0
    assert result.dominant_era is None
