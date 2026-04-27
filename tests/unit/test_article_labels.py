"""M-17 optional label contract (precision/recall scaffolding)."""

from __future__ import annotations

from datetime import UTC, datetime

from forensics.models.labels import ArticleLabel


def test_article_label_round_trip() -> None:
    row = ArticleLabel(
        article_id="art-1",
        author_slug="fixture-author",
        labeled_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        judgment="human",
        notes="spot check",
    )
    payload = row.model_dump(mode="json")
    restored = ArticleLabel.model_validate(payload)
    assert restored == row
