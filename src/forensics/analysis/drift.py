"""Embedding drift analysis (Phase 6): monthly centroids, velocities, AI baseline."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from scipy.spatial.distance import cosine
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import TfidfVectorizer

from forensics.config import get_project_root
from forensics.config.settings import AnalysisConfig, ForensicsSettings
from forensics.features import embeddings as embed_mod
from forensics.models.analysis import DriftScores
from forensics.storage.parquet import read_embeddings_manifest
from forensics.storage.repository import Repository, init_db

logger = logging.getLogger(__name__)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def compute_monthly_centroids(
    article_embeddings: list[tuple[datetime, np.ndarray]],
) -> list[tuple[str, np.ndarray]]:
    """Mean embedding vector per calendar month, sorted chronologically."""
    monthly: dict[str, list[np.ndarray]] = defaultdict(list)
    for dt, emb in article_embeddings:
        key = dt.strftime("%Y-%m")
        monthly[key].append(np.asarray(emb, dtype=np.float32))
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
    article_embeddings: list[tuple[datetime, np.ndarray]],
    *,
    baseline_count: int = 20,
) -> list[tuple[datetime, float]]:
    """Cosine similarity to centroid of first ``baseline_count`` articles by publish time."""
    if not article_embeddings:
        return []
    ordered = sorted(article_embeddings, key=lambda x: x[0])
    n_base = max(1, min(baseline_count, len(ordered)))
    base_vecs = np.stack([np.asarray(e, dtype=np.float64) for _, e in ordered[:n_base]], axis=0)
    baseline_centroid = base_vecs.mean(axis=0)
    curve: list[tuple[datetime, float]] = []
    for dt, emb in ordered:
        sim = _cosine_similarity(np.asarray(emb, dtype=np.float64), baseline_centroid)
        curve.append((dt, sim))
    return curve


def compute_intra_period_variance(
    article_embeddings: list[tuple[datetime, np.ndarray]],
    *,
    period: str = "month",
) -> list[tuple[str, float]]:
    """Mean pairwise cosine distance within each period (default: calendar month)."""
    if period != "month":
        msg = f"Unsupported period: {period!r} (only 'month' is implemented)"
        raise ValueError(msg)
    buckets: dict[str, list[np.ndarray]] = defaultdict(list)
    for dt, emb in article_embeddings:
        buckets[dt.strftime("%Y-%m")].append(np.asarray(emb, dtype=np.float64))
    out: list[tuple[str, float]] = []
    for key in sorted(buckets.keys()):
        vecs = buckets[key]
        if len(vecs) < 2:
            out.append((key, 0.0))
            continue
        dists: list[float] = []
        for i in range(len(vecs)):
            for j in range(i + 1, len(vecs)):
                d = float(cosine(vecs[i].ravel(), vecs[j].ravel()))
                if np.isfinite(d):
                    dists.append(d)
        out.append((key, float(np.mean(dists)) if dists else 0.0))
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
    embeddings_dir: Path,
    db_path: Path,
    *,
    project_root: Path | None = None,
) -> list[tuple[datetime, np.ndarray]]:
    """Load ``(published_date, embedding)`` for one author from manifest + ``.npy`` files."""
    init_db(db_path)
    root = project_root or get_project_root()
    repo = Repository(db_path)
    author = repo.get_author_by_slug(author_slug)
    if author is None:
        msg = f"Unknown author slug for embeddings load: {author_slug}"
        raise ValueError(msg)
    manifest_path = embeddings_dir / "manifest.jsonl"
    records = read_embeddings_manifest(manifest_path)
    pairs: list[tuple[datetime, np.ndarray]] = []
    for rec in records:
        if rec.author_id != author.id:
            continue
        p = Path(rec.embedding_path)
        abs_path = p if p.is_absolute() else (root / p)
        if not abs_path.is_file():
            logger.warning("Missing embedding file for article %s: %s", rec.article_id, abs_path)
            continue
        vec = np.load(abs_path)
        pairs.append((rec.timestamp, vec))
    pairs.sort(key=lambda x: x[0])
    return pairs


def _load_ai_baseline_embeddings(author_slug: str, project_root: Path) -> list[np.ndarray]:
    base = project_root / "data" / "ai_baseline" / author_slug / "embeddings"
    if not base.is_dir():
        return []
    out: list[np.ndarray] = []
    for path in sorted(base.glob("*.npy")):
        out.append(np.load(path))
    return out


def extract_lda_topic_keywords(
    texts: list[str],
    *,
    num_topics: int = 20,
    n_keywords: int = 10,
    random_state: int = 42,
) -> list[tuple[int, list[str], str]]:
    """Fit LDA on TF-IDF corpus; return ``(topic_id, keywords, summary)`` per topic."""
    if not texts:
        return []
    n_samples = len(texts)
    max_features = min(5000, max(100, n_samples * 10))
    vectorizer = TfidfVectorizer(
        max_df=0.95,
        min_df=max(1, min(2, n_samples // 5)),
        max_features=max_features,
        stop_words="english",
    )
    X = vectorizer.fit_transform(texts)
    n_topics_eff = max(2, min(num_topics, max(2, X.shape[0] // 5)))
    lda = LatentDirichletAllocation(
        n_components=n_topics_eff,
        random_state=random_state,
        max_iter=30,
        learning_method="online",
    )
    lda.fit(X)
    names = vectorizer.get_feature_names_out()
    topics: list[tuple[int, list[str], str]] = []
    for topic_idx, topic in enumerate(lda.components_):
        top_ix = topic.argsort()[: -n_keywords - 1 : -1]
        kws = [str(names[i]) for i in top_ix]
        summary = ", ".join(kws[:5])
        topics.append((topic_idx, kws, summary))
    return topics


async def _openai_chat_completion(
    *,
    api_key: str,
    model: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    return str(data["choices"][0]["message"]["content"])


async def generate_ai_baseline(
    db_path: Path,
    author_slug: str,
    config: AnalysisConfig,
    *,
    project_root: Path | None = None,
    llm_model: str = "gpt-4o",
    articles_per_topic: int = 3,
    num_topics: int = 20,
    api_key: str | None = None,
    skip_generation: bool = False,
) -> Path:
    """Synthetic AI articles + embeddings under ``data/ai_baseline/{author_slug}/``."""
    init_db(db_path)
    root = project_root or get_project_root()
    out_dir = root / "data" / "ai_baseline" / author_slug
    articles_dir = out_dir / "articles"
    emb_dir = out_dir / "embeddings"
    articles_dir.mkdir(parents=True, exist_ok=True)
    emb_dir.mkdir(parents=True, exist_ok=True)

    repo = Repository(db_path)
    author = repo.get_author_by_slug(author_slug)
    if author is None:
        msg = f"Unknown author slug: {author_slug}"
        raise ValueError(msg)

    model_name = config.embedding_model
    key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()

    if not skip_generation:
        if not key:
            msg = "OPENAI_API_KEY or api_key is required unless --skip-generation is set"
            raise ValueError(msg)
        corpus = repo.list_articles_for_extraction(author_id=author.id)
        texts = [a.clean_text for a in corpus if a.clean_text.strip()]
        if len(texts) < 5:
            msg = f"Need at least 5 articles with text for LDA baseline (got {len(texts)})"
            raise ValueError(msg)
        word_counts = [a.word_count for a in corpus if a.clean_text.strip()]
        median_words = int(np.median(word_counts)) if word_counts else 600

        topics = extract_lda_topic_keywords(texts, num_topics=num_topics, n_keywords=10)
        if not topics:
            msg = "LDA returned no topics; corpus may be too small or too uniform."
            raise ValueError(msg)
        generated: list[dict[str, Any]] = []

        for topic_id, keywords, summary in topics:
            topic_summary = summary
            for _j in range(articles_per_topic):
                prompt = (
                    f"Write a {median_words}-word news article about {topic_summary} "
                    "in the style of a professional journalist."
                )
                text = await _openai_chat_completion(
                    api_key=key,
                    model=llm_model,
                    user_prompt=prompt,
                    temperature=0.7,
                    max_tokens=1500,
                )
                rec_id = str(uuid.uuid4())
                payload = {
                    "id": rec_id,
                    "topic_id": topic_id,
                    "topic_keywords": keywords,
                    "prompt": prompt,
                    "model": llm_model,
                    "model_version": datetime.now(UTC).date().isoformat(),
                    "generated_at": datetime.now(UTC).isoformat(),
                    "text": text,
                    "generation_params": {"temperature": 0.7, "max_tokens": 1500},
                }
                path = articles_dir / f"{rec_id}.json"
                path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                generated.append(payload)
                logger.info("ai_baseline: wrote synthetic article %s (topic %s)", rec_id, topic_id)

        for payload in generated:
            vec = embed_mod.compute_embedding(payload["text"], model_name)
            np.save(emb_dir / f"{payload['id']}.npy", vec)
    else:
        json_paths = sorted(articles_dir.glob("*.json"))
        if not json_paths:
            msg = f"No baseline articles under {articles_dir}; run without --skip-generation first."
            raise ValueError(msg)
        for path in json_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            vec = embed_mod.compute_embedding(str(payload.get("text", "")), model_name)
            np.save(emb_dir / f"{Path(path).stem}.npy", vec)
        logger.info("ai_baseline: re-embedded %s from existing JSON", author_slug)

    return out_dir


def _write_drift_artifacts(
    author_slug: str,
    author_id: str,
    *,
    analysis_dir: Path,
    drift: DriftScores,
    centroids: list[tuple[str, np.ndarray]],
    baseline_curve: list[tuple[datetime, float]],
    umap_payload: dict[str, Any],
) -> None:
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / f"{author_slug}_drift.json").write_text(
        drift.model_dump_json(indent=2),
        encoding="utf-8",
    )
    months = np.array([m for m, _ in centroids], dtype="U7")
    vecs = np.stack([np.asarray(v, dtype=np.float32) for _, v in centroids], axis=0)
    np.savez_compressed(
        analysis_dir / f"{author_slug}_centroids.npz",
        months=months,
        centroids=vecs,
    )
    curve_json = [
        {"published_at": dt.isoformat(), "similarity": float(sim)} for dt, sim in baseline_curve
    ]
    (analysis_dir / f"{author_slug}_baseline_curve.json").write_text(
        json.dumps(curve_json, indent=2),
        encoding="utf-8",
    )
    (analysis_dir / f"{author_slug}_umap.json").write_text(
        json.dumps(umap_payload, indent=2),
        encoding="utf-8",
    )


def run_drift_analysis(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    project_root: Path | None = None,
    author_slug: str | None = None,
) -> None:
    """Compute drift metrics for configured authors and write ``data/analysis/*`` outputs."""
    init_db(db_path)
    root = project_root or get_project_root()
    embed_root = root / "data" / "embeddings"
    analysis_dir = root / "data" / "analysis"
    repo = Repository(db_path)

    slugs = [author_slug] if author_slug else [a.slug for a in settings.authors]
    centroids_by_author: dict[str, list[tuple[str, np.ndarray]]] = {}

    for slug in slugs:
        try:
            article_embs = load_article_embeddings(slug, embed_root, db_path, project_root=root)
        except ValueError as exc:
            logger.warning("drift: skip slug=%s (%s)", slug, exc)
            continue
        if len(article_embs) < 2:
            logger.warning("drift: insufficient embeddings for %s", slug)
            continue

        author = repo.get_author_by_slug(slug)
        if author is None:
            logger.warning("drift: author row missing for slug=%s", slug)
            continue
        monthly = compute_monthly_centroids(article_embs)
        if not monthly:
            continue
        velocities = track_centroid_velocity(monthly)
        baseline_curve = compute_baseline_similarity_curve(
            article_embs,
            baseline_count=20,
        )
        intra = compute_intra_period_variance(article_embs, period="month")

        ai_vecs = _load_ai_baseline_embeddings(slug, root)
        ai_conv = compute_ai_convergence(monthly, ai_vecs) if ai_vecs else None
        ai_centroid_plot: np.ndarray | None = None
        if ai_vecs:
            stacked_ai = np.stack([np.asarray(e, dtype=np.float64) for e in ai_vecs], axis=0)
            ai_centroid_plot = stacked_ai.mean(axis=0).ravel()

        drift = compute_drift_scores(
            author.id,
            baseline_curve,
            ai_conv,
            velocities,
            intra,
        )
        centroids_by_author[slug] = monthly

        umap_one = generate_umap_projection(
            {slug: monthly},
            ai_centroid=ai_centroid_plot,
        )
        _write_drift_artifacts(
            slug,
            author.id,
            analysis_dir=analysis_dir,
            drift=drift,
            centroids=monthly,
            baseline_curve=baseline_curve,
            umap_payload=umap_one,
        )
        logger.info("drift: wrote analysis artifacts for %s", slug)

    if len(centroids_by_author) > 1:
        combined = generate_umap_projection(
            centroids_by_author,
            ai_centroid=None,
        )
        (analysis_dir / "combined_umap.json").write_text(
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
    openai_key: str | None = None,
    llm_model: str = "gpt-4o",
) -> None:
    """CLI entry: generate or re-embed AI baseline corpus."""
    slugs = [author_slug] if author_slug else [a.slug for a in settings.authors]

    async def _run() -> None:
        for slug in slugs:
            await generate_ai_baseline(
                db_path,
                slug,
                settings.analysis,
                project_root=project_root,
                llm_model=llm_model,
                skip_generation=skip_generation,
                api_key=openai_key,
            )

    asyncio.run(_run())
