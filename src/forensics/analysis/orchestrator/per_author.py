"""Per-author analysis routines and test gating."""

from __future__ import annotations

import logging
from bisect import bisect_left
from collections import defaultdict, deque
from datetime import UTC, datetime
from datetime import time as dt_time
from uuid import uuid4

import numpy as np
import polars as pl

from forensics.analysis.changepoint import (
    analyze_author_feature_changepoints,
    write_imputation_stats_artifact,
)
from forensics.analysis.convergence import (
    ConvergenceInput,
    ProbabilityTrajectory,
    compute_convergence_scores,
)
from forensics.analysis.drift import (
    EmbeddingDriftInputsError,
    EmbeddingRevisionGateError,
    compute_author_drift_pipeline,
    load_article_embeddings,
)
from forensics.analysis.era import classify_ai_marker_era
from forensics.analysis.evidence import filter_evidence_change_points
from forensics.analysis.orchestrator.mode import DEFAULT_ANALYSIS_MODE, AnalysisMode
from forensics.analysis.orchestrator.timings import _StageTimer
from forensics.analysis.statistics import (
    apply_correction,
    apply_cross_author_correction,
    compute_n_rankable_features_per_family,
    filter_by_effect_size,
    run_hypothesis_tests,
)
from forensics.analysis.utils import pair_months_with_velocities
from forensics.config.settings import AnalysisConfig, ForensicsSettings
from forensics.models.analysis import AnalysisResult, ChangePoint, DriftScores
from forensics.models.features import strict_feature_decode_confirmatory
from forensics.paths import AnalysisArtifactPaths
from forensics.preregistration import (
    PREREGISTERED_FEATURES,
    PREREGISTERED_SPLIT_DATE,
    PREREGISTERED_TEST_PREFIXES,
)
from forensics.storage.json_io import stable_sort_artifact_list, write_json_artifact
from forensics.storage.parquet import load_feature_frame_sorted
from forensics.storage.repository import Repository
from forensics.utils.datetime import timestamps_from_frame
from forensics.utils.provenance import compute_analysis_config_hash

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


def _write_per_author_json_artifacts(
    slug: str,
    paths: AnalysisArtifactPaths,
    change_points: list[ChangePoint],
    convergence_windows: list,
    assembled: AnalysisResult,
    all_tests: list,
) -> None:
    # Phase 15 H2 — sort list-valued artifact bodies on the stable-tuple spec
    # so parallel and serial dispatch produce byte-identical JSON.
    write_json_artifact(
        paths.changepoints_json(slug),
        stable_sort_artifact_list(change_points, kind="change_points"),
    )
    write_json_artifact(
        paths.convergence_json(slug),
        stable_sort_artifact_list(convergence_windows, kind="convergence_windows"),
    )
    write_json_artifact(paths.result_json(slug), assembled)
    write_json_artifact(
        paths.hypothesis_tests_json(slug),
        stable_sort_artifact_list(all_tests, kind="hypothesis_tests"),
    )


def _clean_feature_series(df_author: pl.DataFrame, feature_name: str) -> list[float]:
    """Cast to float, median-impute non-finite values, and return a plain ``list[float]``.

    Hoisted out of :func:`_run_hypothesis_tests_for_changepoints` so the per-
    feature cleaning can be cached across multiple change-points on the same
    feature (Phase 15 F2) and so tests can monkeypatch this symbol to assert
    cache-hit behaviour.
    """
    col = pl.col(feature_name).cast(pl.Float64, strict=False)
    lf = df_author.lazy()
    med_scalar = lf.select(col.filter(col.is_finite()).median()).collect().item()
    med = 0.0 if med_scalar is None else float(med_scalar)
    cleaned = lf.select(
        pl.when(col.is_finite()).then(col).otherwise(pl.lit(med)).alias("_v")
    ).collect()["_v"]
    return [float(x) for x in cleaned.to_list()]


def _run_hypothesis_tests_for_changepoints(
    df_author: pl.DataFrame,
    timestamps: list[datetime],
    change_points: list[ChangePoint],
    author_id: str,
    analysis_cfg: AnalysisConfig,
) -> list:
    # Phase 15 F2: cache cleaned per-feature series so multiple CPs on the
    # same feature reuse one median-imputation pass instead of re-scanning
    # the dataframe each iteration.
    feature_cache: dict[str, tuple[list[float], int]] = {}
    all_tests: list = []
    for cp in change_points:
        if cp.feature_name not in df_author.columns:
            continue
        cached = feature_cache.get(cp.feature_name)
        if cached is None:
            series = _clean_feature_series(df_author, cp.feature_name)
            feature_cache[cp.feature_name] = (series, len(series))
        series, n = feature_cache[cp.feature_name]
        if n < 6 or n != len(timestamps):
            continue
        bidx = _breakpoint_index(timestamps, cp.timestamp)
        all_tests.extend(
            run_hypothesis_tests(
                series,
                bidx,
                cp.feature_name,
                author_id,
                n_bootstrap=analysis_cfg.hypothesis.bootstrap_iterations,
                bootstrap_seed=analysis_cfg.hypothesis.hypothesis_bootstrap_seed,
                enable_ks_test=analysis_cfg.hypothesis.enable_ks_test,
                hypothesis_min_segment_n=analysis_cfg.hypothesis.hypothesis_min_segment_n,
            )
        )
    return all_tests


