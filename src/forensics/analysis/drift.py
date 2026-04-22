"""Embedding drift analysis (Phase 6): monthly centroids, velocities, AI baseline."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial.distance import cosine

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.utils import resolve_author_rows
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import DriftScores
from forensics.storage.parquet import (
    EMBEDDING_BATCH_KEY_BYTES,
    EMBEDDING_BATCH_KEY_LENGTHS,
    EMBEDDING_BATCH_KEY_VECTORS,
    read_embeddings_manifest,
    unpack_article_ids_from_embedding_batch,
)
from forensics.storage.repository import Repository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ArticleEmbedding:
    """One article's semantic embedding with its publish time (drift pipeline input)."""

    published_at: datetime
    embedding: np.ndarray = field(repr=False)


def _load_embedding_row(
    abs_path: Path,
    article_id: str,
    batch_cache: dict[Path, tuple[np.ndarray, dict[str, int]]],
) -> np.ndarray | None:
    """Load one embedding row from a legacy ``.npy`` file or a per-author ``batch.npz``."""
    if not abs_path.is_file():
        return None
    if abs_path.suffix.lower() == ".npz":
        if abs_path not in batch_cache:
            try:
                z = np.load(abs_path, allow_pickle=False)
            except (OSError, ValueError) as exc:
                logger.warning("Could not read embedding batch %s: %s", abs_path, exc)
                return None
            keys = frozenset(z.files)
            if (
                EMBEDDING_BATCH_KEY_LENGTHS in keys
                and EMBEDDING_BATCH_KEY_BYTES in keys
                and EMBEDDING_BATCH_KEY_VECTORS in keys
            ):
                try:
                    ids_list = unpack_article_ids_from_embedding_batch(
                        z[EMBEDDING_BATCH_KEY_LENGTHS],
                        z[EMBEDDING_BATCH_KEY_BYTES],
                    )
                except ValueError as exc:
                    logger.warning("Malformed embedding batch %s: %s", abs_path, exc)
                    return None
                mat = np.asarray(z[EMBEDDING_BATCH_KEY_VECTORS], dtype=np.float32)
                if mat.ndim != 2 or mat.shape[0] != len(ids_list):
                    logger.warning(
                        "Malformed embedding batch (shape mismatch): %s", abs_path
                    )
                    return None
                id_map = {ids_list[i]: i for i in range(len(ids_list))}
            elif "article_ids" in keys and EMBEDDING_BATCH_KEY_VECTORS in keys:
                logger.warning(
                    "Legacy embedding batch %s uses pickled article_ids; "
                    "re-run feature extraction to rewrite the batch.",
                    abs_path,
                )
                return None
            else:
                logger.warning("Malformed embedding batch (missing keys): %s", abs_path)
                return None
            batch_cache[abs_path] = (mat, id_map)
        mat, id_map = batch_cache[abs_path]
        row = id_map.get(article_id)
        if row is None:
            logger.warning("Article %s not in embedding batch %s", article_id, abs_path)
            return None
        return np.asarray(mat[row], dtype=np.float32)
    try:
        return np.asarray(np.load(abs_path), dtype=np.float32).ravel()
    except (OSError, ValueError) as exc:
        logger.warning("Could not read embedding file %s: %s", abs_path, exc)
        return None


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def compute_monthly_centroids(
    article_embeddings: Sequence[ArticleEmbedding],
) -> list[tuple[str, np.ndarray]]:
    """Mean embedding vector per calendar month, sorted chronologically."""
    monthly: dict[str, list[np.ndarray]] = defaultdict(list)
    for row in article_embeddings:
        key = row.published_at.strftime("%Y-%m")
        monthly[key].append(np.asarray(row.embedding, dtype=np.float32))
    centroids: list[tuple[str, np.ndarray]] = []
    for month in sorted(monthly.keys()):
        vectors = np.stack(monthly[month], axis=0)
        centroid = vectors.mean(axis=0)
        centroids.append((month, centroid))
    return centroids


def track_centroid_velocity(centroids: list[tuple[str, np.ndarray]]) -> list[float]:
    """Cosine distance between consecutive monthly centroids (drift velocity)."""
    velocities: list[float] = []
    for i in range(1, len(centroids)):
        prev_v = np.asarray(centroids[i - 1][1], dtype=np.float64).ravel()
        cur_v = np.asarray(centroids[i][1], dtype=np.float64).ravel()
        d = float(cosine(prev_v, cur_v))
        if not np.isfinite(d):
            d = 0.0
        velocities.append(d)
    return velocities


