"""Phase 9 — orchestrator that scores all articles for probability features.

Writes one Parquet per author under ``data/probability/`` plus a
``model_card.json`` that pins the reference / Binoculars model revisions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from forensics.config import get_project_root
from forensics.config.settings import ForensicsSettings
from forensics.features.binoculars import compute_binoculars_score, load_binoculars_models
from forensics.features.probability import compute_perplexity, load_reference_model
from forensics.models.article import Article
from forensics.storage.repository import Repository, init_db

logger = logging.getLogger(__name__)


def _model_card_payload(
    settings: ForensicsSettings,
    *,
    include_binoculars: bool,
    device: str,
    transformers_version: str,
) -> dict:
    cfg = settings.probability
    identity = "|".join(
        [
            cfg.reference_model,
            cfg.reference_model_revision,
            cfg.binoculars_model_base if include_binoculars else "-",
            cfg.binoculars_model_instruct if include_binoculars else "-",
        ]
    )
    return {
        "reference_model": cfg.reference_model,
        "reference_model_revision": cfg.reference_model_revision,
        "binoculars_base": cfg.binoculars_model_base if include_binoculars else None,
        "binoculars_instruct": cfg.binoculars_model_instruct if include_binoculars else None,
        "binoculars_enabled": include_binoculars,
        "scored_at": datetime.now(UTC).isoformat(),
        "device_used": device,
        "transformers_version": transformers_version,
        "model_card_digest": hashlib.sha256(identity.encode()).hexdigest(),
    }


def _write_model_card(output_dir: Path, payload: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "model_card.json"
    existing: dict = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    if existing and existing.get("model_card_digest") != payload["model_card_digest"]:
        logger.warning(
            "Probability model_card.json digest mismatch (was=%s, now=%s) — "
            "scores across runs may not be comparable.",
            existing.get("model_card_digest"),
            payload["model_card_digest"],
        )
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _filter_articles(articles: list[Article]) -> list[Article]:
    keep: list[Article] = []
    for a in articles:
        if a.is_duplicate:
            continue
        if not a.clean_text:
            continue
        if a.word_count < 50:
            continue
        keep.append(a)
    return keep


def _transformers_version() -> str:
    try:
        import transformers  # type: ignore[import-not-found]
    except ImportError:
        return "unknown"
    return getattr(transformers, "__version__", "unknown")


def extract_probability_features(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    author_slug: str | None = None,
    include_binoculars: bool | None = None,
    device: str | None = None,
) -> int:
    """Score every article for perplexity / burstiness / Binoculars.

    Returns the number of articles scored.
    """
    cfg = settings.probability
    include_binoculars = (
        cfg.binoculars_enabled if include_binoculars is None else include_binoculars
    )
    device_cfg = device or (cfg.device if cfg.device != "auto" else None)

    init_db(db_path)
    repo = Repository(db_path)

    configured_slugs = [a.slug for a in settings.authors]
    if author_slug:
        if author_slug not in configured_slugs:
            raise ValueError(f"No configured author with slug {author_slug!r}")
        slugs = [author_slug]
    else:
        slugs = configured_slugs

    target_authors = []
    for slug in slugs:
        author = repo.get_author_by_slug(slug)
        if author is None:
            logger.warning(
                "probability: author %s not in articles.db (run `forensics scrape --discover`)",
                slug,
            )
            continue
        target_authors.append(author)

    model, tokenizer = load_reference_model(
        model_name=cfg.reference_model,
        revision=cfg.reference_model_revision,
        device=device_cfg,
    )
    resolved_device = str(next(model.parameters()).device)

    binoc = None
    if include_binoculars:
        binoc = load_binoculars_models(
            cfg.binoculars_model_base,
            cfg.binoculars_model_instruct,
            enabled=True,
            device=device_cfg,
        )

    output_dir = get_project_root() / "data" / "probability"
    _write_model_card(
        output_dir,
        _model_card_payload(
            settings,
            include_binoculars=bool(binoc),
            device=resolved_device,
            transformers_version=_transformers_version(),
        ),
    )

    total = 0
    for author in target_authors:
        articles = _filter_articles(repo.get_articles_by_author(author.id))
        if not articles:
            logger.info("probability: no eligible articles for author=%s", author.slug)
            continue

        rows: list[dict] = []
        for idx, article in enumerate(articles, start=1):
            ppl = compute_perplexity(
                article.clean_text,
                model,
                tokenizer,
                max_length=cfg.max_sequence_length,
                stride=cfg.sliding_window_stride,
                low_ppl_threshold=cfg.low_ppl_threshold,
            )
            bino: float | None = None
            if binoc is not None:
                model_base, model_inst, bino_tok = binoc
                bino = compute_binoculars_score(
                    article.clean_text,
                    model_base,
                    model_inst,
                    bino_tok,
                    max_length=min(cfg.max_sequence_length, 512),
                )

            rows.append(
                {
                    "article_id": article.id,
                    "author_id": article.author_id,
                    "publish_date": article.published_date.date(),
                    "mean_perplexity": ppl["mean_perplexity"],
                    "median_perplexity": ppl["median_perplexity"],
                    "perplexity_variance": ppl["perplexity_variance"],
                    "min_sentence_ppl": ppl["min_sentence_ppl"],
                    "max_sentence_ppl": ppl["max_sentence_ppl"],
                    "ppl_skewness": ppl["ppl_skewness"],
                    "low_ppl_sentence_ratio": ppl["low_ppl_sentence_ratio"],
                    "binoculars_score": bino,
                }
            )
            if idx % 25 == 0:
                logger.info(
                    "probability: %d/%d articles scored (%s)",
                    idx,
                    len(articles),
                    author.slug,
                )

        out_path = output_dir / f"{author.slug}.parquet"
        pl.DataFrame(rows).write_parquet(out_path)
        logger.info(
            "probability: wrote %d rows to %s (binoculars=%s)",
            len(rows),
            out_path,
            binoc is not None,
        )
        total += len(rows)

    return total
