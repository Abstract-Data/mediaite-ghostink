"""Unit tests for scrape error transient classification (CLI exit TRANSIENT)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from forensics.cli import scrape as scrape_mod
from forensics.cli._exit import ExitCode
from forensics.scraper.fetcher import (
    SCRAPE_RUN_TELEMETRY,
    ScrapeRunTelemetry,
    append_scrape_error,
    log_scrape_error,
    scrape_error_record,
    scrape_error_transient_from_http_status,
    scrape_failure_transient,
)


def test_scrape_failure_transient_timeouts() -> None:
    assert scrape_failure_transient(httpx.ReadTimeout("timeout")) is True
    assert scrape_failure_transient(httpx.ConnectTimeout("timeout")) is True
    assert scrape_failure_transient(httpx.TimeoutException("timeout")) is True


def test_scrape_failure_transient_http_status_error() -> None:
    def _resp(code: int) -> httpx.Response:
        return httpx.Response(code, request=httpx.Request("GET", "https://example.test/x"))

    exc_503 = httpx.HTTPStatusError("msg", request=_resp(503).request, response=_resp(503))
    assert scrape_failure_transient(exc_503) is True
    exc_429 = httpx.HTTPStatusError("msg", request=_resp(429).request, response=_resp(429))
    assert scrape_failure_transient(exc_429) is True
    exc_404 = httpx.HTTPStatusError("msg", request=_resp(404).request, response=_resp(404))
    assert scrape_failure_transient(exc_404) is False


def test_scrape_failure_transient_connect_error_not_timeout() -> None:
    exc = httpx.ConnectError("dns")
    assert scrape_failure_transient(exc) is False


def test_scrape_error_transient_from_http_status() -> None:
    assert scrape_error_transient_from_http_status(503) is True
    assert scrape_error_transient_from_http_status(429) is True
    assert scrape_error_transient_from_http_status(404) is False
    assert scrape_error_transient_from_http_status(None) is False


def test_scrape_error_record_includes_transient() -> None:
    row = scrape_error_record("https://x", 503, "boom", "html_fetch", transient=True)
    assert row["transient"] is True
    assert "timestamp" in row


@pytest.mark.asyncio
async def test_append_scrape_error_roundtrip_transient(tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    rec = scrape_error_record("u", None, "ReadTimeout", "html_fetch", transient=True)
    await append_scrape_error(path, rec)
    line = path.read_text(encoding="utf-8").strip()
    loaded = json.loads(line)
    assert loaded["transient"] is True


def test_scrape_run_telemetry_transient_only_total_failure() -> None:
    tel = ScrapeRunTelemetry()
    assert tel.transient_only_total_failure() is False
    tel.record_scrape_error_line(True)
    assert tel.transient_only_total_failure() is True
    tel.mark_row_success()
    assert tel.transient_only_total_failure() is False


@pytest.mark.asyncio
async def test_dispatch_scrape_transient_exit_on_fetch_only_failures(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate fetch path: logged errors all transient, no successful HTML rows."""

    async def fake_fetch(*_a, **_k):
        err = tmp_path / "data" / "scrape_errors.jsonl"
        err.parent.mkdir(parents=True, exist_ok=True)
        await log_scrape_error(
            err,
            "https://example.test/a",
            None,
            "ReadTimeout",
            "html_fetch",
            transient=True,
        )
        return 0

    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scrape_mod, "fetch_articles", fake_fetch)

    rc = await scrape_mod.dispatch_scrape(
        discover=False,
        metadata=False,
        fetch=True,
        dedup=False,
        archive=False,
        dry_run=False,
        force_refresh=False,
    )
    assert rc == int(ExitCode.TRANSIENT)


@pytest.mark.asyncio
async def test_dispatch_scrape_no_transient_when_success_after_transient_errors(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch(*_a, **_k):
        err = tmp_path / "data" / "scrape_errors.jsonl"
        err.parent.mkdir(parents=True, exist_ok=True)
        await log_scrape_error(err, "https://x", None, "ReadTimeout", "html_fetch", transient=True)
        tel = SCRAPE_RUN_TELEMETRY.get()
        if tel is not None:
            tel.mark_row_success()
        return 1

    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scrape_mod, "fetch_articles", fake_fetch)

    rc = await scrape_mod.dispatch_scrape(
        discover=False,
        metadata=False,
        fetch=True,
        dedup=False,
        archive=False,
        dry_run=False,
        force_refresh=False,
    )
    assert rc == 0


@pytest.mark.asyncio
async def test_dispatch_scrape_mixed_permanent_errors_no_transient_exit(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch(*_a, **_k):
        err = tmp_path / "data" / "scrape_errors.jsonl"
        err.parent.mkdir(parents=True, exist_ok=True)
        await log_scrape_error(err, "https://x", None, "ReadTimeout", "html_fetch", transient=True)
        await log_scrape_error(err, "https://y", 404, "Not Found", "html_fetch", transient=False)
        return 0

    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scrape_mod, "fetch_articles", fake_fetch)

    rc = await scrape_mod.dispatch_scrape(
        discover=False,
        metadata=False,
        fetch=True,
        dedup=False,
        archive=False,
        dry_run=False,
        force_refresh=False,
    )
    assert rc == 0
