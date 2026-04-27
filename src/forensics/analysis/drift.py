"""Embedding drift: monthly centroids, velocities, AI baseline."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from forensics.analysis.utils import pair_months_with_velocities
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import DriftScores
from forensics.models.features import EmbeddingRecord
from forensics.paths import AnalysisArtifactPaths, resolve_author_rows
from forensics.storage.json_io import write_json_artifact
from forensics.storage.parquet import (
    EMBEDDING_BATCH_KEY_BYTES,
    EMBEDDING_BATCH_KEY_LENGTHS,
    EMBEDDING_BATCH_KEY_VECTORS,
    read_embeddings_manifest,
    save_numpy_compressed_atomic,
    unpack_article_ids_from_embedding_batch,
)
from forensics.storage.repository import Repository
from forensics.utils.datetime import parse_datetime

logger = logging.getLogger(__name__)

# N-03 — UMAP with fewer than four monthly centroids is not meaningful.
_UMAP_MIN_MONTHLY_CENTROIDS: int = 4


class EmbeddingRevisionGateError(ValueError):
    """Raised when stored ``model_revision`` disagrees with the configured HF pin."""


@dataclass(frozen=True, slots=True)
class DriftPipelineResult:
    """Outputs of :func:`compute_author_drift_pipeline` (RF-SMELL-002).

    Replaces a 6-tuple whose callers had to destructure with throwaway names
    (``_umap``, ``_bc``, ``_vel``, ``_ai``). Field access is now explicit.
    """

    monthly_centroids: list[tuple[str, np.ndarray]]
    drift_scores: DriftScores
    umap_payload: dict[str, Any]
    baseline_curve: list[tuple[datetime, float]]
    velocities: list[float]
    ai_convergence: list[tuple[str, float]] | None


@dataclass(frozen=True, slots=True)
class DriftSummary:
    """Cached-or-recomputed drift per author: monthly velocities + baseline curve.

    ``velocities`` pairs each month label with its cosine distance from the previous
    month's centroid (so ``velocities[0]`` describes the jump from month 0 to month 1).
    ``baseline_curve`` is the per-article cosine similarity to the first-articles
    centroid. Either may be empty when no cached artifact exists and embeddings are
    unavailable.
    """

    velocities: list[tuple[str, float]]
    baseline_curve: list[tuple[datetime, float]]


@dataclass(frozen=True, slots=True)
class ArticleEmbedding:
    """One article's semantic embedding with its publish time (drift pipeline input)."""

    published_at: datetime
    embedding: np.ndarray = field(repr=False)


def _load_npy_embedding(abs_path: Path) -> np.ndarray | None:
    """Load a single embedding from a legacy per-article ``.npy`` file."""
    try:
        return np.asarray(np.load(abs_path), dtype=np.float32).ravel()
    except (OSError, ValueError) as exc:
        logger.warning("Could not read embedding file %s: %s", abs_path, exc)
        return None