def _run_preregistered_split_tests(
    df_author: pl.DataFrame,
    timestamps: list[datetime],
    author_id: str,
    analysis_cfg: AnalysisConfig,
) -> list:
    if not timestamps:
        return []
    split_dt = datetime.combine(PREREGISTERED_SPLIT_DATE, dt_time.min, tzinfo=UTC)
    split_idx = bisect_left([_ts_key(t) for t in timestamps], _ts_key(split_dt))
    all_tests: list = []
    allowed_prefixes = tuple(f"{prefix}_" for prefix in PREREGISTERED_TEST_PREFIXES)
    for feature in PREREGISTERED_FEATURES:
        if feature not in df_author.columns:
            continue
        raw = df_author[feature].cast(pl.Float64, strict=False).to_numpy()
        finite = raw[np.isfinite(raw)]
        if finite.size == 0:
            continue
        series = _clean_feature_series(df_author, feature)
        tests = run_hypothesis_tests(
            series,
            split_idx,
            feature,
            author_id,
            n_bootstrap=analysis_cfg.hypothesis.bootstrap_iterations,
            bootstrap_seed=analysis_cfg.hypothesis.hypothesis_bootstrap_seed,
            hypothesis_min_segment_n=analysis_cfg.hypothesis.hypothesis_min_segment_n,
        )
        all_tests.extend(test for test in tests if test.test_name.startswith(allowed_prefixes))
    return all_tests


def _apply_global_test_gates(
    tests_by_slug: dict[str, list],
    analysis_cfg: AnalysisConfig,
) -> dict[str, list]:
    labeled = [(slug, test) for slug, tests in tests_by_slug.items() for test in tests]
    if not labeled:
        return {slug: [] for slug in tests_by_slug}
    corrected = apply_correction(
        [test for _slug, test in labeled],
        method=analysis_cfg.hypothesis.multiple_comparison_method,
        alpha=analysis_cfg.hypothesis.significance_threshold,
    )
    by_slug: dict[str, list] = defaultdict(list)
    for (slug, _), t in zip(labeled, corrected, strict=True):
        by_slug[slug].append(t)
    if analysis_cfg.hypothesis.enable_cross_author_correction:
        by_slug = apply_cross_author_correction(dict(by_slug))
    queues = {slug: deque(tests) for slug, tests in by_slug.items()}
    corrected_in_order = [queues[slug].popleft() for slug, _ in labeled]
    gated = filter_by_effect_size(
        corrected_in_order,
        analysis_cfg.hypothesis.effect_size_threshold,
        alpha=analysis_cfg.hypothesis.significance_threshold,
    )
    grouped: dict[str, list] = {slug: [] for slug in tests_by_slug}
    for (slug, _test), gated_test in zip(labeled, gated, strict=True):
        grouped[slug].append(gated_test)
    return grouped


def _load_drift_signals(
    slug: str,
    author_id: str,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    mode: AnalysisMode = DEFAULT_ANALYSIS_MODE,
) -> tuple[
    DriftScores | None,
    list[tuple[datetime, float]],
    list[tuple[str, float]],
    list[tuple[str, float]] | None,
]:
    """Load embeddings and run the per-author drift pipeline.

    Extracted from :func:`_run_per_author_analysis` (Phase 15 G3) to keep the
    parent function under the McCabe complexity ceiling once per-stage
    timing brackets and the early-out ``return None`` paths are factored
    in. Returns ``(drift, baseline_curve, vel_tuples, ai_conv)`` with
    permissive defaults (empty lists / ``None``) when embeddings are
    unavailable and ``mode.exploratory`` is true; confirmatory runs raise
    ``EmbeddingDriftInputsError`` instead.
    """
    baseline_curve: list[tuple[datetime, float]] = []
    vel_tuples: list[tuple[str, float]] = []
    ai_conv: list[tuple[str, float]] | None = None
    drift: DriftScores | None = None

    try:
        pairs = load_article_embeddings(
            slug,
            paths,
            expected_revision=config.analysis.embedding.embedding_model_revision,
            mode=mode,
        )
    except EmbeddingRevisionGateError:
        raise
    except (ValueError, OSError) as exc:
        if mode.exploratory:
            logger.info("analysis: no embeddings for %s (%s)", slug, exc)
            pairs = []
        else:
            raise EmbeddingDriftInputsError(
                f"Cannot load article embeddings for analysis (author={slug!r})."
            ) from exc

    if not mode.exploratory and len(pairs) < 2:
        raise EmbeddingDriftInputsError(
            "Insufficient article embeddings for drift in analysis "
            f"(author={slug!r}): need at least 2 usable vectors, got {len(pairs)}."
        )

    drift_res = compute_author_drift_pipeline(
        slug,
        author_id,
        pairs,
        config,
        paths=paths,
    )
    if drift_res is not None:
        drift = drift_res.drift_scores
        baseline_curve = drift_res.baseline_curve
        ai_conv = drift_res.ai_convergence
        vel_tuples = pair_months_with_velocities(drift_res.monthly_centroids, drift_res.velocities)
    return drift, baseline_curve, vel_tuples, ai_conv


