"""Every CLI command help includes ``Examples:`` (and JSON leaves carry examples)."""

from __future__ import annotations

import re
from collections.abc import Iterator

import click
import pytest
from typer.main import get_command
from typer.testing import CliRunner

from forensics.cli import app

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _help_paths(cmd: click.Command, prefix: list[str]) -> Iterator[list[str]]:
    """Yield argv prefixes (under ``forensics``) whose ``--help`` should list examples."""
    if isinstance(cmd, click.Group):
        if prefix:
            yield prefix
        for name in sorted(cmd.commands):
            sub = cmd.commands[name]
            if getattr(sub, "hidden", False):
                continue
            yield from _help_paths(sub, prefix + [name])
    elif prefix:
        yield prefix


@pytest.mark.parametrize(
    "argv",
    list(_help_paths(get_command(app), [])),
)
def test_help_contains_examples_section(argv: list[str]) -> None:
    result = runner.invoke(
        app,
        [*argv, "--help"],
        catch_exceptions=False,
        color=False,
    )
    assert result.exit_code == 0, f"help failed for {argv}: {result.output}"
    combined = _strip_ansi((result.stdout or "") + (result.stderr or ""))
    assert "Examples:" in combined, f"missing Examples for forensics {' '.join(argv)} --help"
