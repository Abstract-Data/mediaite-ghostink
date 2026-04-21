"""Feature extraction for synthetic baseline JSON articles."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from forensics.baseline.generation import sanitize_model_name
from forensics.config.settings import ForensicsSettings
from forensics.features import content, lexical, pos_patterns, productivity, readability, structural
from forensics.models.features import FeatureVector
from forensics.utils.datetime import parse_datetime

logger = logging.getLogger(__name__)


def _cell_key(model_name: str, prompt_template: str, temperature: float) -> str:
    mode = "raw" if prompt_template == "raw_generation" else "mimicry"
    return f"{sanitize_model_name(model_name)}_{mode}_t{temperature}"


def extract_baseline_features(
    baseline_dir: Path,
    config: ForensicsSettings,
) -> dict[str, pl.DataFrame]:
    """Extract Phase-4-style features per model/temperature/mode group from JSON articles."""
    try:
        import spacy
    except ImportError as exc:  # pragma: no cover
        msg = "spaCy is required for baseline feature extraction"
        raise RuntimeError(msg) from exc

    nlp = spacy.load("en_core_web_md")
    features_root = baseline_dir / "features"
    features_root.mkdir(parents=True, exist_ok=True)

    buckets: dict[str, list[dict[str, Any]]] = {}

    skip_dirs = {"features", "eval_reports"}
    for author_dir in sorted(
        p for p in baseline_dir.iterdir() if p.is_dir() and p.name not in skip_dirs
    ):
        for json_path in sorted(author_dir.rglob("article_*.json")):
            try:
                rec = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                logger.warning("skip unreadable baseline json %s", json_path)
                continue
            if rec.get("dry_run"):
                continue
            model_name = str(rec.get("model", ""))
            pt = str(rec.get("prompt_template", "raw_generation"))
            temp = float(rec.get("temperature", 0.0))
            key = _cell_key(model_name, pt, temp)
            text = str(rec.get("text", ""))
            if len(text.split()) < 10:
                continue
            doc = nlp(text)
            lex = lexical.extract_lexical_features(text, doc)
            pos = pos_patterns.extract_pos_pattern_features(doc)
            struct = structural.extract_structural_features(text, doc)
            cont = content.extract_content_features(text, doc, [], [])
            pub = parse_datetime(str(rec.get("generated_at", ""))) or datetime.now(UTC)
            prod = productivity.extract_productivity_features(
                pub, int(rec.get("actual_word_count", 0)), []
            )
            read = readability.extract_readability_features(text)
            fv = FeatureVector(
                article_id=str(rec.get("article_id", json_path.stem)),
                author_id=f"baseline:{author_dir.name}",
                timestamp=pub,
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
            buckets.setdefault(key, []).append(fv.model_dump(mode="json"))

    out: dict[str, pl.DataFrame] = {}
    for key, rows in buckets.items():
        if not rows:
            continue
        df = pl.DataFrame(rows)
        path = features_root / f"{key}.parquet"
        df.write_parquet(path)
        out[key] = df
        logger.info("baseline features: wrote %s (%d rows)", path.name, df.height)

    _ = config  # reserved for embedding model alignment / probability hooks
    return out