def compute_baseline_similarity_curve(
    article_embeddings: Sequence[ArticleEmbedding],
    *,
    baseline_count: int = 20,
) -> list[tuple[datetime, float]]:
    """Cosine similarity to centroid of first ``baseline_count`` articles by publish time."""
    if not article_embeddings:
        return []
    ordered = sorted(article_embeddings, key=lambda r: r.published_at)
    n_base = max(1, min(baseline_count, len(ordered)))
    base_vecs = np.stack(
        [np.asarray(r.embedding, dtype=np.float64) for r in ordered[:n_base]], axis=0
    )
    baseline_centroid = base_vecs.mean(axis=0)
    curve: list[tuple[datetime, float]] = []
    for row in ordered:
        sim = _cosine_similarity(
            np.asarray(row.embedding, dtype=np.float64), baseline_centroid
        )
        curve.append((row.published_at, sim))
    return curve


def _pairwise_mean_cosine_distance(vecs: list[np.ndarray]) -> float:
    dists: list[float] = []
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            d = float(cosine(vecs[i].ravel(), vecs[j].ravel()))
            if np.isfinite(d):
                dists.append(d)
    return float(np.mean(dists)) if dists else 0.0


def _mean_cosine_to_centroid(vecs: list[np.ndarray]) -> float:
    stacked = np.stack([v.ravel() for v in vecs], axis=0)
    centroid = stacked.mean(axis=0)
    dists_c: list[float] = []
    for v in vecs:
        d = float(cosine(v.ravel(), centroid))
        if np.isfinite(d):
            dists_c.append(d)
    return float(np.mean(dists_c)) if dists_c else 0.0


def compute_intra_period_variance(
    article_embeddings: Sequence[ArticleEmbedding],
    *,
    period: str = "month",
    max_pairwise: int = 20,
) -> list[tuple[str, float]]:
    """Dispersion within each calendar month.

    For small buckets (``<= max_pairwise``), use mean pairwise cosine distance.
    For larger buckets, use mean distance to the monthly centroid (O(k) vs O(k²)).
    """
    if period != "month":
        msg = f"Unsupported period: {period!r} (only 'month' is implemented)"
        raise ValueError(msg)
    buckets: dict[str, list[np.ndarray]] = defaultdict(list)
    for row in article_embeddings:
        buckets[row.published_at.strftime("%Y-%m")].append(
            np.asarray(row.embedding, dtype=np.float64)
        )
    out: list[tuple[str, float]] = []
    for key in sorted(buckets.keys()):
        vecs = buckets[key]
        if len(vecs) < 2:
            out.append((key, 0.0))
            continue
        if len(vecs) <= max_pairwise:
            out.append((key, _pairwise_mean_cosine_distance(vecs)))
            continue
        out.append((key, _mean_cosine_to_centroid(vecs)))
    return out


def compute_ai_convergence(
    author_monthly_centroids: list[tuple[str, np.ndarray]],
    ai_baseline_embeddings: Sequence[np.ndarray],
) -> list[tuple[str, float]]:
    """Monthly cosine similarity between author centroid and global AI baseline centroid."""
    if not author_monthly_centroids or not ai_baseline_embeddings:
        return []
    stacked = np.stack([np.asarray(e, dtype=np.float64) for e in ai_baseline_embeddings], axis=0)
    ai_centroid = stacked.mean(axis=0).ravel()
    convergence: list[tuple[str, float]] = []
    for month, centroid in author_monthly_centroids:
        c = np.asarray(centroid, dtype=np.float64).ravel()
        sim = _cosine_similarity(c, ai_centroid)
        convergence.append((month, sim))
    return convergence


def generate_umap_projection(
    centroids_by_author: dict[str, list[tuple[str, np.ndarray]]],
    *,
    ai_centroid: np.ndarray | None = None,
    random_state: int = 42,
) -> dict[str, Any]:
    """2D UMAP coordinates for monthly centroids (and optional AI centroid)."""
    try:
        import umap
    except ImportError as exc:  # pragma: no cover
        msg = "umap-learn is required for generate_umap_projection"
        raise RuntimeError(msg) from exc

    all_vectors: list[np.ndarray] = []
    meta: list[tuple[str, str]] = []
    for author, centroids in centroids_by_author.items():
        for month, vec in centroids:
            all_vectors.append(np.asarray(vec, dtype=np.float32).ravel())
            meta.append((author, month))
    if ai_centroid is not None:
        all_vectors.append(np.asarray(ai_centroid, dtype=np.float32).ravel())
        meta.append(("AI_BASELINE", "synthetic"))

    if not all_vectors:
        return {"projections": {}, "ai_projection": None}

    n = len(all_vectors)
    if n < 2:
        projections: dict[str, list[dict[str, float | str]]] = defaultdict(list)
        auth0, label0 = meta[0]
        projections[auth0].append({"month": label0, "x": 0.0, "y": 0.0})
        return {"projections": dict(projections), "ai_projection": None}

    n_neighbors = max(1, min(15, n - 1))
    reducer = umap.UMAP(
        n_components=2,
        random_state=random_state,
        metric="cosine",
        n_neighbors=n_neighbors,
        min_dist=0.1,
    )
    projected = reducer.fit_transform(np.stack(all_vectors, axis=0))

    projections: dict[str, list[dict[str, float | str]]] = defaultdict(list)
    ai_projection: dict[str, float] | None = None
    for idx, (auth, label) in enumerate(meta):
        row = {"month": label, "x": float(projected[idx, 0]), "y": float(projected[idx, 1])}
        if auth == "AI_BASELINE":
            ai_projection = {"x": row["x"], "y": row["y"]}
        else:
            projections[auth].append(row)
    return {"projections": dict(projections), "ai_projection": ai_projection}


