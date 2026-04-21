"""Feature extraction pipeline wiring (Phase 4)."""

from __future__ import annotations

import json
import logging
import shutil
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from forensics.config import get_project_root
from forensics.config.settings import ForensicsSettings
from forensics.features import (
    content,
    embeddings,
    lexical,
    pos_patterns,
    productivity,
    readability,
    structural,
)
from forensics.models.article import Article
from forensics.models.features import EmbeddingRecord, FeatureVector
from forensics.storage.parquet import write_embeddings_manifest, write_features
from forensics.storage.repository import Repository, init_db

logger = logging.getLogger(__name__)


def _recent_peer_texts(
    articles_chrono: list[Article],
    idx: int,
    days: int,
) -> list[str]:
    """Clean texts of same-author articles in ``[cur-days, cur)`` (exclude current index)."""
    cur = articles_chrono[idx].published_date
    start = cur - timedelta(days=days)
    out: list[str] = []
    for j in range(idx):
        a = articles_chrono[j]
        if start <= a.published_date < cur:
            out.append(a.clean_text)
    return out


def _archive_embeddings_if_mismatch(embed_root: Path, model_name: str, model_version: str) -> None:
    manifest = embed_root / "manifest.jsonl"
    if not manifest.is_file():
        return
    try:
        first = json.loads(manifest.read_text(encoding="utf-8").splitlines()[0])
    except (json.JSONDecodeError, IndexError, OSError):
        return
    if first.get("model_name") == model_name and first.get("model_version") == model_version:
        return
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = embed_root.parent / f"embeddings_archive_{ts}"
    logger.warning(
        "Embedding model mismatch (manifest=%s/%s, config=%s/%s). Archiving to %s",
        first.get("model_name"),
        first.get("model_version"),
        model_name,
        model_version,
        dest,
    )
    if embed_root.exists():
        shutil.move(str(embed_root), str(dest))
    embed_root.mkdir(parents=True, exist_ok=True)


def _resolve_project_root(db_path: Path, project_root: Path | None) -> Path:
    if project_root is not None:
        return project_root
    if db_path.name == "articles.db" and db_path.parent.name == "data":
        return db_path.parent.parent
    return get_project_root()


def extract_all_features(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    author_slug: str | None = None,
    skip_embeddings: bool = False,
    skip_probability: bool = False,
    probability_no_binoculars: bool = False,
    project_root: Path | None = None,
) -> int:
    """
    Run feature extraction for all eligible articles (optionally one author).

    Writes ``data/features/{slug}.parquet`` and ``data/embeddings/{slug}/{id}.npy``.
    """
    init_db(db_path)
    root = _resolve_project_root(db_path, project_root)
    data_dir = root / "data"
    features_dir = data_dir / "features"
    embed_root = data_dir / "embeddings"
    features_dir.mkdir(parents=True, exist_ok=True)
    embed_root.mkdir(parents=True, exist_ok=True)

    model_name = settings.analysis.embedding_model
    model_version = settings.analysis.embedding_model_version
    if not skip_embeddings:
        _archive_embeddings_if_mismatch(embed_root, model_name, model_version)

    repo = Repository(db_path)
    author_id_filter: str | None = None
    if author_slug:
        au = repo.get_author_by_slug(author_slug)
        if au is None:
            msg = f"Unknown author slug: {author_slug}"
            raise ValueError(msg)
        author_id_filter = au.id

    articles = repo.list_articles_for_extraction(author_id=author_id_filter)
    if not articles:
        logger.info("No articles eligible for feature extraction.")
        return 0

    by_author: dict[str, list[Article]] = defaultdict(list)
    for a in articles:
        by_author[a.author_id].append(a)
    for aid in by_author:
        by_author[aid].sort(key=lambda x: x.published_date)

    try:
        import spacy

        nlp = spacy.load("en_core_web_md")
    except OSError as exc:
        logger.error("spaCy model en_core_web_md is required: %s", exc)
        raise

    processed = 0
    manifest_records: list[EmbeddingRecord] = []

    for author_id, seq in by_author.items():
        author = repo.get_author(author_id)
        slug = author.slug if author else author_id
        author_name = author.name if author else author_id
        out_features: list[FeatureVector] = []
        embed_dir_author = embed_root / slug
        if not skip_embeddings:
            embed_dir_author.mkdir(parents=True, exist_ok=True)

        for idx, article in enumerate(seq):
            if processed and processed % 50 == 0:
                logger.info(
                    "Extracting features: %d articles (%s)",
                    processed,
                    author_name,
                )
            try:
                doc = nlp(article.clean_text)
                lex = lexical.extract_lexical_features(article.clean_text, doc)
                pos = pos_patterns.extract_pos_pattern_features(doc)
                struct = structural.extract_structural_features(article.clean_text, doc)
                recent30 = _recent_peer_texts(seq, idx, 30)
                recent90 = _recent_peer_texts(seq, idx, 90)
                cont = content.extract_content_features(
                    article.clean_text,
                    doc,
                    recent30,
                    recent90,
                )
                prior_tuples = [(a.published_date, a.word_count) for a in seq[:idx]]
                prod = productivity.extract_productivity_features(
                    article.published_date,
                    article.word_count,
                    prior_tuples,
                )
                read = readability.extract_readability_features(article.clean_text)

                fv = FeatureVector(
                    article_id=article.id,
                    author_id=article.author_id,
                    timestamp=article.published_date,
                    **lex,
                    **struct,
                    **cont,
                    **prod,
                    **read,
                    pos_bigram_top30=pos["pos_bigram_top30"],
                    clause_initial_entropy=pos["clause_initial_entropy"],
                    clause_initial_top10=pos["clause_initial_top10"],
                    dep_depth_mean=pos["dep_depth_mean"],
                    dep_depth_std=pos["dep_depth_std"],
                    dep_depth_max=pos["dep_depth_max"],
                )
                out_features.append(fv)

                if not skip_embeddings:
                    vec = embeddings.compute_embedding(article.clean_text, model_name)
                    rel_path = Path("data") / "embeddings" / slug / f"{article.id}.npy"
                    abs_path = root / rel_path
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(abs_path, vec)
                    manifest_records.append(
                        EmbeddingRecord(
                            article_id=article.id,
                            author_id=article.author_id,
                            timestamp=article.published_date,
                            model_name=model_name,
                            model_version=model_version,
                            embedding_path=str(rel_path),
                            embedding_dim=int(vec.shape[0]),
                        )
                    )
                processed += 1
            except Exception:
                logger.exception("Feature extraction failed for article %s", article.id)

        if out_features:
            write_features(out_features, features_dir / f"{slug}.parquet")

    if not skip_embeddings:
        write_embeddings_manifest(manifest_records, embed_root / "manifest.jsonl")

    logger.info("Feature extraction finished: %d article(s) processed.", processed)

    if not skip_probability:
        from forensics.features.probability_pipeline import (
            extract_probability_features,
            maybe_log_probability_hint,
            probability_stack_available,
        )

        if probability_stack_available():
            try:
                extract_probability_features(
                    db_path,
                    settings,
                    author_slug=author_slug,
                    no_binoculars=probability_no_binoculars,
                    project_root=root,
                )
            except Exception:
                logger.exception("Probability extraction failed after feature pass")
        else:
            maybe_log_probability_hint()

    return processed
