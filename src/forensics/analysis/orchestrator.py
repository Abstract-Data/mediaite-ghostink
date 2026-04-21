"""Phase 7 orchestration: assemble ``AnalysisResult`` and run full multi-author analysis."""

from __future__ import annotations

import hashlib
import json
import logging
from bisect import bisect_left
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import polars as pl

from forensics.analysis.changepoint import (
    analyze_author_feature_changepoints,
)
from forensics.analysis.comparison import compare_target_to_controls
from forensics.analysis.convergence import ProbabilityTrajectory, compute_convergence_scores
from forensics.analysis.drift import compute_author_drift_pipeline, load_article_embeddings
from forensics.analysis.statistics import (
    apply_correction,
    filter_by_effect_size,
    run_hypothesis_tests,
)
from forensics.config.settings import AnalysisConfig, ForensicsSettings
from forensics.models.analysis import AnalysisResult, ChangePoint, DriftScores
from forensics.storage.parquet import load_feature_frame_sorted
from forensics.storage.repository import Repository, init_db
from forensics.utils.datetime import parse_datetime
from forensics.utils.provenance import write_corpus_custody

logger = logging.getLogger(__name__)


def _ts_key(t: datetime) -> float:
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.timestamp()


def _breakpoint_index(timestamps: list[datetime], event: datetime) -> int:
    keys = [_ts_key(t) for t in timestamps]
    x = _ts_key(event)
    i = bisect_left(keys, x)
    return max(1, min(len(timestamps) - 1, i))


def assemble_analysis_result(
    author_id: str,
    change_points: list[ChangePoint],
    convergence_windows: list,
    drift_scores: DriftScores | None,
    hypothesis_tests: list,
    config: AnalysisConfig,
) -> AnalysisResult:
    """Build ``AnalysisResult`` with a short deterministic hash of analysis settings."""
    payload = config.model_dump(mode="json", round_trip=True)
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    config_hash = hashlib.sha256(raw).hexdigest()[:16]
    return AnalysisResult(
        author_id=author_id,
        run_id=str(uuid4()),
        run_timestamp=datetime.now(UTC),
        config_hash=config_hash,
        change_points=change_points,
        convergence_windows=convergence_windows,
        drift_scores=drift_scores,
        hypothesis_tests=hypothesis_tests,
    )


