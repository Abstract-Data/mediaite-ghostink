"""Aggregate style hints for mimicry prompts (no verbatim author text)."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from forensics.storage.repository import Repository, init_db

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def author_style_context(author_slug: str, db_path: Path) -> dict[str, str]:
    """Summary stats from baseline-period articles only (``baseline_end`` inclusive)."""
    init_db(db_path)
    repo = Repository(db_path)
    author = repo.get_author_by_slug(author_slug)
    if author is None:
        msg = f"Unknown author slug: {author_slug}"
        raise ValueError(msg)
    arts = repo.list_articles_for_extraction(author_id=author.id)
    baseline_end = author.baseline_end
    baseline = [a for a in arts if a.published_date.date() <= baseline_end]
    if not baseline:
        baseline = arts

    sent_lengths: list[float] = []
    for a in baseline[:400]:
        parts = [p.strip() for p in _SENT_SPLIT.split(a.clean_text) if p.strip()]
        if not parts:
            continue
        sent_lengths.append(a.word_count / max(len(parts), 1))
    avg_sent = int(np.median(sent_lengths)) if sent_lengths else 18

    return {
        "outlet_name": author.outlet or "political news site",
        "topic_area": "national politics, media, and Washington news cycles",
        "author_avg_sentence_length": str(max(8, min(40, avg_sent))),
        "author_tone_description": "analytical, deadline-driven, and opinion-forward",
        "author_structure_notes": (
            "inverted-pyramid lede, supporting quotes or paraphrase, closing framing paragraph"
        ),
    }
