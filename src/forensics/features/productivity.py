"""Productivity-style temporal features."""

from __future__ import annotations

from datetime import datetime, timedelta


def extract_productivity_features(
    published_date: datetime,
    word_count: int,
    prior_chronological: list[tuple[datetime, int]],
) -> dict[str, float | int]:
    """
    Temporal burst proxies for one article.

    ``prior_chronological`` — same-author articles strictly **before** this one,
    sorted by ``published_date`` ascending. Each tuple is ``(published_date, word_count)``.

    Rolling counts use the closed interval ``[published_date - N days, published_date]``,
    including the current article.
    """
    timeline = [*prior_chronological, (published_date, word_count)]

    if len(prior_chronological) == 0:
        days_since = 0.0
    else:
        prev = prior_chronological[-1][0]
        days_since = float((published_date - prev).total_seconds() / 86400.0)

    def count_in_window(days: int) -> int:
        start = published_date - timedelta(days=days)
        return sum(1 for d, _ in timeline if start <= d <= published_date)

    return {
        "days_since_last_article": days_since,
        "rolling_7d_count": count_in_window(7),
        "rolling_30d_count": count_in_window(30),
    }