def compute_drift_scores(
    author_id: str,
    baseline_similarity_curve: list[tuple[datetime, float]],
    ai_convergence: list[tuple[str, float]] | None,
    centroid_velocities: list[float],
    intra_variance_trend: list[tuple[str, float]],
) -> DriftScores:
    """Bundle drift metrics into ``DriftScores``."""
    last_baseline = float(baseline_similarity_curve[-1][1]) if baseline_similarity_curve else 0.0
    last_ai = float(ai_convergence[-1][1]) if ai_convergence else 0.0
    return DriftScores(
        author_id=author_id,
        baseline_centroid_similarity=last_baseline,
        ai_baseline_similarity=last_ai,
        monthly_centroid_velocities=list(centroid_velocities),
        intra_period_variance_trend=[v for _, v in intra_variance_trend],
    )


def load_article_embeddings(
    author_slug: str,
    paths: AnalysisArtifactPaths,
) -> list[ArticleEmbedding]:
    """Load article embeddings from manifest + ``.npy`` or ``batch.npz``."""
    root = paths.project_root
    batch_cache: dict[Path, tuple[np.ndarray, dict[str, int]]] = {}
    with Repository(paths.db_path) as repo:
        author = repo.get_author_by_slug(author_slug)
        if author is None:
            msg = f"Unknown author slug for embeddings load: {author_slug}"
            raise ValueError(msg)
        manifest_path = paths.embeddings_dir / "manifest.jsonl"
        records = read_embeddings_manifest(manifest_path)
        pairs: list[ArticleEmbedding] = []
        for rec in records:
            if rec.author_id != author.id:
                continue
            p = Path(rec.embedding_path)
            abs_path = p if p.is_absolute() else (root / p)
            vec = _load_embedding_row(abs_path, rec.article_id, batch_cache)
            if vec is None:
                logger.warning(
                    "Missing or unreadable embedding for article %s: %s", rec.article_id, abs_path
                )
                continue
            pairs.append(ArticleEmbedding(published_at=rec.timestamp, embedding=vec))
        pairs.sort(key=lambda r: r.published_at)
        return pairs


def load_ai_baseline_embeddings(author_slug: str, paths: AnalysisArtifactPaths) -> list[np.ndarray]:
    base = paths.ai_baseline_embeddings_dir(author_slug)
    if not base.is_dir():
        return []
    out: list[np.ndarray] = []
    for path in sorted(base.glob("*.npy")):
        out.append(np.load(path))
    return out


def write_drift_artifacts(
    author_slug: str,
    author_id: str,
    *,
    paths: AnalysisArtifactPaths,
    drift: DriftScores,
    centroids: list[tuple[str, np.ndarray]],
    baseline_curve: list[tuple[datetime, float]],
    umap_payload: dict[str, Any],
) -> None:
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)
    paths.drift_json(author_slug).write_text(
        drift.model_dump_json(indent=2),
        encoding="utf-8",
    )
    months = np.array([m for m, _ in centroids], dtype="U7")
    vecs = np.stack([np.asarray(v, dtype=np.float32) for _, v in centroids], axis=0)
    np.savez_compressed(
        paths.centroids_npz(author_slug),
        months=months,
        centroids=vecs,
    )
    curve_json = [
        {"published_at": dt.isoformat(), "similarity": float(sim)} for dt, sim in baseline_curve
    ]
    paths.baseline_curve_json(author_slug).write_text(
        json.dumps(curve_json, indent=2),
        encoding="utf-8",
    )
    paths.umap_json(author_slug).write_text(
        json.dumps(umap_payload, indent=2),
        encoding="utf-8",
    )


