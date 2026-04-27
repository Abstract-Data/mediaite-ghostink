"""Quarto book rendering for forensic notebooks."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from forensics.config import (
    DEFAULT_DB_RELATIVE,
    ForensicsSettings,
    get_project_root,
    get_settings,
)
from forensics.models.analysis import AnalysisResult
from forensics.models.report_args import ReportArgs
from forensics.paths import AnalysisArtifactPaths
from forensics.preregistration import verify_preregistration
from forensics.reporting.narrative import generate_evidence_narrative
from forensics.storage.json_io import ensure_dir, write_text_atomic
from forensics.storage.repository import Repository
from forensics.survey.scoring import compute_composite_score
from forensics.utils.provenance import validate_analysis_result_config_hashes, verify_corpus_hash

logger = logging.getLogger(__name__)
_MAX_EVIDENCE_ROWS = 50


def _analysis_artifacts_ok(
    settings: ForensicsSettings,
    analysis_dir: Path,
    author_slugs: list[str] | None = None,
) -> tuple[bool, str]:
    if author_slugs is None:
        author_slugs = [a.slug for a in settings.authors]
    return validate_analysis_result_config_hashes(settings, analysis_dir, author_slugs)


def _artifact_slugs(analysis_dir: Path) -> list[str]:
    return sorted(
        path.name.removesuffix("_result.json") for path in analysis_dir.glob("*_result.json")
    )


def _per_author_slugs(
    settings: ForensicsSettings,
    analysis_dir: Path,
    author_slug: str | None,
) -> list[str]:
    if author_slug:
        return [author_slug]
    artifact_slugs = _artifact_slugs(analysis_dir)
    configured = [author.slug for author in settings.authors if author.slug in artifact_slugs]
    return configured if configured else artifact_slugs


def _legacy_db_artifact_ok(root: Path) -> tuple[bool, str]:
    legacy_db = root / "data" / "forensics.db"
    if legacy_db.is_file() and legacy_db.stat().st_size == 0:
        return False, f"Remove zero-byte legacy SQLite artifact before reporting: {legacy_db}"
    return True, ""


def _quarto_bin() -> str | None:
    return shutil.which("quarto")


def resolve_notebook_path(root: Path, nb: str) -> Path | None:
    """Resolve ``05`` / ``05_change_point_detection.ipynb`` to a path under ``notebooks/``."""
    s = nb.strip()
    if s.isdigit():
        matches = sorted((root / "notebooks").glob(f"{int(s):02d}_*.ipynb"))
        return matches[0] if matches else None
    candidate = root / "notebooks" / s
    if candidate.is_file():
        return candidate
    alt = root / s
    return alt if alt.is_file() else None


def _prepare_report_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _validate_report_prerequisites(
    settings: ForensicsSettings,
    root: Path,
    args: ReportArgs,
) -> tuple[bool, int, str | None]:
    """Return ``(ok, exit_code, quarto_path)``; ``quarto_path`` is set only when ``ok``."""
    analysis_dir = root / "data" / "analysis"
    author_slug = getattr(args, "author_slug", None)
    slugs = (
        _per_author_slugs(settings, analysis_dir, author_slug)
        if bool(getattr(args, "per_author", False))
        else None
    )
    ok, msg = _analysis_artifacts_ok(settings, analysis_dir, slugs)
    if not ok:
        logger.error("report: %s", msg)
        return False, 1, None
    ok, msg = _legacy_db_artifact_ok(root)
    if not ok:
        logger.error("report: %s", msg)
        return False, 1, None

    if bool(getattr(args, "verify", False)):
        db_path = root / DEFAULT_DB_RELATIVE
        v_ok, v_msg = verify_corpus_hash(db_path, analysis_dir)
        if not v_ok:
            logger.error("report --verify failed: %s", v_msg)
            return False, 1, None
        logger.info("report --verify: %s", v_msg)

    quarto = _quarto_bin()
    if quarto is None:
        logger.error("report: quarto executable not found on PATH")
        return False, 1, None
    return True, 0, quarto


def _render_notebook_chapter(
    quarto: str,
    root: Path,
    reports_dir: Path,
    nb: str,
    fmt: str,
    env: dict[str, str],
) -> int:
    target = resolve_notebook_path(root, nb)
    if target is None:
        logger.error("report: notebook not found: %s", nb)
        return 1
    cmd = [quarto, "render", str(target), "--output-dir", str(reports_dir)]
    if fmt != "both":
        cmd.extend(["--to", fmt])
    logger.info("report: running %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=root, env=env, check=False)
    return int(proc.returncode)


def _render_full_book(
    quarto: str,
    root: Path,
    reports_dir: Path,
    fmt: str,
    env: dict[str, str],
) -> int:
    if fmt == "both":
        cmds = [
            [quarto, "render", "--output-dir", str(reports_dir), "--to", "html"],
            [quarto, "render", "--output-dir", str(reports_dir), "--to", "pdf"],
        ]
    else:
        cmds = [[quarto, "render", "--output-dir", str(reports_dir), "--to", fmt]]

    for cmd in cmds:
        logger.info("report: running %s", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=root, env=env, check=False)
        if proc.returncode != 0:
            return int(proc.returncode)
    return 0


def _load_analysis_result(paths: AnalysisArtifactPaths, slug: str) -> AnalysisResult:
    path = paths.result_json(slug)
    return AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))


def _load_sensitivity_summary(paths: AnalysisArtifactPaths) -> dict[str, Any]:
    path = paths.sensitivity_dir("section_residualized") / "sensitivity_summary.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _author_article_links(
    paths: AnalysisArtifactPaths,
    slug: str,
    analysis: AnalysisResult,
) -> list[str]:
    if not paths.db_path.is_file():
        return []
    event = min((cp.timestamp for cp in analysis.change_points), default=None)
    with Repository(paths.db_path) as repo:
        author = repo.get_author_by_slug(slug)
        if author is None:
            return []
        articles = list(repo.iter_articles_by_author(author.id))
    if not articles:
        return []
    if event is None:
        selected = [articles[0], articles[-1]] if len(articles) > 1 else [articles[0]]
    else:
        before = [a for a in articles if a.published_date <= event]
        after = [a for a in articles if a.published_date >= event]
        selected = []
        if before:
            selected.append(before[-1])
        if after and (not selected or after[0].id != selected[0].id):
            selected.append(after[0])
    return [
        f"- {article.published_date.date().isoformat()}: [{article.title}]({article.url})"
        for article in selected
    ]


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None._"
    sep = ["---" for _ in headers]
    rendered = ["| " + " | ".join(headers) + " |", "| " + " | ".join(sep) + " |"]
    rendered.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(rendered)


def _limited_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if len(rows) <= _MAX_EVIDENCE_ROWS:
        return _markdown_table(headers, rows)
    shown = rows[:_MAX_EVIDENCE_ROWS]
    return (
        _markdown_table(headers, shown)
        + f"\n\n_Showing first {_MAX_EVIDENCE_ROWS} of {len(rows)} rows._"
    )


def _change_point_rows(analysis: AnalysisResult) -> list[list[str]]:
    return [
        [
            cp.timestamp.date().isoformat(),
            cp.feature_name,
            cp.method,
            f"{cp.confidence:.2f}",
            f"{cp.effect_size_cohens_d:.2f}",
            cp.direction,
        ]
        for cp in sorted(analysis.change_points, key=lambda item: item.timestamp)
    ]


def _significant_test_rows(analysis: AnalysisResult) -> list[list[str]]:
    return [
        [
            test.feature_name,
            test.test_name,
            f"{test.corrected_p_value:.4g}",
            f"{test.effect_size_cohens_d:.2f}",
            (f"[{test.confidence_interval_95[0]:.2f}, {test.confidence_interval_95[1]:.2f}]"),
        ]
        for test in analysis.hypothesis_tests
        if test.significant
    ]


def _sensitivity_line(sensitivity: dict[str, Any], slug: str) -> str:
    authors = sensitivity.get("authors")
    sensitivity_author = authors.get(slug, {}) if isinstance(authors, dict) else {}
    if not sensitivity_author:
        return "not run"
    return (
        f"{sensitivity_author.get('section_residualized_change_points', 0)} residualized "
        f"vs {sensitivity_author.get('primary_change_points', 0)} primary change-points; "
        f"downgrade recommended: {sensitivity_author.get('downgrade_recommended', False)}"
    )


def _summary_lines(
    slug: str,
    role: str,
    analysis: AnalysisResult,
    sensitivity: dict[str, Any],
) -> list[str]:
    score = compute_composite_score(analysis)
    drift = analysis.drift_scores
    ai_similarity = "not available" if drift is None else str(drift.ai_baseline_similarity)
    era = analysis.era_classification
    return [
        f"- Author slug: `{slug}`",
        f"- Role: `{role}`",
        f"- Signal strength: `{score.strength.value}`",
        f"- Composite score: `{score.composite:.3f}`",
        f"- Analysis config hash: `{analysis.config_hash}`",
        f"- AI-baseline similarity: {ai_similarity}",
        f"- Section-residualized sensitivity: {_sensitivity_line(sensitivity, slug)}",
        f"- Dominant AI-marker era: `{era.dominant_era or 'none'}`",
    ]


def _author_evidence_markdown(
    slug: str,
    settings: ForensicsSettings,
    analysis: AnalysisResult,
    sensitivity: dict[str, Any],
    article_links: list[str],
) -> str:
    author_cfg = next((a for a in settings.authors if a.slug == slug), None)
    display_name = author_cfg.name if author_cfg is not None else slug
    role = author_cfg.role if author_cfg is not None else "unknown"
    score = compute_composite_score(analysis)
    control_count = sum(1 for author in settings.authors if author.role == "control")
    preregistration = verify_preregistration(settings)
    narrative = generate_evidence_narrative(
        analysis,
        slug,
        score=score,
        control_count=control_count,
        preregistration=preregistration,
    )
    summary = "\n".join(_summary_lines(slug, role, analysis, sensitivity))
    article_text = "\n".join(article_links) if article_links else "_No article links available._"
    cp_table = _limited_markdown_table(
        ["Date", "Feature", "Method", "Confidence", "Effect d", "Direction"],
        _change_point_rows(analysis),
    )
    test_table = _limited_markdown_table(
        ["Feature", "Test", "Adjusted p", "Effect d", "95% CI"],
        _significant_test_rows(analysis),
    )
    return f"""---
