"""``forensics config`` subcommands."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

import typer

from forensics.cli._decorators import examples_epilog, forensics_examples, with_examples
from forensics.cli._envelope import emit
from forensics.cli._exit import ExitCode
from forensics.cli.state import get_cli_state
from forensics.config import get_settings

logger = logging.getLogger(__name__)

config_app = typer.Typer(
    name="config",
    help="Inspect and validate configuration.",
    epilog=examples_epilog("forensics config audit"),
)

_AUDIT_EPILOG, _audit_ex = forensics_examples("forensics config audit")


def _analysis_field_diffs(
    current: Any,
    default: Any,
    prefix: str = "analysis.",
) -> list[dict[str, object]]:
    diffs: list[dict[str, object]] = []
    cur_cls = type(current)
    if not hasattr(cur_cls, "model_fields"):
        return diffs
    for name in cur_cls.model_fields:
        cv = getattr(current, name)
        bv = getattr(default, name)
        if hasattr(type(cv), "model_fields"):
            diffs.extend(_analysis_field_diffs(cv, bv, f"{prefix}{name}."))
        elif cv != bv:
            diffs.append({"path": f"{prefix}{name}", "value": cv, "default": bv})
    return diffs


@config_app.command(name="audit", epilog=_AUDIT_EPILOG)
@with_examples("forensics config audit")
@_audit_ex
def config_audit(
    ctx: typer.Context,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit one JSON object on stdout (for scripts)."),
    ] = False,
) -> None:
    """Report non-default analysis fields (P2-CQ-001)."""
    from forensics.config.analysis_settings import AnalysisConfig

    settings = get_settings()
    diffs = _analysis_field_diffs(settings.analysis, AnalysisConfig())

    if json_output:
        typer.echo(json.dumps({"non_default_fields": diffs, "count": len(diffs)}, default=str))
        raise typer.Exit(int(ExitCode.OK))

    fmt = get_cli_state(ctx).output_format
    if not diffs:
        if fmt == "json":
            emit({"status": "ok", "message": "all analysis fields match defaults"})
        else:
            typer.echo("config audit: analysis section matches defaults (no overrides).")
        raise typer.Exit(int(ExitCode.OK))

    if fmt == "json":
        emit({"status": "ok", "diffs": diffs, "count": len(diffs)})
    else:
        typer.echo(f"config audit: {len(diffs)} non-default analysis field(s):")
        for item in diffs:
            typer.echo(f"  {item['path']}: {item['value']!r} (default {item['default']!r})")
    logger.info("config audit listed %d non-default analysis fields", len(diffs))
    raise typer.Exit(int(ExitCode.OK))
