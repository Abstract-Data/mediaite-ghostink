"""Feature extraction pipeline wiring."""

from __future__ import annotations

import logging
import shutil
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

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
from forensics.features.assembler import build_feature_vector_from_extractors
from forensics.models.article import Article
from forensics.models.features import EmbeddingRecord, FeatureVector
from forensics.paths import AnalysisArtifactPaths, resolve_author_rows
from forensics.storage.json_io import ensure_dir
from forensics.storage.parquet import (
    AUTHOR_EMBEDDING_BATCH_BASENAME,
    read_embeddings_manifest,
    write_author_embedding_batch,
    write_embeddings_manifest,
    write_features,
)
from forensics.storage.repository import Repository
from forensics.utils.model_cache import KeyedModelCache
from forensics.utils.url import section_from_url

logger = logging.getLogger(__name__)

__all__ = [
    "clear_spacy_model_cache",
    "extract_all_features",
]

# Recoverable failures from extractors, numpy I/O, and sentence-transformers encode.
# MemoryError and RecursionError are intentionally excluded — they indicate
# process-level failure and should halt the pipeline rather than be counted as
# per-article extraction errors.
_RECOVERABLE_EXTRACTION_ERRORS: tuple[type[Exception], ...] = (
    ArithmeticError,
    AttributeError,
    LookupError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


@dataclass(slots=True)
class _AuthorBatchResult:
    """Aggregated output of a single author's feature-extraction batch."""

    features: list[FeatureVector] = field(default_factory=list)
    embedding_records: list[EmbeddingRecord] = field(default_factory=list)
    processed: int = 0
    failed: int = 0


@dataclass(slots=True)
class _PeerDequeWindows:
    """C-12 — sliding 90-day deque for peer texts (O(n) per author vs O(n²) rescans)."""

    _q: deque[tuple[datetime, str]] = field(default_factory=deque)

    def peers_before(self, article: Article) -> tuple[list[str], list[str]]:
        """Return ``(recent30, recent90)`` for ``article`` without mutating history."""
        cur = article.published_date
        start90 = cur - timedelta(days=90)
        while self._q and self._q[0][0] < start90:
            self._q.popleft()
        start30 = cur - timedelta(days=30)
        recent30 = [t for dt, t in self._q if dt >= start30]
        recent90 = [t for _dt, t in self._q]
        return recent30, recent90

    def record(self, article: Article) -> None:
        """Append ``article`` after successful feature extraction for this index."""
        self._q.append((article.published_date, article.clean_text))


def _archive_embeddings_if_mismatch(
    embed_root: Path,
    model_name: str,
    model_version: str,
    model_revision: str,
) -> None:
    """P-05 — scan the full embedding manifest; archive on any model mismatch or mixed tuples."""
    manifest = embed_root / "manifest.jsonl"
    if not manifest.is_file():
        return
    try:
        records = read_embeddings_manifest(manifest)
    except OSError:
        return
    if not records:
        return
    expected = (model_name, model_version, str(model_revision or ""))
    triples = {(r.model_name, r.model_version, str(r.model_revision or "")) for r in records}
    if len(triples) > 1:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        dest = embed_root.parent / f"embeddings_archive_{ts}"
        logger.warning(
            "Embedding manifest mixes multiple model tuples %s; archiving to %s",
            triples,
            dest,
        )
        if embed_root.exists():
            shutil.move(str(embed_root), str(dest))
        ensure_dir(embed_root)
        return
    got = triples.pop()
    if got == expected:
        return
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = embed_root.parent / f"embeddings_archive_{ts}"
    logger.warning(
        "Embedding model mismatch (manifest=%s/%s@%s, config=%s/%s@%s). Archiving to %s",
        got[0],
        got[1],
        got[2] or "(none)",
        model_name,
        model_version,
        model_revision,
        dest,
    )
    if embed_root.exists():
        shutil.move(str(embed_root), str(dest))
    ensure_dir(embed_root)


def _resolve_project_root(db_path: Path, project_root: Path | None) -> Path:
    if project_root is not None:
        return project_root
    if db_path.name == "articles.db" and db_path.parent.name == "data":
        return db_path.parent.parent
    return get_project_root()


_SPACY_MODEL_CACHE = KeyedModelCache()


def _load_spacy_model(model_name: str = "en_core_web_md") -> Any:
    """Load the requested spaCy pipeline (or return a cached handle) or raise."""

    def _load() -> Any:
        try:
            import spacy

            logger.info("Loading spaCy model: %s", model_name)
            return spacy.load(model_name)
        except OSError as exc:
            logger.error("spaCy model %s is required: %s", model_name, exc)
            raise

    return _SPACY_MODEL_CACHE.get_or_load(model_name, _load)


def clear_spacy_model_cache() -> None:
    """Drop cached spaCy pipelines (tests)."""
    _SPACY_MODEL_CACHE.clear()


def _extract_features_for_article(
    article: Article,
    idx: int,
    seq: list[Article],
    nlp: Any,
    settings: ForensicsSettings,
    doc: Any | None = None,
    *,
    peer_windows: _PeerDequeWindows,
) -> FeatureVector:
    """Compute one :class:`FeatureVector` (extractors + assembler; no I/O).

    If ``doc`` is omitted, parses ``article.clean_text`` with ``nlp``; if set,
    uses the caller's pipelined doc (e.g. ``nlp.pipe``).
    """
    if doc is None:
        doc = nlp(article.clean_text)
    lex = lexical.extract_lexical_features(article.clean_text, doc)
    pos = pos_patterns.extract_pos_pattern_features(doc)
    struct = structural.extract_structural_features(article.clean_text, doc)
    recent30, recent90 = peer_windows.peers_before(article)
    cont = content.extract_content_features(
        article.clean_text,
        doc,
        recent30,
        recent90,
        analysis=settings.analysis,
    )
    prior_tuples = [(a.published_date, a.word_count) for a in seq[:idx]]
    prod = productivity.extract_productivity_features(
        article.published_date,
        article.word_count,
        prior_tuples,
    )
    read = readability.extract_readability_features(article.clean_text)
    return build_feature_vector_from_extractors(
        article,
        lex=lex,
        struct=struct,
        cont=cont,
        prod=prod,
        read=read,
        pos=pos,
    )


def _write_author_embedding_artifacts(
    *,
    author_id: str,
    slug: str,
    paths: AnalysisArtifactPaths,
    embed_batch: list[tuple[str, datetime, np.ndarray]],
    model_name: str,
    model_version: str,
    model_revision: str,
) -> list[EmbeddingRecord]:
    """Persist the NPZ matrix for one author and build the manifest records."""
    abs_batch = paths.embeddings_dir / slug / AUTHOR_EMBEDDING_BATCH_BASENAME
    rel_batch = abs_batch.relative_to(paths.project_root)
    # Parent dir created inside write_author_embedding_batch (RF-DRY-004).
    mat = np.stack([row[2] for row in embed_batch], axis=0)
    write_author_embedding_batch(
        abs_batch,
        [row[0] for row in embed_batch],
        mat,
    )
    return [
        EmbeddingRecord(
            article_id=aid,
            author_id=author_id,
            timestamp=ts,
            model_name=model_name,
            model_version=model_version,
            model_revision=model_revision,
            embedding_path=str(rel_batch),
            embedding_dim=int(vec.shape[0]),
        )
        for aid, ts, vec in embed_batch
    ]


def _process_author_batch(
    author_id: str,
    articles_seq: list[Article],
    nlp: Any,
    settings: ForensicsSettings,
    *,
    slug: str,
    author_name: str,
    paths: AnalysisArtifactPaths,
    skip_embeddings: bool,
    progress: Progress | None,
    processed_before_batch: int,
) -> _AuthorBatchResult:
    """Extract features (and optional embeddings) for one author's article list."""
    model_name = settings.analysis.embedding_model
    model_version = settings.analysis.embedding_model_version
    model_revision = settings.analysis.embedding_model_revision
    max_fail_ratio = settings.analysis.feature_extraction_max_failure_ratio

    result = _AuthorBatchResult()
    embed_batch: list[tuple[str, datetime, np.ndarray]] = []

    batch = len(articles_seq)
    batch_failed = 0
    task_id: int | None = None
    if progress is not None:
        task_id = progress.add_task(f"Extracting {author_name}", total=batch)

    # Pre-parse every article with nlp.pipe for ~1.5-2× throughput over per-article
    # nlp(text). n_process stays at 1 so this is safe to run inside a
    # ProcessPoolExecutor worker (author-level parallelism); spaCy's own fork-based
    # multiprocessing would deadlock when nested.
    texts = [a.clean_text for a in articles_seq]
    docs_iter = nlp.pipe(texts, batch_size=200, n_process=1)
    peer_windows = _PeerDequeWindows()

    for idx, (article, doc) in enumerate(zip(articles_seq, docs_iter, strict=True)):
        running_processed = processed_before_batch + result.processed
        if running_processed and running_processed % 50 == 0:
            logger.debug(
                "Extracting features: %d articles (%s)",
                running_processed,
                author_name,
            )
        try:
            fv = _extract_features_for_article(
                article,
                idx,
                articles_seq,
                nlp,
                settings,
                doc=doc,
                peer_windows=peer_windows,
            )
            result.features.append(fv)

            if not skip_embeddings:
                vec = embeddings.compute_embedding(article.clean_text, model_name, model_revision)
                embed_batch.append(
                    (
                        article.id,
                        article.published_date,
                        np.asarray(vec, dtype=np.float32),
                    )
                )
            result.processed += 1
        except _RECOVERABLE_EXTRACTION_ERRORS as exc:
            batch_failed += 1
            result.failed += 1
            logger.exception(
                "Feature extraction failed for article %s (%s: %s)",
                article.id,
                type(exc).__name__,
                exc,
            )
            if batch and (batch_failed / batch) > max_fail_ratio:
                msg = (
                    f"Feature extraction abort: >{max_fail_ratio:.0%} "
                    f"failures in author batch slug={slug} "
                    f"({batch_failed}/{batch})"
                )
                raise RuntimeError(msg) from exc
        finally:
            peer_windows.record(article)
            if progress is not None and task_id is not None:
                progress.update(task_id, advance=1)

    if not skip_embeddings and embed_batch:
        result.embedding_records = _write_author_embedding_artifacts(
            author_id=author_id,
            slug=slug,
            paths=paths,
            embed_batch=embed_batch,
            model_name=model_name,
            model_version=model_version,
            model_revision=model_revision,
        )

    return result


def _group_articles_by_author(articles: list[Article]) -> dict[str, list[Article]]:
    """Group articles by ``author_id``, sorting each group chronologically."""
    by_author: dict[str, list[Article]] = defaultdict(list)
    for a in articles:
        by_author[a.author_id].append(a)
    for aid in by_author:
        by_author[aid].sort(key=lambda x: x.published_date)
    return by_author


def _filter_excluded_sections(
    articles: list[Article],
    excluded: frozenset[str],
) -> list[Article]:
    """Drop articles whose URL-derived ``section`` is in ``excluded``.

    Logs DEBUG per dropped row; survey writes ``excluded_articles.csv`` for audits.
    """
    if not excluded:
        return articles
    kept: list[Article] = []
    dropped = 0
    for art in articles:
        section = section_from_url(str(art.url))
        if section in excluded:
            dropped += 1
            logger.debug(
                "feature extraction skipping article id=%s section=%s url=%s",
                art.id,
                section,
                art.url,
            )
            continue
        kept.append(art)
    if dropped:
        logger.info(
            "feature extraction: skipped %d article(s) in excluded sections (%s)",
            dropped,
            ",".join(sorted(excluded)),
        )
    return kept


def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        transient=False,
    )


