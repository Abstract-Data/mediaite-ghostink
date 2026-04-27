"""``forensics commands`` — machine-readable command catalog for agents."""

from __future__ import annotations

from typing import Any

import click
import typer

from forensics.cli._decorators import jsonable_param_default
from forensics.cli._envelope import emit, success
from forensics.cli._exit import ExitCode
from forensics.cli.state import get_cli_state


def _serialize_click_param(p: click.Parameter) -> dict[str, Any]:
    typ = p.type
    type_name = getattr(typ, "name", None) or str(typ)
    choices: list[Any] = []
    raw_choices = getattr(typ, "choices", None)
    if raw_choices is not None:
        try:
            choices = list(raw_choices)
        except TypeError:
            choices = []
    default: Any = p.default
    if callable(default):
        default = None
    else:
        default = jsonable_param_default(default)
    return {
        "name": p.name,
        "type": type_name,
        "required": bool(getattr(p, "required", False)),
        "is_flag": bool(getattr(p, "is_flag", False)),
        "default": default,
        "help": (getattr(p, "help", "") or "").strip(),
        "choices": choices,
    }


def _callback_examples(cmd: click.Command) -> list[str]:
    """Read ``__forensics_examples__`` from the command callback (unwrap Typer wrappers)."""
    cb = getattr(cmd, "callback", None)
    if cb is None:
        return []
    seen: set[int] = set()
    cur: Any = cb
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        ex = getattr(cur, "__forensics_examples__", None)
        if isinstance(ex, list) and ex:
            return list(ex)
        cur = getattr(cur, "__wrapped__", None)
    return []


def walk_command(
    cmd: click.Command,
    path: list[str],
    parent_ctx: click.Context | None,
) -> dict[str, Any]:
    """Build one catalog node (params, examples, nested subcommands)."""
    info_name = path[-1] if path else (cmd.name or "forensics")
    ctx = click.Context(cmd, info_name=info_name, parent=parent_ctx)
    params = [_serialize_click_param(p) for p in cmd.params if p.name not in {"help"}]
    examples = _callback_examples(cmd)
    node: dict[str, Any] = {
        "name": ".".join(path) if path else (cmd.name or "forensics"),
        "help": (cmd.help or "").strip(),
        "params": params,
        "examples": examples,
        "subcommands": [],
    }
    if isinstance(cmd, click.Group):
        for sub_name in sorted(cmd.commands):
            sub = cmd.commands[sub_name]
            if getattr(sub, "hidden", False):
                continue
            node["subcommands"].append(walk_command(sub, [*path, sub_name], ctx))
    return node


def _render_command_tree(node: dict[str, Any], *, indent: int = 0) -> None:
    """Print an indented text tree of command names and first-line help."""
    prefix = "  " * indent
    name = str(node["name"])
    help_text = str(node.get("help") or "").strip()
    first = help_text.split("\n")[0].strip() if help_text else ""
    line = f"{prefix}{name}"
    if first:
        line = f"{line} — {first}"
    typer.echo(line)
    for sub in node.get("subcommands", []):
        if isinstance(sub, dict):
            _render_command_tree(sub, indent=indent + 1)


def run_list_commands(ctx: typer.Context, root_click: click.Command) -> None:
    """Dump the full command catalog (text tree or JSON envelope)."""
    state = get_cli_state(ctx)
    tree = walk_command(root_click, [], None)
    payload = success("commands", {"root": tree})
    if state.output_format == "json":
        emit(payload)
    else:
        _render_command_tree(tree)
    raise typer.Exit(int(ExitCode.OK))
