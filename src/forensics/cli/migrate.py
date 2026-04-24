"""``forensics migrate`` — run storage-layer migrations (Phase 15 Step L6).

Exposes two Typer entry points:

- ``forensics migrate`` — apply any pending forward-only SQLite migrations.
  Idempotent: a no-op when the DB is already at the latest schema version.
- ``forensics features migrate`` — upgrade every feature parquet under
  ``data/features/`` to the current schema version (default: 2). Supports
  ``--dry-run`` so operators can preview the change set before committing.

Both commands are thin wrappers over ``forensics.storage.migrations`` and the
``scripts/migrate_feature_parquets.py`` helper. The CLI is the supported
surface; the script is kept so the migration can also be invoked outside of
the Typer app.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Annotated

import typer

features_app = typer.Typer(
    name="features",
    help="Feature-store maintenance commands (schema migrations, etc).",
    no_args_is_help=True,
)


def migrate(
    db_path: Annotated[
        Path | None,
        typer.Option(
            "--db",
            help="Override the SQLite DB path (default: <project_root>/data/articles.db).",
        ),
    ] = None,
) -> None:
    """Apply pending SQLite migrations (Phase 15 Step 0.2).

    Idempotent. Safe to run on every deploy — migrations that have already
    been recorded in ``schema_version`` are skipped.
    """
    from forensics.config import get_project_root
    from forensics.storage.repository import Repository

    logger = logging.getLogger(__name__)
    target = db_path or (get_project_root() / "data" / "articles.db")
    if not target.parent.is_dir():
        typer.echo(f"Parent directory does not exist: {target.parent}", err=True)
        raise typer.Exit(code=1)

    with Repository(target) as repo:
        applied = repo.apply_migrations()
    if applied:
        logger.info("Applied %d SQLite migration(s): %s", len(applied), applied)
        typer.echo(f"Applied migrations: {applied}")
    else:
        typer.echo("No pending SQLite migrations.")


@features_app.command(name="migrate")
def features_migrate(
    features_dir: Annotated[
        Path | None,
        typer.Option(
            "--features-dir",
            help="Override the features directory (default: <project_root>/data/features).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Log the would-be changes without touching any files.",
        ),
    ] = False,
) -> None:
    """Upgrade every feature parquet to the current schema version."""
    from forensics.config import get_project_root

    logger = logging.getLogger(__name__)
    mig = importlib.import_module("forensics.storage.migrations.002_feature_parquet_section")
    target = features_dir or (get_project_root() / "data" / "features")
    if not target.is_dir():
        typer.echo(
            f"features directory not found: {target} (nothing to migrate).",
            err=True,
        )
        return

    migrated, skipped = mig.migrate_all(target, dry_run=dry_run)
    logger.info(
        "features migrate: migrated=%d skipped=%d dry_run=%s",
        migrated,
        skipped,
        dry_run,
    )
    typer.echo(f"features migrate: migrated={migrated} skipped={skipped} dry_run={dry_run}")