def compute_author_drift_pipeline(
    slug: str,
    author_id: str,
    article_embs: Sequence[ArticleEmbedding],
    settings: ForensicsSettings,
    *,
    paths: AnalysisArtifactPaths,
) -> (
    tuple[
        list[tuple[str, np.ndarray]],
        DriftScores,
        dict[str, Any],
        list[tuple[datetime, float]],
        list[float],
        list[tuple[str, float]] | None,
    ]
    | None
):
    """Shared drift workflow: centroids, curves, scores, UMAP, artifact write.

    Returns ``(monthly, drift, umap_payload, baseline_curve, velocities, ai_conv)`` or
    ``None`` when embeddings are insufficient.
    """
    if len(article_embs) < 2:
        return None
    monthly = compute_monthly_centroids(article_embs)
    if not monthly:
        return None
    velocities = track_centroid_velocity(monthly)
    baseline_curve = compute_baseline_similarity_curve(
        article_embs,
        baseline_count=settings.analysis.baseline_embedding_count,
    )
    intra = compute_intra_period_variance(
        article_embs,
        period="month",
        max_pairwise=settings.analysis.intra_variance_pairwise_max,
    )
    ai_vecs = load_ai_baseline_embeddings(slug, paths)
    ai_conv = compute_ai_convergence(monthly, ai_vecs) if ai_vecs else None
    ai_centroid_plot: np.ndarray | None = None
    if ai_vecs:
        stacked_ai = np.stack([np.asarray(e, dtype=np.float64) for e in ai_vecs], axis=0)
        ai_centroid_plot = stacked_ai.mean(axis=0).ravel()
    drift = compute_drift_scores(
        author_id,
        baseline_curve,
        ai_conv,
        velocities,
        intra,
    )
    umap_one = generate_umap_projection({slug: monthly}, ai_centroid=ai_centroid_plot)
    write_drift_artifacts(
        slug,
        author_id,
        paths=paths,
        drift=drift,
        centroids=monthly,
        baseline_curve=baseline_curve,
        umap_payload=umap_one,
    )
    return monthly, drift, umap_one, baseline_curve, velocities, ai_conv


def run_drift_analysis(
    settings: ForensicsSettings,
    *,
    paths: AnalysisArtifactPaths,
    author_slug: str | None = None,
) -> None:
    """Compute drift metrics for configured authors and write ``data/analysis/*`` outputs."""
    centroids_by_author: dict[str, list[tuple[str, np.ndarray]]] = {}

    with Repository(paths.db_path) as repo:
        author_rows = resolve_author_rows(repo, settings, author_slug=author_slug)
        for author in author_rows:
            try:
                article_embs = load_article_embeddings(author.slug, paths)
            except ValueError as exc:
                logger.warning("drift: skip slug=%s (%s)", author.slug, exc)
                continue
            res = compute_author_drift_pipeline(
                author.slug,
                author.id,
                article_embs,
                settings,
                paths=paths,
            )
            if res is None:
                logger.warning("drift: insufficient embeddings for %s", author.slug)
                continue
            monthly, _drift, _umap, _bc, _vel, _ai = res
            centroids_by_author[author.slug] = monthly
            logger.info("drift: wrote analysis artifacts for %s", author.slug)

    if len(centroids_by_author) > 1:
        combined = generate_umap_projection(
            centroids_by_author,
            ai_centroid=None,
        )
        paths.combined_umap_json().write_text(
            json.dumps(combined, indent=2),
            encoding="utf-8",
        )


def run_ai_baseline_command(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    project_root: Path | None = None,
    author_slug: str | None = None,
    skip_generation: bool = False,
    articles_per_cell: int | None = None,
    model_filter: str | None = None,
    dry_run: bool = False,
) -> None:
    """CLI entry: generate or re-embed AI baseline corpus via local Ollama.

    Delegates to ``forensics.baseline.orchestrator``. The Phase 10 v0.3.0 spec
    replaces the old OpenAI path with three locally-run Ollama models
    (Llama 3.1 8B, Mistral 7B, Gemma 2 9B) so baselines are reproducible by
    model digest with no external API keys required.
    """
    from forensics.baseline.orchestrator import (
        reembed_existing_baseline,
        run_generation_matrix,
    )

    slugs = [author_slug] if author_slug else [a.slug for a in settings.authors]

    if skip_generation:
        for slug in slugs:
            reembed_existing_baseline(slug, settings, project_root=project_root)
        return

    async def _run() -> None:
        for slug in slugs:
            await run_generation_matrix(
                slug,
                settings,
                db_path=db_path,
                project_root=project_root,
                articles_per_cell=articles_per_cell,
                model_filter=model_filter,
                dry_run=dry_run,
            )

    asyncio.run(_run())