async def run_full_analysis(
    db_path: Path,
    features_dir: Path,
    embeddings_dir: Path,
    config: ForensicsSettings,
    *,
    project_root: Path,
    author_slug: str | None = None,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory] | None = None,
) -> dict[str, AnalysisResult]:
    """Run changepoint + drift + convergence + hypothesis tests; write JSON artifacts."""
    init_db(db_path)
    analysis_dir = project_root / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    slugs = [author_slug] if author_slug else [a.slug for a in config.authors]
    prob_map = probability_trajectory_by_slug or {}

    results: dict[str, AnalysisResult] = {}

    with Repository(db_path) as repo:
        for slug in slugs:
            author = repo.get_author_by_slug(slug)
            if author is None:
                logger.warning("analysis: unknown slug=%s", slug)
                continue
            feat_path = features_dir / f"{slug}.parquet"
            if not feat_path.is_file():
                logger.warning("analysis: skip %s (missing %s)", slug, feat_path)
                continue

            df = load_feature_frame_sorted(feat_path)
            df_author = df.filter(pl.col("author_id") == author.id)
            if df_author.is_empty():
                df_author = df

            change_points = analyze_author_feature_changepoints(
                df_author,
                author_id=author.id,
                settings=config,
            )

            baseline_curve: list[tuple[datetime, float]] = []
            vel_tuples: list[tuple[str, float]] = []
            ai_conv: list[tuple[str, float]] | None = None
            drift: DriftScores | None = None

            try:
                pairs = load_article_embeddings(
                    slug,
                    embeddings_dir,
                    db_path,
                    project_root=project_root,
                )
            except (ValueError, OSError) as exc:
                logger.info("analysis: no embeddings for %s (%s)", slug, exc)
                pairs = []

            drift_res = compute_author_drift_pipeline(
                slug,
                author.id,
                pairs,
                config,
                project_root=project_root,
                analysis_dir=analysis_dir,
            )
            if drift_res is not None:
                monthly, drift, _umap, baseline_curve, vels, ai_conv = drift_res
                vel_tuples = [(monthly[i + 1][0], vels[i]) for i in range(len(vels))]

            prob = prob_map.get(slug)
            convergence_windows = compute_convergence_scores(
                change_points,
                vel_tuples,
                baseline_curve,
                ai_convergence_curve=ai_conv,
                probability_trajectory=prob,
                settings=config,
            )

            ts_list = df_author["timestamp"].to_list()
            timestamps = [parse_datetime(t) for t in ts_list]

            all_tests: list = []
            for cp in change_points:
                if cp.feature_name not in df_author.columns:
                    continue
                raw = df_author[cp.feature_name].cast(pl.Float64, strict=False).to_numpy()
                med = (
                    float(np.nanmedian(raw[np.isfinite(raw)])) if np.any(np.isfinite(raw)) else 0.0
                )
                raw = np.nan_to_num(raw, nan=med)
                series = [float(x) for x in raw]
                if len(series) < 6 or len(series) != len(timestamps):
                    continue
                bidx = _breakpoint_index(timestamps, cp.timestamp)
                all_tests.extend(
                    run_hypothesis_tests(
                        series,
                        bidx,
                        cp.feature_name,
                        author.id,
                        n_bootstrap=config.analysis.bootstrap_iterations,
                    )
                )

            apply_correction(
                all_tests,
                method=config.analysis.multiple_comparison_method,
                alpha=config.analysis.significance_threshold,
            )
            filter_by_effect_size(
                all_tests,
                config.analysis.effect_size_threshold,
                alpha=config.analysis.significance_threshold,
            )

            assembled = assemble_analysis_result(
                author.id,
                change_points,
                convergence_windows,
                drift,
                all_tests,
                config.analysis,
            )
            results[slug] = assembled

            (analysis_dir / f"{slug}_changepoints.json").write_text(
                json.dumps(
                    [c.model_dump(mode="json") for c in change_points], indent=2, default=str
                ),
                encoding="utf-8",
            )
            conv_payload = [w.model_dump(mode="json") for w in convergence_windows]
            (analysis_dir / f"{slug}_convergence.json").write_text(
                json.dumps(conv_payload, indent=2, default=str),
                encoding="utf-8",
            )
            (analysis_dir / f"{slug}_result.json").write_text(
                assembled.model_dump_json(indent=2),
                encoding="utf-8",
            )
            (analysis_dir / f"{slug}_hypothesis_tests.json").write_text(
                json.dumps([t.model_dump(mode="json") for t in all_tests], indent=2, default=str),
                encoding="utf-8",
            )
            logger.info(
                "analysis: author=%s change_points=%d windows=%d tests=%d",
                slug,
                len(change_points),
                len(convergence_windows),
                len(all_tests),
            )

    comparison_payload: dict[str, Any] = {"targets": {}}
    controls = [a.slug for a in config.authors if a.role == "control"]
    targets = [a.slug for a in config.authors if a.role == "target"]
    if author_slug:
        targets = [author_slug] if author_slug in targets else targets

    for tid in targets:
        if tid not in results:
            continue
        try:
            report = compare_target_to_controls(
                tid,
                controls,
                features_dir,
                db_path,
                settings=config,
                analysis_dir=analysis_dir,
                embeddings_dir=embeddings_dir,
                project_root=project_root,
            )
            comparison_payload["targets"][tid] = report
        except (ValueError, OSError) as exc:
            logger.warning("analysis: comparison failed for %s (%s)", tid, exc)

    (analysis_dir / "comparison_report.json").write_text(
        json.dumps(comparison_payload, indent=2, default=str),
        encoding="utf-8",
    )

    meta_path = analysis_dir / "run_metadata.json"
    if meta_path.is_file():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = {}
    else:
        prev = {}
    prev.update(
        {
            "full_analysis_authors": list(results.keys()),
            "comparison_targets": list(comparison_payload["targets"].keys()),
            "completed_at": datetime.now(UTC).isoformat(),
        }
    )
    meta_path.write_text(json.dumps(prev, indent=2), encoding="utf-8")

    write_corpus_custody(db_path, analysis_dir)

    return results


def run_compare_only(
    config: ForensicsSettings,
    *,
    project_root: Path,
    db_path: Path,
    author_slug: str | None = None,
) -> dict[str, Any]:
    """Regenerate ``comparison_report.json`` from on-disk artifacts."""
    init_db(db_path)
    features_dir = project_root / "data" / "features"
    embeddings_dir = project_root / "data" / "embeddings"
    analysis_dir = project_root / "data" / "analysis"
    controls = [a.slug for a in config.authors if a.role == "control"]
    targets = [a.slug for a in config.authors if a.role == "target"]
    if author_slug:
        targets = [author_slug] if author_slug in targets else [author_slug]
    out: dict[str, Any] = {"targets": {}}
    for tid in targets:
        try:
            out["targets"][tid] = compare_target_to_controls(
                tid,
                controls,
                features_dir,
                db_path,
                settings=config,
                analysis_dir=analysis_dir,
                embeddings_dir=embeddings_dir,
                project_root=project_root,
            )
        except (ValueError, OSError) as exc:
            logger.warning("compare-only: failed for %s (%s)", tid, exc)
    report_path = analysis_dir / "comparison_report.json"
    report_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out
