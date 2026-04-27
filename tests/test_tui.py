"""Tests for the setup-wizard TUI (Phase 12 §10 — TUI Tests).

All tests that require ``textual`` are gated behind ``pytest.importorskip`` so
the suite still runs on environments without the ``tui`` extra.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("textual")

from forensics.tui.screens import config as config_screen  # noqa: E402
from forensics.tui.screens import dependencies as deps_screen  # noqa: E402


def test_dependency_check_returns_structured_results() -> None:
    results = deps_screen.check_dependencies()
    assert len(results) >= 3
    # Every result is a frozen dataclass with the expected fields.
    for r in results:
        assert isinstance(r, deps_screen.DependencyCheckResult)
        assert r.name
        assert r.status in {"pass", "warn", "fail"}
        assert isinstance(r.required, bool)
    names = {r.name for r in results}
    assert any("Python" in n for n in names)
    assert any("spaCy" in n for n in names)


def test_dependency_check_detects_missing_spacy(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "spacy":
            raise ImportError("simulated missing spacy")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    result = deps_screen._check_spacy_model()
    assert result.status == "fail"
    assert result.required is True
    assert result.is_blocker


def test_dependency_check_has_blocking_failures_helper() -> None:
    ok = deps_screen.DependencyCheckResult(
        name="Python 3.13+", required=True, status="pass", version="3.13.0", install_hint=""
    )
    blocker = deps_screen.DependencyCheckResult(
        name="spaCy en_core_web_sm",
        required=True,
        status="fail",
        version="missing",
        install_hint="uv run python -m spacy download en_core_web_sm",
    )
    optional_warn = deps_screen.DependencyCheckResult(
        name="Quarto", required=False, status="warn", version="not found", install_hint=""
    )
    assert deps_screen.has_blocking_failures([ok, optional_warn]) is False
    assert deps_screen.has_blocking_failures([ok, blocker, optional_warn]) is True


def test_config_generation_no_placeholders_blind() -> None:
    text = config_screen.generate_config(config_screen.ConfigInputs(mode="blind"))
    lowered = text.lower()
    for bad in ("fixme", "todo", "xxx", "<your", "<insert"):
        assert bad not in lowered, f"placeholder {bad!r} found in generated config"
    # TOML sanity — the required sections are present.
    for section in ("[scraping]", "[analysis]", "[survey]", "[baseline]", "[report]"):
        assert section in text
    # TOML parses.
    import tomllib

    parsed = tomllib.loads(text)
    assert "scraping" in parsed
    assert "analysis" in parsed
    assert "survey" in parsed
    assert parsed["authors"]  # seed block present for blind mode


def test_config_generation_no_placeholders_handpick() -> None:
    inputs = config_screen.ConfigInputs(
        mode="pick",
        author_slugs=("jane-doe", "john-roe"),
    )
    text = config_screen.generate_config(inputs)
    lowered = text.lower()
    for bad in ("fixme", "todo", "xxx"):
        assert bad not in lowered
    import tomllib

    parsed = tomllib.loads(text)
    slugs = {a["slug"] for a in parsed["authors"]}
    assert slugs == {"jane-doe", "john-roe"}


def test_write_config_backs_up_existing(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text("old content\n", encoding="utf-8")
    new_text = config_screen.generate_config(config_screen.ConfigInputs())
    backup = config_screen.write_config(target, new_text)
    assert backup is not None and backup.is_file()
    assert backup.read_text() == "old content\n"
    assert target.read_text() == new_text


def test_write_config_no_backup_when_missing(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    new_text = config_screen.generate_config(config_screen.ConfigInputs())
    backup = config_screen.write_config(target, new_text)
    assert backup is None
    assert target.read_text() == new_text


@pytest.mark.asyncio
async def test_tui_app_mounts() -> None:
    from forensics.tui.app import ForensicsSetupApp

    app = ForensicsSetupApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # The first screen is pushed on mount.
        assert app.screen is not None
        # Navigation via the "n" binding advances to the next screen.
        await pilot.press("n")
        await pilot.pause()
        # Quit binding closes the app cleanly.
        await pilot.press("q")
        await pilot.pause()
