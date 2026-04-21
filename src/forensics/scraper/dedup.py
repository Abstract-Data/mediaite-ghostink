"""Deduplication helpers for scraped documents."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from forensics.models.article import Article
from forensics.storage.repository import Repository, init_db
from forensics.utils.hashing import simhash, simhash_hamming

logger = logging.getLogger(__name__)

_NEAR_DUP_HAMMING = 3


def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _union(parent: list[int], i: int, j: int) -> None:
    ri, rj = _find(parent, i), _find(parent, j)
    if ri != rj:
        parent[rj] = ri


def deduplicate_articles(db_path: Path, *, hamming_threshold: int = _NEAR_DUP_HAMMING) -> list[str]:
    """
    Mark near-duplicate articles (simhash Hamming distance <= threshold).

    Uses union-find over the similarity graph, then keeps the earliest ``published_date``
    per component. Returns IDs that are marked duplicate (excluding canonical rows).
    """
    init_db(db_path)
    repo = Repository(db_path)
    pool: list[Article] = [
        a
        for a in repo.get_all_articles()
        if a.clean_text and not a.clean_text.startswith("[REDIRECT:")
    ]
    if not pool:
        return []

    indices = list(range(len(pool)))
    parent = list(indices)
    fingerprints = [simhash(a.clean_text) for a in pool]

    for i in indices:
        for j in range(i + 1, len(pool)):
            if simhash_hamming(fingerprints[i], fingerprints[j]) <= hamming_threshold:
                _union(parent, i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in indices:
        groups[_find(parent, i)].append(i)

    duplicate_ids: list[str] = []
    for members in groups.values():
        canonical_i = min(members, key=lambda i: pool[i].published_date)
        can = pool[canonical_i]
        for i in members:
            art = pool[i]
            art.is_duplicate = i != canonical_i
            repo.upsert_article(art)
            if art.is_duplicate:
                logger.info(
                    "DUPLICATE: '%s' (%s) ≈ '%s' (%s)",
                    art.title,
                    art.published_date.date().isoformat(),
                    can.title,
                    can.published_date.date().isoformat(),
                )
                duplicate_ids.append(art.id)

    return duplicate_ids