def _load_packed_batch(abs_path: Path) -> tuple[np.ndarray, dict[str, int]] | None:
    """Load a packed-IDs ``batch.npz`` file and return ``(matrix, id_map)``.

    Returns ``None`` for legacy pickled-IDs batches or malformed files —
    callers log once and skip the whole author.
    """
    try:
        z = np.load(abs_path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        logger.warning("Could not read embedding batch %s: %s", abs_path, exc)
        return None
    keys = frozenset(z.files)
    has_packed = (
        EMBEDDING_BATCH_KEY_LENGTHS in keys
        and EMBEDDING_BATCH_KEY_BYTES in keys
        and EMBEDDING_BATCH_KEY_VECTORS in keys
    )
    if not has_packed:
        if "article_ids" in keys and EMBEDDING_BATCH_KEY_VECTORS in keys:
            logger.warning(
                "Legacy embedding batch %s uses pickled article_ids; "
                "re-run feature extraction to rewrite the batch.",
                abs_path,
            )
        else:
            logger.warning("Malformed embedding batch (missing keys): %s", abs_path)
        return None
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
        logger.warning("Malformed embedding batch (shape mismatch): %s", abs_path)
        return None
    return mat, {aid: i for i, aid in enumerate(ids_list)}


def _load_embedding_row(
    abs_path: Path,
    article_id: str,
    batch_cache: dict[Path, tuple[np.ndarray, dict[str, int]]],
) -> np.ndarray | None:
    """Load one embedding row, dispatching on suffix between ``.npy`` and ``batch.npz``."""
    if not abs_path.is_file():
        return None
    if abs_path.suffix.lower() != ".npz":
        return _load_npy_embedding(abs_path)
    if abs_path not in batch_cache:
        loaded = _load_packed_batch(abs_path)
        if loaded is None:
            return None
        batch_cache[abs_path] = loaded
    mat, id_map = batch_cache[abs_path]
    row = id_map.get(article_id)
    if row is None:
        logger.warning("Article %s not in embedding batch %s", article_id, abs_path)
        return None
    return np.asarray(mat[row], dtype=np.float32)


def validate_embedding_record(
    record: EmbeddingRecord,
    vec: np.ndarray,
    expected_revision: str,
    *,
    exploratory: bool,
    allow_pre_phase16_embeddings: bool,
) -> None:
    """Ensure ``vec`` matches ``record`` metadata before drift consumes it.

    Dimension mismatches always raise :class:`ValueError` (correctness /
    integrity). When ``expected_revision`` is non-empty, the manifest revision
    must match unless the operator is in exploratory mode **and** passed
    ``--allow-pre-phase16-embeddings`` (legacy vectors or mismatched HF pins),
    in which case a WARNING is logged and execution continues.
    """
    got_dim = int(vec.shape[-1])
    if got_dim != int(record.embedding_dim):
        msg = (
            f"Embedding dimension mismatch for article {record.article_id}: "
            f"vector shape {vec.shape}, record.embedding_dim={record.embedding_dim}."
        )
        raise ValueError(msg)
    if not (expected_revision or "").strip():
        return
    stored = (record.model_revision or "").strip()
    expected = expected_revision.strip()
    if stored == expected:
        return
    msg = (
        f"Embedding model revision mismatch for article {record.article_id}: "
        f"manifest has {stored!r}, analysis expects {expected!r}."
    )
    if exploratory and allow_pre_phase16_embeddings:
        logger.warning(
            "%s Continuing due to --exploratory and --allow-pre-phase16-embeddings.",
            msg,
        )
        return
    raise EmbeddingRevisionGateError(msg)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """C-03/C-04 — cosine distance matching ``scipy.spatial.distance.cosine`` for finite norms."""
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    d = 1.0 - float(np.dot(a, b) / (na * nb))
    return float(d) if np.isfinite(d) else 0.0


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
        d = _cosine_distance(prev_v, cur_v)
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
        sim = _cosine_similarity(np.asarray(row.embedding, dtype=np.float64), baseline_centroid)
        curve.append((row.published_at, sim))
    return curve


def _pairwise_mean_cosine_distance(vecs: list[np.ndarray]) -> float:
    dists: list[float] = []
    for i in range(len(vecs)):
        for j in range(i + 1, len(vecs)):
            d = _cosine_distance(vecs[i].ravel(), vecs[j].ravel())
            if np.isfinite(d):
                dists.append(d)
    return float(np.mean(dists)) if dists else 0.0


def _mean_cosine_to_centroid(vecs: list[np.ndarray]) -> float:
    stacked = np.stack([v.ravel() for v in vecs], axis=0)
    centroid = stacked.mean(axis=0)
    dists_c: list[float] = []
    for v in vecs:
        d = _cosine_distance(v.ravel(), centroid)
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
    """Bundle drift metrics into ``DriftScores``.

    ``ai_baseline_similarity`` is ``None`` when no AI baseline is available —
    callers must distinguish "no measurement" from a real 0.0 convergence.
    """
    last_baseline = float(baseline_similarity_curve[-1][1]) if baseline_similarity_curve else 0.0
    last_ai = float(ai_convergence[-1][1]) if ai_convergence else None
    return DriftScores(
        author_id=author_id,
        baseline_centroid_similarity=last_baseline,
        ai_baseline_similarity=last_ai,
        monthly_centroid_velocities=list(centroid_velocities),
        intra_period_variance_trend=[v for _, v in intra_variance_trend],
    )


def _classify_embedding_path(abs_path: Path) -> str:
    """Return ``"npz"`` for a packed batch file, ``"npy"`` for legacy per-article.

    Used by :func:`load_article_embeddings` to emit a single per-author DEBUG
    audit line covering the mix of writer formats encountered (Phase 15 G3).
    """
    return "npz" if abs_path.suffix.lower() == ".npz" else "npy"


def load_article_embeddings(
    author_slug: str,
    paths: AnalysisArtifactPaths,
    *,
    expected_revision: str = "",
    exploratory: bool = False,
    allow_pre_phase16_embeddings: bool = False,
) -> list[ArticleEmbedding]:
    """Load article embeddings from manifest + ``.npy`` or ``batch.npz``.

    Phase 15 G3: emits one DEBUG line summarising the mix of writer formats
    referenced in the manifest for this author. The default writer is
    ``batch.npz`` (see :func:`forensics.storage.parquet.write_author_embedding_batch`);
    a non-zero ``.npy`` count indicates legacy artifacts that predate the
    packed-batch migration and is informational only — readers handle both.

    Pass ``expected_revision=settings.analysis.embedding.embedding_model_revision`` in
    production so vectors from a different HF commit fail fast. Use
    ``expected_revision=\"\"`` only in tests that intentionally omit revision
    metadata. Mismatches respect ``exploratory`` and
    ``allow_pre_phase16_embeddings`` (see :func:`validate_embedding_record`).
    """
    root = paths.project_root
    batch_cache: dict[Path, tuple[np.ndarray, dict[str, int]]] = {}
    format_counts: dict[str, int] = {"npz": 0, "npy": 0}
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
            format_counts[_classify_embedding_path(abs_path)] += 1
            vec = _load_embedding_row(abs_path, rec.article_id, batch_cache)
            if vec is None:
                logger.warning(
                    "Missing or unreadable embedding for article %s: %s", rec.article_id, abs_path
                )
                continue
            validate_embedding_record(
                rec,
                vec,
                expected_revision,
                exploratory=exploratory,
                allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
            )
            pairs.append(ArticleEmbedding(published_at=rec.timestamp, embedding=vec))
        if format_counts["npz"] or format_counts["npy"]:
            logger.debug(
                "embedding I/O audit: slug=%s npz=%d npy=%d (default writer is batch.npz)",
                author_slug,
                format_counts["npz"],
                format_counts["npy"],
            )
        pairs.sort(key=lambda r: r.published_at)
        return pairs


def _iter_ai_baseline_embedding_paths(author_slug: str, paths: AnalysisArtifactPaths) -> list[Path]:
    """Return legacy and nested generated AI baseline vector paths."""
    author_root = paths.ai_baseline_dir(author_slug)
    legacy_dir = paths.ai_baseline_embeddings_dir(author_slug)
    candidates: set[Path] = set()
    if legacy_dir.is_dir():
        candidates.update(legacy_dir.glob("*.npy"))
    manifest_path = author_root / "generation_manifest.json"
    if author_root.is_dir() and manifest_path.is_file():
        candidates.update(p for p in author_root.rglob("*.npy") if "embeddings" in p.parts)
    return sorted(candidates)


def _load_ai_baseline_vector(path: Path, *, expected_dim: int) -> np.ndarray | None:
    """Load and validate one AI baseline embedding vector."""
    try:
        vec = np.asarray(np.load(path), dtype=np.float32).ravel()
    except (OSError, ValueError) as exc:
        logger.warning("Could not read AI baseline embedding %s: %s", path, exc)
        return None
    if vec.shape != (expected_dim,):
        logger.warning(
            "Skipping AI baseline embedding with unexpected dimension: %s shape=%s expected=(%d,)",
            path,
            vec.shape,
            expected_dim,
        )
        return None
    return vec


def load_ai_baseline_embeddings(
    author_slug: str,
    paths: AnalysisArtifactPaths,
    *,
    expected_dim: int = 384,
) -> list[np.ndarray]:
    """Load generated AI baseline embeddings from legacy or nested Phase 10 layouts."""
    embedding_paths = _iter_ai_baseline_embedding_paths(author_slug, paths)
    if not embedding_paths:
        return []
    out: list[np.ndarray] = []
    for path in embedding_paths:
        vec = _load_ai_baseline_vector(path, expected_dim=expected_dim)
        if vec is not None:
            out.append(vec)
    return out


def _load_cached_baseline_curve(path: Path) -> list[tuple[datetime, float]]:
    if not path.is_file():
        return []
    return [
        (parse_datetime(row["published_at"]), float(row["similarity"]))
        for row in json.loads(path.read_text(encoding="utf-8"))
    ]


def _load_cached_velocities(
    drift_path: Path,
    centroids_path: Path,
) -> list[tuple[str, float]]:
    if not drift_path.is_file():
        return []
    scores = DriftScores.model_validate_json(drift_path.read_text(encoding="utf-8"))
    if not scores.monthly_centroid_velocities:
        return []
    months: list[str] = []
    if centroids_path.is_file():
        months = [str(x) for x in np.load(centroids_path)["months"].tolist()]
    if len(months) >= 2:
        return list(zip(months[1:], scores.monthly_centroid_velocities, strict=False))
    return [(f"m{i}", v) for i, v in enumerate(scores.monthly_centroid_velocities)]


def _author_has_embeddings_on_disk(slug: str, paths: AnalysisArtifactPaths) -> bool:
    """True iff ``data/embeddings/<slug>/`` exists and contains at least one file.

    Used by :func:`load_drift_summary` to decide whether a missing drift
    artifact warrants a WARNING (embeddings present → silent write failure)
    or stays at the default DEBUG-quiet path (no embeddings → no analysis).
    """
    slug_dir = paths.embeddings_dir / slug
    if not slug_dir.is_dir():
        return False
    return any(slug_dir.iterdir())


# Phase 15 E2 — stable WARNING template. Log-grep dashboards key on this exact
# prefix; do not change without updating the regression-pin test.
_DRIFT_ARTIFACT_MISSING_WARNING: str = (
    "drift summary: missing artifact %s for slug=%s but embeddings exist on disk"
)


def _warn_missing_drift_artifacts(slug: str, paths: AnalysisArtifactPaths) -> None:
    """Phase 15 E2: emit one WARNING per missing artifact when embeddings exist.

    Default behaviour of :func:`load_drift_summary` (return empty fields) is
    preserved — this is a logging-only diagnostic that surfaces silent
    artifact-write failures for authors who do have embeddings on disk.
    """
    if not _author_has_embeddings_on_disk(slug, paths):
        return
    artifacts = (
        ("drift.json", paths.drift_json(slug)),
        ("baseline_curve.json", paths.baseline_curve_json(slug)),
        ("centroids.npz", paths.centroids_npz(slug)),
    )
    for label, path in artifacts:
        if not path.is_file():
            logger.warning(_DRIFT_ARTIFACT_MISSING_WARNING, label, slug)


def load_drift_summary(
    slug: str,
    paths: AnalysisArtifactPaths,
    *,
    settings: ForensicsSettings,
    exploratory: bool = False,
    allow_pre_phase16_embeddings: bool = False,
) -> DriftSummary:
    """Drift velocities and baseline curve for ``slug``.

    Prefers cached artifacts (``*_drift.json``, ``*_centroids.npz``, ``*_baseline_curve.json``)
    written by :func:`run_drift_analysis`. Falls back to recomputing from raw embeddings
    when cached velocities are missing. Missing embeddings produce empty fields rather than
    raising.

    Phase 15 E2: when one of the cached artifacts is missing but the author
    has embeddings on disk, emit a WARNING per missing artifact so silent
    write failures become visible. Authors with no embeddings stay quiet to
    avoid log noise.
    """
    _warn_missing_drift_artifacts(slug, paths)
    baseline_curve = _load_cached_baseline_curve(paths.baseline_curve_json(slug))
    velocities = _load_cached_velocities(
        paths.drift_json(slug),
        paths.centroids_npz(slug),
    )
    if velocities:
        return DriftSummary(velocities=velocities, baseline_curve=baseline_curve)

    try:
        pairs = load_article_embeddings(
            slug,
            paths,
            expected_revision=settings.analysis.embedding.embedding_model_revision,
            exploratory=exploratory,
            allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
        )
    except EmbeddingRevisionGateError:
        raise
    except (ValueError, OSError) as exc:
        logger.debug("drift summary: no embeddings for %s (%s)", slug, exc)
        return DriftSummary(velocities=velocities, baseline_curve=baseline_curve)

    if len(pairs) < 2:
        return DriftSummary(velocities=velocities, baseline_curve=baseline_curve)

    monthly = compute_monthly_centroids(pairs)
    vels = track_centroid_velocity(monthly)
    velocities = pair_months_with_velocities(monthly, vels)
    if not baseline_curve:
        baseline_curve = compute_baseline_similarity_curve(
            pairs,
            baseline_count=settings.analysis.embedding.baseline_embedding_count,
        )
    return DriftSummary(velocities=velocities, baseline_curve=baseline_curve)


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
    # Parent dir is created inside each writer (RF-DRY-004).
    write_json_artifact(paths.drift_json(author_slug), drift)
    months = np.array([m for m, _ in centroids], dtype="U7")
    vecs = np.stack([np.asarray(v, dtype=np.float32) for _, v in centroids], axis=0)
    save_numpy_compressed_atomic(
        paths.centroids_npz(author_slug),
        months=months,
        centroids=vecs,
    )
    curve_json = [
        {"published_at": dt.isoformat(), "similarity": float(sim)} for dt, sim in baseline_curve
    ]
    write_json_artifact(paths.baseline_curve_json(author_slug), curve_json)
    write_json_artifact(paths.umap_json(author_slug), umap_payload)


def compute_author_drift_pipeline(
    slug: str,
    author_id: str,
    article_embs: Sequence[ArticleEmbedding],
    settings: ForensicsSettings,
    *,
    paths: AnalysisArtifactPaths,
) -> DriftPipelineResult | None:
    """Shared drift workflow: centroids, curves, scores, UMAP, artifact write.

    Returns a :class:`DriftPipelineResult` or ``None`` when embeddings are
    insufficient.
    """
    if len(article_embs) < 2:
        return None
    monthly = compute_monthly_centroids(article_embs)
    if not monthly:
        return None
    velocities = track_centroid_velocity(monthly)
    baseline_curve = compute_baseline_similarity_curve(
        article_embs,
        baseline_count=settings.analysis.embedding.baseline_embedding_count,
    )
    intra = compute_intra_period_variance(
        article_embs,
        period="month",
        max_pairwise=settings.analysis.intra_variance_pairwise_max,
    )
    ai_vecs = load_ai_baseline_embeddings(
        slug,
        paths,
        expected_dim=int(settings.analysis.embedding.embedding_vector_dim),
    )
    if not ai_vecs and len(article_embs) >= 2:
        baseline_root = paths.ai_baseline_dir(slug)
        legacy_emb = paths.ai_baseline_embeddings_dir(slug)
        manifest = baseline_root / "generation_manifest.json"
        has_legacy = legacy_emb.is_dir() and any(legacy_emb.glob("*.npy"))
        if (baseline_root.is_dir() and manifest.is_file()) or has_legacy:
            logger.warning(
                "drift: AI baseline layout present for slug=%s but no vectors loaded "
                "(re-run `forensics baseline` or inspect paths); "
                "ai_baseline_similarity will be absent (L-03)",
                slug,
            )
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
    n_months = len(monthly)
    if n_months >= _UMAP_MIN_MONTHLY_CENTROIDS:
        umap_one = generate_umap_projection(
            {slug: monthly},
            ai_centroid=ai_centroid_plot,
            random_state=int(settings.analysis.embedding.drift_umap_random_state),
        )
    else:
        logger.warning(
            "drift: skipping UMAP for slug=%s — %d monthly centroid(s) "
            "(<%d); projection would be unstable (N-03)",
            slug,
            n_months,
            _UMAP_MIN_MONTHLY_CENTROIDS,
        )
        umap_one = {
            "projections": {},
            "ai_projection": None,
            "skipped": True,
            "reason": "insufficient_monthly_centroids",
            "n_monthly_centroids": n_months,
        }
    write_drift_artifacts(
        slug,
        author_id,
        paths=paths,
        drift=drift,
        centroids=monthly,
        baseline_curve=baseline_curve,
        umap_payload=umap_one,
    )
    return DriftPipelineResult(
        monthly_centroids=monthly,
        drift_scores=drift,
        umap_payload=umap_one,
        baseline_curve=baseline_curve,
        velocities=velocities,
        ai_convergence=ai_conv,
    )


def run_drift_analysis(
    settings: ForensicsSettings,
    *,
    paths: AnalysisArtifactPaths,
    author_slug: str | None = None,
    exploratory: bool = False,
    allow_pre_phase16_embeddings: bool = False,
) -> None:
    """Compute drift metrics for configured authors and write ``data/analysis/*`` outputs."""
    centroids_by_author: dict[str, list[tuple[str, np.ndarray]]] = {}

    with Repository(paths.db_path) as repo:
        author_rows = resolve_author_rows(repo, settings, author_slug=author_slug)
        for author in author_rows:
            try:
                article_embs = load_article_embeddings(
                    author.slug,
                    paths,
                    expected_revision=settings.analysis.embedding.embedding_model_revision,
                    exploratory=exploratory,
                    allow_pre_phase16_embeddings=allow_pre_phase16_embeddings,
                )
            except EmbeddingRevisionGateError:
                raise
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
            centroids_by_author[author.slug] = res.monthly_centroids
            logger.info("drift: wrote analysis artifacts for %s", author.slug)

    if len(centroids_by_author) > 1:
        total_monthly = sum(len(v) for v in centroids_by_author.values())
        if total_monthly >= _UMAP_MIN_MONTHLY_CENTROIDS:
            combined = generate_umap_projection(
                centroids_by_author,
                ai_centroid=None,
                random_state=int(settings.analysis.embedding.drift_umap_random_state),
            )
        else:
            logger.warning(
                "drift: skipping combined UMAP — %d monthly centroid(s) across authors (<%d; N-03)",
                total_monthly,
                _UMAP_MIN_MONTHLY_CENTROIDS,
            )
            combined = {
                "projections": {},
                "ai_projection": None,
                "skipped": True,
                "reason": "insufficient_monthly_centroids",
                "n_monthly_centroids": total_monthly,
            }
        write_json_artifact(paths.combined_umap_json(), combined)
