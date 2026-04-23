"""Unit tests for ``forensics.pipeline`` (mocked I/O)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import typer

from forensics.config.settings import (
    AnalysisConfig,
    ForensicsSettings,
    ReportConfig,
    ScrapingConfig,
)
from forensics.models.report_args import ReportArgs
from forensics.pipeline import run_all_pipeline
from forensics.preflight import PreflightCheck, PreflightReport


def _settings() -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(),
        report=ReportConfig(output_format="html"),
    )


def test_run_all_pipeline_returns_2_on_preflight_failures() -> None:
    report = PreflightReport(
        checks=(PreflightCheck("disk", "fail", "no space"),),
    )
    with mock.patch("forensics.preflight.run_all_preflight_checks", return_value=report):
        assert run_all_pipeline(show_progress=False) == 2


def test_run_all_pipeline_logs_warnings_but_continues() -> None:
    report = PreflightReport(
        checks=(PreflightCheck("ollama", "warn", "not running"),),
    )
    root = Path("/tmp/forensics-pipeline-test-root")

    async def _fake_dispatch(**_kwargs: object) -> int:
        return 0

    fake_ctx = mock.MagicMock()

    with (
        mock.patch("forensics.preflight.run_all_preflight_checks", return_value=report),
        mock.patch("forensics.pipeline.get_settings", return_value=_settings()),
        mock.patch("forensics.pipeline.get_project_root", return_value=root),
        mock.patch("forensics.pipeline.PipelineContext.resolve", return_value=fake_ctx),
        mock.patch("forensics.pipeline.dispatch_scrape", side_effect=_fake_dispatch),
        mock.patch("forensics.pipeline.extract_all_features") as ex,
        mock.patch("forensics.pipeline.run_analyze"),
        mock.patch("forensics.pipeline.run_report", return_value=0) as rr,
    ):
        assert run_all_pipeline(show_progress=False) == 0
    ex.assert_called_once()
    rr.assert_called_once()
    assert isinstance(rr.call_args.args[0], ReportArgs)
    fake_ctx.record_audit.assert_called()


def test_run_all_pipeline_propagates_scrape_exit_code() -> None:
    report = PreflightReport(checks=())
    root = Path("/tmp/forensics-pipeline-test-root")

    async def _fail_dispatch(**_kwargs: object) -> int:
        return 3

    with (
        mock.patch("forensics.preflight.run_all_preflight_checks", return_value=report),
        mock.patch("forensics.pipeline.get_settings", return_value=_settings()),
        mock.patch("forensics.pipeline.get_project_root", return_value=root),
        mock.patch("forensics.pipeline.PipelineContext.resolve", return_value=mock.MagicMock()),
        mock.patch("forensics.pipeline.dispatch_scrape", side_effect=_fail_dispatch),
        mock.patch("forensics.pipeline.extract_all_features") as ex,
    ):
        assert run_all_pipeline(show_progress=False) == 3
    ex.assert_not_called()


def test_run_all_pipeline_maps_typer_exit_from_analyze() -> None:
    report = PreflightReport(checks=())
    root = Path("/tmp/forensics-pipeline-test-root")

    async def _ok_dispatch(**_kwargs: object) -> int:
        return 0

    with (
        mock.patch("forensics.preflight.run_all_preflight_checks", return_value=report),
        mock.patch("forensics.pipeline.get_settings", return_value=_settings()),
        mock.patch("forensics.pipeline.get_project_root", return_value=root),
        mock.patch("forensics.pipeline.PipelineContext.resolve", return_value=mock.MagicMock()),
        mock.patch("forensics.pipeline.dispatch_scrape", side_effect=_ok_dispatch),
        mock.patch("forensics.pipeline.extract_all_features"),
        mock.patch("forensics.pipeline.run_analyze", side_effect=typer.Exit(5)),
        mock.patch("forensics.pipeline.run_report") as rr,
    ):
        assert run_all_pipeline(show_progress=False) == 5
    rr.assert_not_called()


def test_run_all_pipeline_typer_exit_zero_from_analyze_still_reports() -> None:
    report = PreflightReport(checks=())
    root = Path("/tmp/forensics-pipeline-test-root")

    async def _ok_dispatch(**_kwargs: object) -> int:
        return 0

    with (
        mock.patch("forensics.preflight.run_all_preflight_checks", return_value=report),
        mock.patch("forensics.pipeline.get_settings", return_value=_settings()),
        mock.patch("forensics.pipeline.get_project_root", return_value=root),
        mock.patch("forensics.pipeline.PipelineContext.resolve", return_value=mock.MagicMock()),
        mock.patch("forensics.pipeline.dispatch_scrape", side_effect=_ok_dispatch),
        mock.patch("forensics.pipeline.extract_all_features"),
        mock.patch("forensics.pipeline.run_analyze", side_effect=typer.Exit(0)),
        mock.patch("forensics.pipeline.run_report", return_value=0) as rr,
    ):
        assert run_all_pipeline(show_progress=False) == 0
    rr.assert_called_once()
