# ADR-001: SQLite Connection Management Strategy

- **Status:** Accepted
- **Date:** 2026-04-20
- **Deciders:** John Eakin
- **Trigger:** Code review identified connection-per-call with autocommit as the #1 cross-cutting issue across all three review reports (P1-ARCH-1, RF-SMELL-001, Dev Assessment §14).

## Context

Historically, each `Repository` method opened a new SQLite connection per call. As of 2026-04-21, `Repository` is a **context manager** that holds one connection for `with Repository(path) as repo:` blocks. The problems below motivated that change:

1. **Data integrity risk.** Autocommit means each INSERT/UPDATE is its own transaction. A crash mid-batch (e.g., during `fetch_articles` writing 500 articles) leaves partial state with no rollback capability.
2. **Performance overhead.** During `collect_article_metadata`, each `article_url_exists` check and `upsert_article` call opens and closes a connection — potentially 10,000+ connection cycles for a full scrape. This overhead will multiply as Phases 4–7 add feature writes, analysis reads, and report queries.
3. **Shotgun surgery.** The `db_path` parameter appears in all 10 public repository functions. Changing the connection strategy (WAL mode, pooling, context manager) requires modifying every function signature.

The `fetcher.py` module mitigates concurrent access with a module-level `asyncio.Lock`, but this only serializes writes from a single caller — it cannot protect against interleaving from other pipeline stages or CLI invocations.

## Decision

Introduce a `Repository` class that owns connection lifecycle and exposes the existing functions as instance methods. Connections use WAL mode and explicit transaction boundaries.

### Design

```python
from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path
import sqlite3

class Repository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(self._db_path, isolation_level="DEFERRED")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        assert self._conn is not None, "Call connect() first"
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def upsert_author(self, ...) -> None:
        with self.transaction() as conn:
            conn.execute(...)

    # ... remaining methods as instance methods
```

### Migration Path

1. Create `Repository` class alongside existing functions (Phase 1 — non-breaking).
2. Update `cli.py` and `fetcher.py` to instantiate `Repository` and pass it through (Phase 2).
3. Deprecate and remove the standalone functions (Phase 3).
4. Each phase must have passing tests before proceeding.

### WAL Mode

Enable `PRAGMA journal_mode=WAL` on every connection. This allows concurrent readers during writes and eliminates most `SQLITE_BUSY` errors without changing the single-writer model.

### Transaction Boundaries

- **Batch operations** (scrape metadata collection, feature vector writes) should wrap the entire batch in a single transaction.
- **Individual lookups** (`article_url_exists`, `get_author`) use autocommit reads (WAL mode makes this safe).
- **Pipeline stage transitions** commit at stage boundaries, never mid-stage.

## Consequences

- **Eliminates** the data clump (`db_path` in every function signature).
- **Enables** transactional grouping for batch operations.
- **Enables** WAL mode configuration in a single place.
- **Requires** updating all callers (cli.py, crawler.py, fetcher.py, dedup.py) — estimated 2–3 hours.
- **Requires** updating all tests that use repository functions directly.
- The `fetcher.py` `db_lock` pattern can be simplified since the Repository handles connection safety.

## Related

- GUARDRAILS.md: Sign "Connection-per-call in repository functions"
- Code Review Report: P1-ARCH-1, P2-PERF-2, P2-SCALE-1
- Refactoring Report: RF-SMELL-001
