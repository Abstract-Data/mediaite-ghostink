"""Forward-only SQLite migrations for the forensics corpus DB (Phase 15 Step 0.2).

Each migration is a Python module under this package exposing

    def migrate(conn: sqlite3.Connection) -> None: ...

and is named ``NNN_short_slug.py`` where ``NNN`` is a zero-padded monotonic
integer. :func:`apply_migrations` is idempotent — it inspects ``schema_version``
and applies only migrations whose version is higher than the current maximum.

Run via ``forensics migrate`` (see ``src/forensics/cli/migrate.py``) or
implicitly on ``Repository.__enter__`` (both code paths end up here).

Design choices:

* Forward-only. Rollbacks are accomplished by restoring from the pre-migration
  backup DB copy the operator takes before running migrations in production.
* ``schema_version`` table is created lazily so existing databases gain
  migration bookkeeping on first contact.
* Migrations run inside a single transaction per-migration so a failure in
  migration N does not leave the DB straddling N/N+1.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

__all__ = [
    "apply_migrations",
    "applied_versions",
    "discover_migrations",
]

logger = logging.getLogger(__name__)

_MIGRATION_NAME_RE = re.compile(r"^(\d{3,})_[a-z0-9_]+$")


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL
        )
        """
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of migration versions already applied to ``conn``."""
    _ensure_schema_version_table(conn)
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    return {int(r[0]) for r in rows}


def discover_migrations() -> list[tuple[int, str, Callable[[sqlite3.Connection], None]]]:
    """Return ``(version, module_name, migrate_fn)`` tuples sorted by version."""
    pkg = importlib.import_module(__name__)
    out: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        m = _MIGRATION_NAME_RE.match(info.name)
        if m is None:
            continue
        version = int(m.group(1))
        mod = importlib.import_module(f"{__name__}.{info.name}")
        fn = getattr(mod, "migrate", None)
        if not callable(fn):
            # Non-SQLite migrations (e.g. parquet migrations) live in the same
            # package but expose a differently-named entry point. Skip them
            # silently — they have their own runner.
            logger.debug("Migration %s has no callable migrate(); skipping.", info.name)
            continue
        out.append((version, info.name, fn))
    out.sort(key=lambda t: t[0])
    return out


def apply_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply any unseen numbered migrations and return the list of new versions.

    Idempotent — safe to call on every connection open. Each migration runs in
    a single transaction; the ``schema_version`` row is inserted in the same
    commit so partial application is impossible.
    """
    applied = applied_versions(conn)
    migrations = discover_migrations()
    newly_applied: list[int] = []
    for version, name, fn in migrations:
        if version in applied:
            continue
        logger.info("Applying sqlite migration %s (v%d)", name, version)
        try:
            fn(conn)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(UTC).isoformat()),
            )
            conn.commit()
        except sqlite3.DatabaseError:
            conn.rollback()
            raise
        newly_applied.append(version)
    return newly_applied
