"""Peer reviewer setup: uv tiers, spaCy, Quarto, Ollama pull hints."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated

import typer

from forensics.cli._decorators import forensics_examples
from forensics.cli._errors import fail
from forensics.cli._exit import ExitCode
from forensics.cli.state import get_cli_state

if TYPE_CHECKING:
    from forensics.config import ForensicsSettings

PEER_SETUP_EPILOG, _peer_setup_ex = forensics_examples(
    "forensics peer-setup",
    "forensics peer-setup --check-ollama",
)


def _settings_load_errors() -> tuple[type[BaseException], ...]:
    import tomllib

    from pydantic import ValidationError

    return (ValidationError, FileNotFoundError, tomllib.TOMLDecodeError, ValueError, OSError)


def _print_uv_tiers() -> None:
    typer.echo("\n== uv sync (copy-paste tiers) ==")
    typer.echo("  Reviewer (dev + TUI):")
    typer.echo("    uv sync --extra dev --extra tui")
    typer.echo("  + Phase 10 baseline:")
    typer.echo("    uv sync --extra dev --extra tui --extra baseline")
    typer.echo("  + Phase 9 probability:")
    typer.echo("    uv sync --extra dev --extra tui --extra probability")
    typer.echo("  All optional tracks:")
    typer.echo("    uv sync --extra dev --extra tui --extra baseline --extra probability")


def _print_spacy_note() -> None:
    typer.echo("\n== spaCy ==")
    typer.echo(
        "  Default pipeline en_core_web_md ships as a direct wheel in pyproject.toml; "
        "`uv sync` installs it. Run `uv run python -m spacy download <name>` only if "
        "you change spacy_model in config.toml."
    )


def _print_quarto() -> None:
    typer.echo("\n== Quarto ==")
    typer.echo("  Required for `forensics report` / report step of `forensics all`:")
    typer.echo("  https://quarto.org/docs/get-started/")


def _print_baseline_block(settings: ForensicsSettings) -> None:
    if not settings.baseline.models:
        return
    typer.echo("\n== Phase 10 baseline (Ollama) ==")
    typer.echo(f"  ollama_base_url: {settings.baseline.ollama_base_url}")
    typer.echo("  Ensure Ollama is running (e.g. `ollama serve`) then pull models:")
    for model in settings.baseline.models:
        typer.echo(f"    ollama pull {model}")


@_peer_setup_ex
def peer_setup_cmd(
    ctx: typer.Context,
    check_ollama: Annotated[
        bool,
        typer.Option(
            "--check-ollama",
            help="Probe Ollama for configured baseline models (no auto-pull).",
        ),
    ] = False,
) -> None:
    """Print peer setup hints (uv extras, spaCy, Quarto, Ollama pulls from config)."""
    st = get_cli_state(ctx)
    if st.output_format == "json":
        raise fail(
            ctx,
            "peer-setup",
            "unsupported_output",
            "peer-setup is text-only; omit --output json.",
            exit_code=ExitCode.USAGE_ERROR,
        )

    from forensics.baseline.preflight import preflight_check
    from forensics.config import get_settings

    try:
        settings = get_settings()
    except _settings_load_errors() as exc:
        raise fail(
            ctx,
            "peer-setup",
            "config_invalid",
            f"Could not parse config.toml: {exc}",
            exit_code=ExitCode.USAGE_ERROR,
            suggestion="run: forensics validate",
        ) from exc

    _print_uv_tiers()
    _print_spacy_note()
    _print_quarto()
    _print_baseline_block(settings)

    if check_ollama:
        ok = asyncio.run(
            preflight_check(
                list(settings.baseline.models),
                settings.baseline.ollama_base_url.rstrip("/"),
            )
        )
        typer.echo(f"\nOllama preflight: {'PASS' if ok else 'FAIL'}")
        if not ok:
            raise typer.Exit(int(ExitCode.GENERAL_ERROR))
    raise typer.Exit(int(ExitCode.OK))


def attach_peer_setup(app: typer.Typer) -> None:
    """Register ``peer-setup`` on the root CLI app."""
    app.command(name="peer-setup", epilog=PEER_SETUP_EPILOG)(peer_setup_cmd)


__all__ = ["PEER_SETUP_EPILOG", "attach_peer_setup", "peer_setup_cmd"]
