"""Tests for ``forensics commands`` JSON catalog."""

from __future__ import annotations

import json
import re

import click
from typer.main import get_command
from typer.testing import CliRunner

from forensics.cli import app

runner = CliRunner()


def _top_level_command_names(root: click.Command) -> set[str]:
    if not isinstance(root, click.Group):
        return set()
    return {n for n, c in root.commands.items() if not getattr(c, "hidden", False)}


def test_commands_json_root_and_subcommands() -> None:
    result = runner.invoke(
        app,
        ["--output", "json", "commands"],
        catch_exceptions=False,
        color=False,
    )
    assert result.exit_code == 0, result.output
    raw = (result.stdout or "").strip()
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["type"] == "commands"
    assert payload["schemaVersion"] == 1
    root = payload["data"]["root"]
    assert root["name"] == "forensics"

    click_root = get_command(app)
    expected = _top_level_command_names(click_root)
    names = {n["name"] for n in root["subcommands"]}
    assert names == expected

    for sub in root["subcommands"]:
        for param in sub["params"]:
            assert set(param.keys()) >= {
                "name",
                "type",
                "required",
                "is_flag",
                "default",
                "help",
                "choices",
            }

    analyze = next(s for s in root["subcommands"] if s["name"] == "analyze")
    assert analyze["examples"]
    assert "forensics analyze --author" in " ".join(analyze["examples"])


def test_commands_json_leaf_examples_nonempty() -> None:
    result = runner.invoke(
        app,
        ["--output", "json", "commands"],
        catch_exceptions=False,
        color=False,
    )
    assert result.exit_code == 0
    payload = json.loads((result.stdout or "").strip())

    def walk(node: dict[str, object]) -> None:
        subs = node.get("subcommands") or []
        if not subs:
            assert node.get("examples"), f"leaf {node.get('name')!r} missing examples"
            return
        for ch in subs:
            walk(ch)

    walk(payload["data"]["root"])


def test_commands_text_mode_tree() -> None:
    result = runner.invoke(app, ["commands"], catch_exceptions=False, color=False)
    assert result.exit_code == 0
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout or "")
    assert "forensics" in text
    assert "scrape" in text
    assert "analyze" in text
