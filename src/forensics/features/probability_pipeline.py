"""Orchestration for probability / Binoculars extraction (Phase 9)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from forensics.config import get_project_root
from forensics.config.settings import ForensicsSettings, ProbabilityConfig
from forensics.features import binoculars as binoc_mod
from forensics.features import probability as prob_mod
from forensics.storage.repository import Repository, init_db

logger = logging.getLogger(__name__)

_MODEL_CARD_FILENAME = "model_card.json"


def probability_stack_available() -> bool:
    try:
        import torch  # noqa: F401
        from transformers import AutoModelForCausalLM  # noqa: F401
    except ImportError:
        return False
    return True


def _resolve_torch_device(cfg: ProbabilityConfig, override: str | None) -> Any:
    import torch

    if override:
        return torch.device(override)
    if cfg.device == "cpu":
        return torch.device("cpu")
    if cfg.device == "cuda":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # auto
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _expected_model_card(settings: ForensicsSettings) -> dict[str, Any]:
    import transformers

    p = settings.probability
    return {
        "reference_model": p.reference_model,
        "reference_model_revision": p.reference_model_revision,
        "reference_model_sha256": "",
        "binoculars_base": p.binoculars_model_base,
        "binoculars_instruct": p.binoculars_model_instruct,
        "transformers_version": getattr(transformers, "__version__", "unknown"),
    }


def _read_model_card(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _model_card_matches_disk(settings: ForensicsSettings, card_path: Path) -> bool:
    expected = _expected_model_card(settings)
    existing = _read_model_card(card_path)
    if not existing:
        return True
    keys = (
        "reference_model",
        "reference_model_revision",
        "binoculars_base",
        "binoculars_instruct",
    )
    for k in keys:
        if existing.get(k) != expected.get(k):
            logger.warning(
                "Probability model_card.json does not match config.toml for %s "
                "(existing=%r config=%r). Scores are not comparable across model versions; "
                "re-score the full corpus after aligning config or delete %s.",
                k,
                existing.get(k),
                expected.get(k),
                card_path,
            )
            return False
    return True


def _write_model_card(settings: ForensicsSettings, card_path: Path, device_used: str) -> None:
    card_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _expected_model_card(settings)
    payload["scored_at"] = datetime.now(UTC).isoformat()
    payload["device_used"] = device_used
    card_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_reference_lm(
    cfg: ProbabilityConfig,
    device: Any,
) -> tuple[Any, Any]:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(
        cfg.reference_model,
        revision=cfg.reference_model_revision or None,
    )
    model = AutoModelForCausalLM.from_pretrained(
        cfg.reference_model,
        revision=cfg.reference_model_revision or None,
    )
    model.to(device)
    model.eval()
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return model, tok


def load_reference_language_model(
    settings: ForensicsSettings | None = None,
    *,
    device_override: str | None = None,
) -> tuple[Any, Any]:
    """Load the configured reference causal LM and tokenizer (requires torch + transformers)."""
    from forensics.config import get_settings

    s = settings or get_settings()
    device = _resolve_torch_device(s.probability, device_override)
    return _load_reference_lm(s.probability, device)


def extract_probability_features(
    db_path: Path,
    settings: ForensicsSettings,
    *,
    author_slug: str | None = None,
    no_binoculars: bool = False,
    device_override: str | None = None,
    project_root: Path | None = None,
) -> int:
    """Score perplexity / burstiness (and optionally Binoculars) for eligible articles.

    Writes ``data/probability/{author_slug}.parquet`` and ``data/probability/model_card.json``.
    """
    if not probability_stack_available():
        logger.error(
            "Probability features need torch and transformers. Install with: "
            "`uv sync --extra dev` (or `uv sync --extra probability`), then re-run."
        )
        return 0

    init_db(db_path)
    root = project_root or get_project_root()
    if db_path.name == "articles.db" and db_path.parent.name == "data":
        root = db_path.parent.parent
    prob_dir = root / "data" / "probability"
    prob_dir.mkdir(parents=True, exist_ok=True)
    card_path = prob_dir / _MODEL_CARD_FILENAME

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
        logger.info("No articles eligible for probability scoring.")
        return 0

    device = _resolve_torch_device(settings.probability, device_override)
    _model_card_matches_disk(settings, card_path)

    cfg = settings.probability
    model, tokenizer = _load_reference_lm(cfg, device)
    device_str = str(device)

    binoc_models = None
    if not no_binoculars:
        binoc_models = binoc_mod.load_binoculars_models(cfg, device=device)

    by_author: dict[str, list] = defaultdict(list)
    for a in articles:
        by_author[a.author_id].append(a)

    total = sum(len(v) for v in by_author.values())
    processed = 0

    for author_id, seq in by_author.items():
        author = repo.get_author(author_id)
        slug = author.slug if author else author_id
        author_name = author.name if author else author_id
        rows: list[dict[str, Any]] = []

        for article in seq:
            processed += 1
            if processed == 1 or processed % 50 == 0 or processed == total:
                logger.info(
                    "Scoring probability features: %d/%d articles (%s)",
                    processed,
                    total,
                    author_name,
                )
            metrics = prob_mod.compute_perplexity(
                article.clean_text,
                model,
                tokenizer,
                max_length=cfg.max_sequence_length,
                stride=cfg.stride,
                low_ppl_threshold=cfg.low_ppl_sentence_threshold,
                device=device,
            )
            b_score: float | None = None
            if binoc_models is not None:
                base_m, inst_m, btok = binoc_models
                try:
                    b_score = float(
                        binoc_mod.compute_binoculars_score(
                            article.clean_text,
                            base_m,
                            inst_m,
                            btok,
                            max_length=min(512, cfg.max_sequence_length),
                            device=device,
                        )
                    )
                except Exception:
                    logger.exception("Binoculars scoring failed for article %s", article.id)
                    b_score = None

            rows.append(
                {
                    "article_id": article.id,
                    "author_id": article.author_id,
                    "publish_date": article.published_date.date().isoformat(),
                    "mean_perplexity": metrics["mean_perplexity"],
                    "median_perplexity": metrics["median_perplexity"],
                    "perplexity_variance": metrics["perplexity_variance"],
                    "min_sentence_ppl": metrics["min_sentence_ppl"],
                    "max_sentence_ppl": metrics["max_sentence_ppl"],
                    "ppl_skewness": metrics["ppl_skewness"],
                    "low_ppl_sentence_ratio": metrics["low_ppl_sentence_ratio"],
                    "binoculars_score": b_score,
                }
            )

        if rows:
            out = prob_dir / f"{slug}.parquet"
            pl.DataFrame(rows).write_parquet(out)

    _write_model_card(settings, card_path, device_str)
    logger.info("Probability extraction finished: %d article(s) processed.", processed)
    return processed


def maybe_log_probability_hint() -> None:
    """Log install / download guidance when the optional stack is missing."""
    if probability_stack_available():
        return
    logger.info(
        "Probability features require torch, transformers, and downloading gpt2 (~500MB). "
        "Install extras then run `uv run forensics extract --probability` to score."
    )