def assemble_analysis_result(
    author_id: str,
    change_points: list[ChangePoint],
    convergence_windows: list,
    drift_scores: DriftScores | None,
    hypothesis_tests: list,
    settings: ForensicsSettings,
) -> AnalysisResult:
    """Build ``AnalysisResult`` with a short deterministic hash of analysis settings."""
    config_hash = compute_analysis_config_hash(settings)
    return AnalysisResult(
        author_id=author_id,
        run_id=str(uuid4()),
        run_timestamp=datetime.now(UTC),
        config_hash=config_hash,
        change_points=change_points,
        convergence_windows=convergence_windows,
        drift_scores=drift_scores,
        hypothesis_tests=hypothesis_tests,
        era_classification=classify_ai_marker_era(change_points),
    )


def _run_per_author_analysis(
    slug: str,
    repo: Repository,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    probability_trajectory_by_slug: dict[str, ProbabilityTrajectory],
    stage_timings: dict[str, float] | None = None,
    mode: AnalysisMode = DEFAULT_ANALYSIS_MODE,
) -> tuple[AnalysisResult, list[ChangePoint], list, list] | None:
    """Changepoint, drift, convergence, and hypothesis testing for one author slug.

    When ``stage_timings`` is provided, the per-stage wall-clock seconds are
    written into the dict (keys: ``extract``, ``changepoint``, ``drift``,
    ``convergence``, ``hypothesis_tests``) so the bench script can emit
    non-zero per-stage measurements instead of only the grand ``total``.
    """
    with strict_feature_decode_confirmatory(mode.exploratory):
        author = repo.get_author_by_slug(slug)
        if author is None:
            logger.warning("analysis: unknown slug=%s", slug)
            return None
        feat_path = paths.features_parquet(slug)
        if not feat_path.is_file():
            logger.warning("analysis: skip %s (missing %s)", slug, feat_path)
            return None

        timer = _StageTimer(stage_timings)
        lf_all = load_feature_frame_sorted(feat_path)
        lf_author = lf_all.filter(pl.col("author_id") == author.id)
        df_author = lf_author.collect()
        if df_author.is_empty():
            logger.warning(
                "per_author frame empty after filter; skipping author",
                extra={"author_slug": author.slug, "author_id": author.id},
            )
            return None
        min_w = int(config.analysis.analysis_min_word_count)
        if min_w > 0 and "word_count" in df_author.columns:
            before = int(df_author.height)
            df_author = df_author.filter(pl.col("word_count") >= min_w)
            after = int(df_author.height)
            if after < before:
                logger.info(
                    "analysis: slug=%s dropped %d article(s) below analysis_min_word_count=%d",
                    slug,
                    before - after,
                    min_w,
                )
        timer.record("extract")

        write_imputation_stats_artifact(
            paths.imputation_stats_json(slug),
            df_author,
            author_id=author.id,
            settings=config,
        )
        raw_change_points = analyze_author_feature_changepoints(
            df_author,
            author_id=author.id,
            settings=config,
        )
        change_points = filter_evidence_change_points(raw_change_points, config.analysis)
        timer.record("changepoint")

        drift, baseline_curve, vel_tuples, ai_conv = _load_drift_signals(
            slug,
            author.id,
            paths,
            config,
            mode=mode,
        )
        timer.record("drift")

        timestamps = timestamps_from_frame(df_author)
        all_tests = _run_hypothesis_tests_for_changepoints(
            df_author,
            timestamps,
            change_points,
            author.id,
            config.analysis,
        )
        all_tests.extend(
            _run_preregistered_split_tests(
                df_author,
                timestamps,
                author.id,
                config.analysis,
            )
        )
        timer.record("hypothesis_tests")

        prob = probability_trajectory_by_slug.get(slug)
        n_rankable = compute_n_rankable_features_per_family(all_tests)
        convergence_windows = compute_convergence_scores(
            ConvergenceInput.from_settings(
                change_points,
                vel_tuples,
                baseline_curve,
                config,
                ai_convergence_curve=ai_conv,
                probability_trajectory=prob,
                n_rankable_per_family=n_rankable,
                article_timestamps=timestamps,
            ),
            components_artifact_path=paths.convergence_components_json(slug),
            author_slug=slug,
        )
        timer.record("convergence")

        assembled = assemble_analysis_result(
            author.id,
            change_points,
            convergence_windows,
            drift,
            all_tests,
            config,
        )
        return assembled, change_points, convergence_windows, all_tests
