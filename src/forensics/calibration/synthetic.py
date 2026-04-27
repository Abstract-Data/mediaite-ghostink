"""Spliced and negative-control corpora (deterministic; no filesystem; inputs unmutated)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from forensics.models.article import Article

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyntheticCorpus:
    """A synthetic corpus with known ground truth for calibration.

    ``splice_date`` is ``None`` for negative controls — in that case
    ``synthetic_articles`` is empty and ``combined_articles`` equals
    ``original_articles``.
    """

    author_slug: str
    splice_date: date | None
    original_articles: list[Article]
    synthetic_articles: list[Article]
    combined_articles: list[Article]


def _sorted_by_date(articles: list[Article]) -> list[Article]:
    return sorted(articles, key=lambda a: a.published_date)


def build_spliced_corpus(
    author_slug: str,
    articles: list[Article],
    splice_date: date,
    ai_articles: list[Article],
) -> SyntheticCorpus:
    """Replace articles published strictly after ``splice_date`` with AI content.

    The original article's metadata (``id``, ``url``, ``title``, ``published_date``,
    ``author_id``) is preserved so downstream joins still work — only the textual
    body is swapped. The replacement article is tagged ``metadata.synthetic=True``
    and references the original id via ``metadata.original_id``.

    If ``ai_articles`` is shorter than the number of post-splice originals, the
    remaining post-splice articles are kept unchanged (best-effort splice).

    Args:
        author_slug: Author identifier (used for reporting; not persisted on
            individual articles).
        articles: The author's real archive. Copies are taken — the input list
            is not mutated.
        splice_date: Articles whose ``published_date.date() > splice_date`` are
            replaced with AI-generated text.
        ai_articles: AI-generated articles (e.g. from the Phase 10 baseline)
            whose ``clean_text`` is substituted in.

    Returns:
        A :class:`SyntheticCorpus` describing the known ground truth.
    """
    ordered = _sorted_by_date(articles)
    pre_splice = [a for a in ordered if a.published_date.date() <= splice_date]
    post_splice_originals = [a for a in ordered if a.published_date.date() > splice_date]

    combined: list[Article] = list(pre_splice)
    used_ai: list[Article] = []
    for i, orig in enumerate(post_splice_originals):
        if i < len(ai_articles):
            ai_src = ai_articles[i]
            replacement = orig.model_copy(
                update={
                    "id": f"synthetic_{orig.id}",
                    "clean_text": ai_src.clean_text,
                    "word_count": len(ai_src.clean_text.split()),
                    "metadata": {
                        **(orig.metadata or {}),
                        "synthetic": True,
                        "original_id": orig.id,
                    },
                    "content_hash": "",
                }
            )
            combined.append(replacement)
            used_ai.append(ai_src)
        else:
            combined.append(orig)

    logger.info(
        "calibration.synthetic: spliced %s at %s — %d pre, %d post (%d replaced)",
        author_slug,
        splice_date.isoformat(),
        len(pre_splice),
        len(post_splice_originals),
        len(used_ai),
    )

    return SyntheticCorpus(
        author_slug=author_slug,
        splice_date=splice_date,
        original_articles=list(ordered),
        synthetic_articles=used_ai,
        combined_articles=combined,
    )


def build_negative_control(
    author_slug: str,
    articles: list[Article],
) -> SyntheticCorpus:
    """Build an unmodified corpus as a negative control.

    Returns a :class:`SyntheticCorpus` with ``splice_date=None``. The detector
    should **not** flag this corpus.
    """
    ordered = _sorted_by_date(articles)
    return SyntheticCorpus(
        author_slug=author_slug,
        splice_date=None,
        original_articles=list(ordered),
        synthetic_articles=[],
        combined_articles=list(ordered),
    )
