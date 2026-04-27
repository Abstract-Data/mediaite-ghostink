"""CLI for near-duplicate fingerprint maintenance."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from forensics.cli._decorators import examples_epilog, forensics_examples
from forensics.cli._envelope import emit, success
from forensics.cli._errors import fail
from forensics.cli._exit import ExitCode
from forensics.cli.state import get_cli_state
from forensics.config import DEFAULT_DB_RELATIVE, get_project_root
from forensics.storage.repository import Repository

dedup_app = typer.Typer(
    help="Near-duplicate fingerprint utilities",
    epilog=examples_epilog("forensics dedup recompute-fingerprints --limit 100"),
)

_RECOMP_EPILOG, _recomp_ex = forensics_examples(
    "forensics --output json dedup recompute-fingerprints --limit 100",
)


@dedup_app.command("recompute-fingerprints", epilog=_RECOMP_EPILOG)
@_recomp_ex
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
    """Recompute persisted simhashes for rows not stamped at the current NFKC (v2) version.

    Idempotent: when every row is already current, exit code 5 (CONFLICT) signals
    "nothing to do" for agents (JSON mode still emits a success envelope on stdout
    before exiting). Missing dedup schema columns yield zeros without CONFLICT.
    """
    root = get_project_root()
    db_path = db if db is not None else root / DEFAULT_DB_RELATIVE
    if not db_path.is_file():
        raise fail(
            ctx,
            "dedup.recompute_fingerprints",
            "database_missing",
            f"SQLite database not found: {db_path}",
            exit_code=ExitCode.AUTH_OR_RESOURCE,
            suggestion=("run: forensics scrape --discover --metadata to populate data/articles.db"),
        )
    with Repository(db_path) as repo:
        columns_ok = repo.dedup_simhash_columns_present()
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
    idle = columns_ok and summary["recomputed"] == 0 and summary["errors"] == 0
    if idle:
        raise typer.Exit(int(ExitCode.CONFLICT))
    raise typer.Exit(int(ExitCode.OK))
