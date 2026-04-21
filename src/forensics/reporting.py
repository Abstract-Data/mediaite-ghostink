"""Quarto book rendering for forensic notebooks."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from argparse import Namespace
from pathlib import Path

from forensics.config import ForensicsSettings, get_project_root, get_settings
from forensics.utils.provenance import verify_corpus_hash

logger = logging.getLogger(__name__)


def _analysis_artifacts_ok(settings: ForensicsSettings, analysis_dir: Path) -> tuple[bool, str]:
    missing: list[str] = []
    for a in settings.authors:
        p = analysis_dir / f"{a.slug}_result.json"
        if not p.is_file():
            missing.append(str(p))
    if missing:
        return False, "Missing analysis artifacts: " + "; ".join(missing)
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


def run_report(args: Namespace) -> int:
    """Render the Quarto book (or a single notebook chapter)."""
    settings = get_settings()
    root = get_project_root()
    analysis_dir = root / "data" / "analysis"
    reports_dir = root / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    ok, msg = _analysis_artifacts_ok(settings, analysis_dir)
    if not ok:
        logger.error("report: %s", msg)
        return 1

    if bool(getattr(args, "verify", False)):
        db_path = root / "data" / "articles.db"
        v_ok, v_msg = verify_corpus_hash(db_path, analysis_dir)
        if not v_ok:
            logger.error("report --verify failed: %s", v_msg)
            return 1
        logger.info("report --verify: %s", v_msg)

    quarto = _quarto_bin()
    if quarto is None:
        logger.error("report: quarto executable not found on PATH")
        return 1

    fmt = getattr(args, "report_format", "both") or "both"
    nb = getattr(args, "notebook", None)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")

    if nb:
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
