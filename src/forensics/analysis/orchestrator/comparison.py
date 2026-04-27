"""Target/control comparison orchestration."""

from __future__ import annotations

import logging
from typing import Any

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.comparison import compare_target_to_controls
from forensics.config.settings import ForensicsSettings
from forensics.models.analysis import AnalysisResult
from forensics.storage.json_io import write_json_artifact
from forensics.utils.provenance import validate_analysis_result_config_hashes

logger = logging.getLogger(__name__)


def _resolve_targets_and_controls(
    config: ForensicsSettings,
    author_slug: str | None,
    *,
    compare_pair: tuple[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """Resolve the target and control slug lists for the comparison stage.

    When ``compare_pair`` is provided as ``(target_slug, control_slug)`` the
    explicit pair takes precedence over ``settings.authors`` role assignments
    so operators can pin a one-off comparison without editing ``config.toml``.
    """
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


def _run_target_control_comparisons(
    targets: list[str],
    controls: list[str],
    results: dict[str, AnalysisResult],
    *,
    paths: AnalysisArtifactPaths,
    config: ForensicsSettings,
) -> dict[str, Any]:
    comparison_payload: dict[str, Any] = {"targets": {}}
    active_targets = [target for target in targets if target in results]
    if active_targets:
        _validate_compare_artifact_hashes(active_targets, controls, paths, config)
    changepoints_memory = {slug: list(res.change_points) for slug, res in results.items()}
    for tid in active_targets:
        try:
            report = compare_target_to_controls(
                tid,
                controls,
                paths,
                settings=config,
                changepoints_memory=changepoints_memory,
            )
            comparison_payload["targets"][tid] = report
        except (ValueError, OSError) as exc:
            logger.warning("analysis: comparison failed for %s (%s)", tid, exc)
    return comparison_payload


def run_compare_only(
    config: ForensicsSettings,
    *,
    paths: AnalysisArtifactPaths,
    author_slug: str | None = None,
    compare_pair: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Regenerate ``comparison_report.json`` from on-disk artifacts.

    When ``compare_pair`` is supplied as ``(target_slug, control_slug)`` the
    explicit pair takes precedence over both ``author_slug`` and the
    configured author roles, so operators can pin a one-off comparison
    without editing ``config.toml``.

    When ``author_slug`` is provided (and ``compare_pair`` is not), the
    caller always wants that single author compared even if it isn't in the
    configured target list (matches the pre-Phase-13 CLI contract). A warning
    is logged so the ambiguity surfaces in the operator's logs.
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
    for tid in targets:
        try:
            out["targets"][tid] = compare_target_to_controls(
                tid,
                controls,
                paths,
                settings=config,
            )
        except (ValueError, OSError) as exc:
            logger.warning("compare-only: failed for %s (%s)", tid, exc)
    if not out.get("targets"):
        logger.warning(
            "comparison_report: empty targets after compare-only — no comparisons written (L-02)"
        )
    write_json_artifact(paths.comparison_report_json(), out)
    return out
