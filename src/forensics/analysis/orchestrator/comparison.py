"""Target/control comparison orchestration."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from forensics.analysis.comparison import compare_target_to_controls
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import AnalysisResult, ChangePoint
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.json_io import write_json_artifact
from forensics.utils.provenance import validate_analysis_result_config_hashes

logger = logging.getLogger(__name__)


def _resolve_targets_and_controls(
    config: ForensicsSettings,
    author_slug: str | None,
    *,
    compare_pair: tuple[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """Resolve target/control slug lists; ``compare_pair`` overrides role-based targets."""
    if compare_pair is not None:
        target_slug, control_slug = compare_pair
        return [target_slug], [control_slug]
    controls = [a.slug for a in config.authors if a.role == "control"]
    targets = [a.slug for a in config.authors if a.role == "target"]
    if author_slug:
        targets = [author_slug] if author_slug in targets else targets
    return targets, controls


def _validate_compare_artifact_hashes(
    targets: list[str],
    controls: list[str],
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
) -> None:
    author_slugs = sorted(set(targets) | set(controls))
    ok, msg = validate_analysis_result_config_hashes(config, paths.analysis_dir, author_slugs)
    if not ok:
        raise ValueError(msg)


def _iter_compare_targets(
    targets: list[str],
    controls: list[str],
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    *,
    changepoints_memory: dict[str, list[ChangePoint]] | None,
    log_prefix: str,
    exploratory: bool = False,
) -> Iterator[tuple[str, dict[str, Any]]]:
    for tid in targets:
        try:
            report = compare_target_to_controls(
                tid,
                controls,
                paths,
                settings=config,
                changepoints_memory=changepoints_memory,
                exploratory=exploratory,
            )
        except (ValueError, OSError) as exc:
            logger.warning("%s failed for %s (%s)", log_prefix, tid, exc)
            continue
        yield tid, report


def _run_target_control_comparisons(
    targets: list[str],
    controls: list[str],
    results: dict[str, AnalysisResult],
    *,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
    exploratory: bool = False,
) -> dict[str, Any]:
    comparison_payload: dict[str, Any] = {"targets": {}}
    active_targets = [target for target in targets if target in results]
    if active_targets:
        _validate_compare_artifact_hashes(active_targets, controls, paths, config)
    changepoints_memory = {slug: list(res.change_points) for slug, res in results.items()}
    for tid, report in _iter_compare_targets(
        active_targets,
        controls,
        paths,
        config,
        changepoints_memory=changepoints_memory,
        log_prefix="analysis: comparison",
        exploratory=exploratory,
    ):
        comparison_payload["targets"][tid] = report
    return comparison_payload


def run_compare_only(
    config: ForensicsSettings,
    *,
    paths: AnalysisArtifactPaths,
    author_slug: str | None = None,
    compare_pair: tuple[str, str] | None = None,
    exploratory: bool = False,
) -> dict[str, Any]:
    """Rebuild ``comparison_report.json`` from on-disk artifacts.

    ``compare_pair`` or ``author_slug`` may override configured author roles.
    """
    if compare_pair is not None:
        targets, controls = _resolve_targets_and_controls(
            config,
            author_slug=None,
            compare_pair=compare_pair,
        )
    else:
        targets, controls = _resolve_targets_and_controls(config, author_slug)
        if author_slug and author_slug not in targets:
            logger.warning(
                "compare-only: author_slug=%r is not a configured target; "
                "forcing single-slug comparison (controls are still loaded from config)",
                author_slug,
            )
            targets = [author_slug]
    _validate_compare_artifact_hashes(targets, controls, paths, config)
    out: dict[str, Any] = {"targets": {}}
    for tid, report in _iter_compare_targets(
        targets,
        controls,
        paths,
        config,
        changepoints_memory=None,
        log_prefix="compare-only",
        exploratory=exploratory,
    ):
        out["targets"][tid] = report
    if not out.get("targets"):
        logger.warning(
            "comparison_report: empty targets after compare-only — no comparisons written (L-02)"
        )
    write_json_artifact(paths.comparison_report_json(), out)
    return out