def _run_author_batches(
    *,
    by_author: dict[str, list[Article]],
    repo: Repository,
    nlp: Any,
    settings: ForensicsSettings,
    paths: AnalysisArtifactPaths,
    skip_embeddings: bool,
    use_rich_progress: bool = True,
) -> tuple[int, int, list[EmbeddingRecord]]:
    """Iterate authors, delegate per-batch work, and persist per-author Parquet output."""
    processed = 0
    failed = 0
    manifest_records: list[EmbeddingRecord] = []
    progress = _make_progress() if use_rich_progress else None
    if progress is not None:
        progress.start()
    try:
        for author_id, seq in by_author.items():
            author = repo.get_author(author_id)
            slug = author.slug if author else author_id
            author_name = author.name if author else author_id
            batch_result = _process_author_batch(
                author_id,
                seq,
                nlp,
                settings,
                slug=slug,
                author_name=author_name,
                paths=paths,
                skip_embeddings=skip_embeddings,
                progress=progress,
                processed_before_batch=processed,
            )
            processed += batch_result.processed
            failed += batch_result.failed
            manifest_records.extend(batch_result.embedding_records)
            if batch_result.features:
                write_features(batch_result.features, paths.features_parquet(slug))
    finally:
        if progress is not None:
            progress.stop()
    return processed, failed, manifest_records


