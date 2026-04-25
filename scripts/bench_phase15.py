"""Phase 15 L1 — pre-Phase-15 benchmark capture.

Runs ``run_full_analysis`` author-by-author, records per-stage wall-clock and
the key signal-correctness aggregates (CP counts by method, convergence
window counts, pipeline A/B/C scores, FDR-significant totals), and writes a
versioned JSON snapshot to ``data/bench/phase15_pre_<sha>.json``.

Usage::

    uv run python scripts/bench_phase15.py                            # default output path
    uv run python scripts/bench_phase15.py --output /tmp/bench.json   # explicit path
    uv run python scripts/bench_phase15.py --author isaac-schorr      # single author

When ``data/articles.db`` is absent the script exits cleanly with a helpful
message — the bench is advisory in that case (see HANDOFF.md).

Schema: ``bench_schema_version: 1``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PerAuthorStageTimings:
    """Wall-clock (seconds) for each analysis stage, per author.

    ``compare`` is reported per-author as a convenience even though the
    comparison stage runs once per ``run_full_analysis`` invocation
    (newsroom-wide). When the bench script invokes ``run_full_analysis``
    once per slug (the default) the per-author and newsroom-wide buckets
    are the same value.
    """

    extract: float = 0.0
    changepoint: float = 0.0
    drift: float = 0.0
    convergence: float = 0.0
    hypothesis_tests: float = 0.0
    compare: float = 0.0
    total: float = 0.0


@dataclass
class PerAuthorBench:
    """Per-author benchmark aggregates."""

    author_slug: str
    timings: PerAuthorStageTimings
    cp_count_pelt: int = 0
    cp_count_bocpd: int = 0
    convergence_windows: int = 0
    max_convergence_ratio: float = 0.0
    pipeline_a_max: float = 0.0
    pipeline_b_max: float = 0.0
    pipeline_c_max: float = 0.0
    fdr_significant_count: int = 0
    error: str | None = None


def _get_git_sha(project_root: Path) -> str:
    """Short git SHA for the output filename; ``"nogit"`` when unavailable."""
    import subprocess

    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or "nogit"
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "nogit"


def _bench_one_author(
    slug: str,
    paths,  # type: ignore[no-untyped-def]
    settings,  # type: ignore[no-untyped-def]
) -> PerAuthorBench:
    """Run full analysis for one author and capture timings + signal counts.

    Phase 15 G3: per-stage timings come from ``orchestrator.AnalysisTimings``
    (populated in-place by ``run_full_analysis(timings_out=...)``), so the
    bench emits non-zero ``extract`` / ``changepoint`` / ``drift`` /
    ``convergence`` / ``hypothesis_tests`` / ``compare`` measurements
    instead of the legacy zero-init dict where only ``total`` was populated.
    """
    from forensics.analysis.orchestrator import AnalysisTimings, run_full_analysis

    timings = PerAuthorStageTimings()
    bench = PerAuthorBench(author_slug=slug, timings=timings)
    out_timings = AnalysisTimings()

    t0 = time.perf_counter()
    try:
        results = run_full_analysis(
            paths,
            settings,
            author_slug=slug,
            timings_out=out_timings,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        bench.error = f"{type(exc).__name__}: {exc}"
        bench.timings.total = time.perf_counter() - t0
        return bench
    # Prefer the orchestrator's instrumented total; fall back to the wall-
    # clock bracket here if the orchestrator chose not to populate timings.
    bench.timings.total = out_timings.total or (time.perf_counter() - t0)
    bench.timings.compare = out_timings.compare

    per_author_stages = out_timings.per_author.get(slug, {})
    bench.timings.extract = float(per_author_stages.get("extract", 0.0))
    bench.timings.changepoint = float(per_author_stages.get("changepoint", 0.0))
    bench.timings.drift = float(per_author_stages.get("drift", 0.0))
    bench.timings.convergence = float(per_author_stages.get("convergence", 0.0))
    bench.timings.hypothesis_tests = float(per_author_stages.get("hypothesis_tests", 0.0))

    result = results.get(slug)
    if result is None:
        bench.error = "no AnalysisResult emitted"
        return bench

    method_counts: Counter[str] = Counter(cp.method for cp in result.change_points)
    bench.cp_count_pelt = method_counts.get("pelt", 0)
    bench.cp_count_bocpd = method_counts.get("bocpd", 0)
    bench.convergence_windows = len(result.convergence_windows)
    if result.convergence_windows:
        bench.max_convergence_ratio = max(w.convergence_ratio for w in result.convergence_windows)
        bench.pipeline_a_max = max(w.pipeline_a_score for w in result.convergence_windows)
        bench.pipeline_b_max = max(w.pipeline_b_score for w in result.convergence_windows)
        bench.pipeline_c_max = max((w.pipeline_c_score or 0.0) for w in result.convergence_windows)
    bench.fdr_significant_count = sum(1 for t in result.hypothesis_tests if t.significant)
    return bench


def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: data/bench/phase15_pre_<sha>.json).",
    )
    parser.add_argument(
        "--author",
        type=str,
        default=None,
        help="Single author slug to benchmark (default: every configured author).",
    )
    args = parser.parse_args()

    # Deferred imports keep the script fast to ``--help`` and avoid costing
    # the full settings / DB stack when the DB is absent.
    from forensics.analysis.artifact_paths import AnalysisArtifactPaths
    from forensics.config import get_project_root, get_settings
    from forensics.utils.provenance import compute_model_config_hash

    project_root = get_project_root()
    settings = get_settings()
    db_path = settings.db_path
    if not db_path.is_file():
        logger.warning(
            "data/articles.db not found at %s — bench is a no-op. See HANDOFF.md.",
            db_path,
        )
        return 0

    sha = _get_git_sha(project_root)
    output = args.output or (project_root / "data" / "bench" / f"phase15_pre_{sha}.json")
    output.parent.mkdir(parents=True, exist_ok=True)

    paths = AnalysisArtifactPaths.from_project(project_root, db_path=db_path)
    slugs = [args.author] if args.author else [a.slug for a in settings.authors]

    per_author: list[PerAuthorBench] = []
    grand_start = time.perf_counter()
    for slug in slugs:
        logger.info("benchmarking %s", slug)
        per_author.append(_bench_one_author(slug, paths, settings))
    grand_total = time.perf_counter() - grand_start

    payload: dict[str, Any] = {
        "bench_schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "git_sha": sha,
        "config_hash": compute_model_config_hash(settings.analysis, length=16),
        "grand_total_seconds": grand_total,
        "newsroom_fdr_significant_total": sum(a.fdr_significant_count for a in per_author),
        "per_author": [asdict(a) for a in per_author],
    }
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info("wrote %s", output)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
