"""CLI decorators shared across ``forensics`` Typer commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar, cast

F = TypeVar("F", bound=Callable[..., object])


class _WithForensicsExamples(Protocol):
    __forensics_examples__: list[str]


def examples_epilog(*examples: str) -> str:
    """Build ``epilog=`` text for ``--help``."""
    return "\n\nExamples:\n" + "\n".join(f"  $ {e}" for e in examples)


def forensics_examples(
    *examples: str,
) -> tuple[str, Callable[[F], F]]:
    """Return ``(epilog, decorator)`` for the same example strings."""
    return examples_epilog(*examples), with_examples(*examples)


def with_examples(*examples: str) -> Callable[[F], F]:
    """Attach ``__forensics_examples__`` for JSON catalog (use with :func:`examples_epilog`)."""

    def decorate(fn: F) -> F:
        cast(_WithForensicsExamples, fn).__forensics_examples__ = list(examples)
        return fn

    return decorate


def jsonable_param_default(value: object) -> object:
    """Normalize Click option defaults for JSON catalog emission."""
    if isinstance(value, Path):
        return str(value)
    return value