def extract_all_features(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    author_slug: str | None = None,
    skip_embeddings: bool = False,
    project_root: Path | None = None,
    show_rich_progress: bool = True,
) -> int:
    """Extract features for eligible articles (optional ``author_slug`` filter).

    Writes per-slug Parquet under ``paths.features_dir`` and embedding batches under
    ``paths.embeddings_dir``; analysis may still read legacy per-article ``.npy``.
    """
    root = _resolve_project_root(db_path, project_root)
    paths = AnalysisArtifactPaths.from_project(root, db_path)
    # Output dirs are created inside write_features / write_author_embedding_batch /
    # write_embeddings_manifest / _archive_embeddings_if_mismatch.

    if not skip_embeddings:
        _archive_embeddings_if_mismatch(
            paths.embeddings_dir,
            settings.analysis.embedding_model,
            settings.analysis.embedding_model_version,
            settings.analysis.embedding_model_revision,
        )

    with Repository(db_path) as repo:
        author_rows = resolve_author_rows(repo, settings, author_slug=author_slug)
        author_id_filter = author_rows[0].id if (author_slug and author_rows) else None
        articles = repo.list_articles_for_extraction(author_id=author_id_filter)
        if not articles:
            logger.info("No articles eligible for feature extraction.")
            return 0

        articles = _filter_excluded_sections(articles, settings.features.excluded_sections)
        if not articles:
            logger.info("No articles eligible for feature extraction after section exclusion.")
            return 0

        by_author = _group_articles_by_author(articles)
        nlp = _load_spacy_model(settings.spacy_model)
        processed, failed, manifest_records = _run_author_batches(
            by_author=by_author,
            repo=repo,
            nlp=nlp,
            settings=settings,
            paths=paths,
            skip_embeddings=skip_embeddings,
            use_rich_progress=show_rich_progress,
        )
        if not skip_embeddings:
            write_embeddings_manifest(manifest_records, paths.embeddings_dir / "manifest.jsonl")

    logger.info("Feature extraction finished: %d article(s) processed.", processed)
    if failed:
        logger.warning("Feature extraction: %d article(s) failed", failed)
    return processed
