"""CLI for near-duplicate fingerprint maintenance."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from forensics.cli._envelope import emit, success
from forensics.cli.state import get_cli_state
from forensics.config import DEFAULT_DB_RELATIVE, get_project_root
from forensics.storage.repository import Repository

logger = logging.getLogger(__name__)

dedup_app = typer.Typer(help="Near-duplicate fingerprint utilities")


@dedup_app.command("recompute-fingerprints")
def recompute_fingerprints(
    ctx: typer.Context,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Max rows to recompute (testing)."),
    ] = None,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Override SQLite path (default: project data/articles.db)."),
    ] = None,
) -> None:
    """Recompute persisted simhashes for rows not stamped at the current NFKC (v2) version."""
    root = get_project_root()
    db_path = db if db is not None else root / DEFAULT_DB_RELATIVE
    if not db_path.is_file():
        logger.error("database not found: %s", db_path)
        raise typer.Exit(code=1)
    with Repository(db_path) as repo:
        summary = repo.recompute_stale_dedup_simhashes(limit=limit)
    state = get_cli_state(ctx)
    if state.output_format == "json":
        emit(success("dedup.recompute_fingerprints", summary))
    else:
        typer.echo(
            "Dedup fingerprint recompute: "
            f"recomputed={summary['recomputed']} "
            f"skipped={summary['skipped']} "
            f"errors={summary['errors']}",
        )
