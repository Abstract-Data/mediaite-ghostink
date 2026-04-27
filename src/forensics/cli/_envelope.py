"""JSON envelope for ``--output json``: one sorted object on stdout; logs on stderr.

Exit code 4 failures may set ``error.retry_after_ms`` from upstream ``Retry-After``.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Final, Literal

import typer

SCHEMA_VERSION: Final[int] = 1


def success(cmd: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "type": cmd,
        "schemaVersion": SCHEMA_VERSION,
        "data": data or {},
    }


def failure(
    cmd: str,
    code: str,
    message: str,
    *,
    suggestion: str | None = None,
    **extra: object,
) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message, **extra}
    if suggestion is not None:
        err["suggestion"] = suggestion
    return {
        "ok": False,
        "type": cmd,
        "schemaVersion": SCHEMA_VERSION,
        "error": err,
    }


def emit(payload: dict[str, Any]) -> None:
    """Write the envelope to stdout as one sorted-key JSON line."""
    sys.stdout.write(json.dumps(payload, sort_keys=True))
    sys.stdout.write("\n")
    sys.stdout.flush()


def status(line: str, *, output_format: Literal["text", "json"], err: bool = True) -> None:
    """Human status line; stderr in text mode. Suppressed when ``output_format`` is json."""
    if output_format == "json":
        return
    typer.echo(line, err=err)
