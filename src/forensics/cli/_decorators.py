"""CLI decorators shared across ``forensics`` Typer commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., object])


def examples_epilog(*examples: str) -> str:
    """Rich/Typer ``epilog=`` text so ``--help`` shows realistic invocations."""
    return "\n\nExamples:\n" + "\n".join(f"  $ {e}" for e in examples)


def forensics_examples(
    *examples: str,
) -> tuple[str, Callable[[F], F]]:
    """Return ``(epilog, decorator)`` from one example list (single source of truth)."""
    return examples_epilog(*examples), with_examples(*examples)


def with_examples(*examples: str) -> Callable[[F], F]:
    """Attach example strings for ``forensics commands --output json``.

    Typer renders ``--help`` via Rich; pass the same strings to
    ``@app.command(epilog=...)`` / ``@typer.Typer(epilog=...)`` using
    :func:`examples_epilog` or :func:`forensics_examples`.
    """

    def decorate(fn: F) -> F:
        fn.__forensics_examples__ = list(examples)  # type: ignore[attr-defined]
        return fn

    return decorate


def jsonable_param_default(value: Any) -> Any:
    """Normalize Click option defaults for JSON catalog emission."""
    if isinstance(value, Path):
        return str(value)
    return value
