"""Full end-to-end pipeline (scrape → extract → analyze → report)."""

from __future__ import annotations

from argparse import Namespace

from forensics.cli.analyze import run_analyze
from forensics.cli.extract import run_extract
from forensics.cli.scrape import _dispatch
from forensics.config import get_settings
from forensics.reporting import run_report


async def _run_all_pipeline() -> int:
    """scrape → extract → analyze → report."""
    code = await _dispatch(
        discover=False,
        metadata=False,
        fetch=False,
        dedup=False,
        archive=False,
        dry_run=False,
        force_refresh=False,
    )
    if code != 0:
        return code

    code = run_extract(
        author=None,
        skip_embeddings=False,
        skip_probability=True,
        probability=False,
        no_binoculars=False,
        device=None,
    )
    if code != 0:
        return code

    code = run_analyze(
        changepoint=False,
        timeseries=True,
        drift=False,
        convergence=True,
        compare=False,
        ai_baseline=False,
        skip_generation=False,
        verify_corpus=False,
        author=None,
        openai_key=None,
        llm_model="gpt-4o",
    )
    if code != 0:
        return code

    settings = get_settings()
    report_ns = Namespace(
        verify=False,
        report_format=settings.report.output_format,
        notebook=None,
    )
    return run_report(report_ns)
