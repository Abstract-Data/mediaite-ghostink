#!/usr/bin/env python3
from __future__ import annotations

from _hook_utils import ask, extract_paths, read_payload


def main() -> None:
    payload = read_payload()
    paths = [path.lower() for path in extract_paths(payload)]
    touched_migrations = [path for path in paths if "alembic/versions/" in path]
    if not touched_migrations:
        return

    ask(
        "Alembic versions were touched. Confirm this is a new migration and not editing history.",
        (
            "Alembic versions guard triggered. Editing historical migrations can corrupt state. "
            f"Matched: {', '.join(touched_migrations)}"
        ),
    )


if __name__ == "__main__":
    main()