title: "Evidence Page: {display_name}"
---

## Summary

{summary}

{narrative}

## Change-Point Timeline

{cp_table}

## Significant Pre-Registered Tests

{test_table}

## Representative Articles

{article_text}
"""


def generate_author_evidence_pages(
    settings: ForensicsSettings,
    paths: AnalysisArtifactPaths,
    reports_dir: Path,
    *,
    author_slug: str | None = None,
) -> list[Path]:
    """Write one deterministic Quarto markdown evidence page per selected author."""
    selected = _per_author_slugs(settings, paths.analysis_dir, author_slug)
    pages_dir = reports_dir / "per_author"
    ensure_dir(pages_dir)
    sensitivity = _load_sensitivity_summary(paths)
    pages: list[Path] = []
    for slug in selected:
        analysis = _load_analysis_result(paths, slug)
        markdown = _author_evidence_markdown(
            slug,
            settings,
            analysis,
            sensitivity,
            _author_article_links(paths, slug, analysis),
        )
        page = pages_dir / f"{slug}.qmd"
        write_text_atomic(page, markdown)
        pages.append(page)
    return pages


def _render_author_evidence_pages(
    quarto: str,
    root: Path,
    pages: list[Path],
    fmt: str,
    env: dict[str, str],
) -> int:
    outputs = ["html", "pdf"] if fmt == "both" else [fmt]
    for page in pages:
        for output in outputs:
            cmd = [
                quarto,
                "render",
                str(page),
                "--to",
                output,
                "--output-dir",
                str(page.parent),
            ]
            logger.info("report: running %s", " ".join(cmd))
            proc = subprocess.run(cmd, cwd=root, env=env, check=False)
            if proc.returncode != 0:
                return int(proc.returncode)
    return 0


def run_report(args: ReportArgs) -> int:
    """Render the Quarto book (or a single notebook chapter)."""
    settings = get_settings()
    root = get_project_root()
    reports_dir = root / "data" / "reports"
    ensure_dir(reports_dir)

    ok, code, quarto = _validate_report_prerequisites(settings, root, args)
    if not ok or quarto is None:
        return code

    env = _prepare_report_env(root)
    fmt = getattr(args, "report_format", "both") or "both"
    nb = getattr(args, "notebook", None)

    if getattr(args, "per_author", False):
        paths = AnalysisArtifactPaths.from_project(root, settings.db_path)
        pages = generate_author_evidence_pages(
            settings,
            paths,
            reports_dir,
            author_slug=getattr(args, "author_slug", None),
        )
        return _render_author_evidence_pages(quarto, root, pages, fmt, env)

    if nb:
        return _render_notebook_chapter(quarto, root, reports_dir, nb, fmt, env)
    return _render_full_book(quarto, root, reports_dir, fmt, env)
