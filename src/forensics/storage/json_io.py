"""Shared JSON artifact writer for the analysis/survey/calibration stages.

Prior to this module each stage independently duplicated the
``json.dumps(..., indent=2, default=str)`` + ``Path.write_text`` + ``mkdir``
ceremony (see RF-DRY-001). Centralising the serialisation path keeps the
encoding, indentation, atomic-write, and Pydantic handling rules in one place.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_JsonLike = BaseModel | Mapping[str, Any] | Sequence[Any] | str | int | float | bool | None


def ensure_parent(path: Path) -> None:
    """Create parent directories for a file path (RF-DRY-004)."""
    path.parent.mkdir(parents=True, exist_ok=True)


def ensure_dir(path: Path) -> None:
    """Create a directory path if missing (RF-DRY-004)."""
    path.mkdir(parents=True, exist_ok=True)


def _to_jsonable(payload: Any) -> Any:
    """Return a JSON-ready representation of ``payload``.

    Pydantic models collapse to their ``model_dump(mode="json")`` form so that
    downstream ``json.dumps`` does not need to know about Pydantic at all.
    Anything else is returned unchanged; a ``default=str`` fallback catches
    stragglers like ``datetime`` and ``Path`` at serialise time.
    """
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, Mapping):
        return {key: _to_jsonable(value) for key, value in payload.items()}
    if isinstance(payload, list | tuple):
        return [_to_jsonable(item) for item in payload]
    return payload


def write_json_artifact(
    path: Path,
    payload: Any,
    *,
    indent: int = 2,
    sort_keys: bool = True,
) -> None:
    """Atomically write ``payload`` as JSON to ``path``.

    - Creates parent directories when absent.
    - Accepts plain primitives, dicts, lists, ``BaseModel`` instances, and
      lists/dicts containing them. Nested Pydantic models are normalised via
      :func:`_to_jsonable`.
    - Writes to a sibling tempfile then atomically renames over ``path`` so a
      crash mid-write cannot corrupt a pre-existing artifact.
    - ``sort_keys=True`` by default (Phase 15 H2) so two equivalent payloads
      serialise to byte-identical bytes regardless of dict-insertion order.
      Set ``sort_keys=False`` only when an artifact's reader depends on a
      specific top-level key ordering (none currently do).
    """
    ensure_parent(path)
    rendered = json.dumps(_to_jsonable(payload), indent=indent, sort_keys=sort_keys, default=str)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(rendered)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)

    try:
        os.replace(tmp_path, path)
    except OSError:
        # Cross-FS rename or a permission error left the sibling tempfile on disk.
        # Drop it so the caller doesn't see a ``.{name}.*.tmp`` leak next to the
        # final artifact — then re-raise so the failure is still visible.
        tmp_path.unlink(missing_ok=True)
        raise


def write_text_atomic(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Atomically write ``text`` to ``path``, creating parent dirs as needed.

    Mirrors :func:`write_json_artifact`'s atomic-rename pattern for callers
    that need to write pre-rendered text (Quarto-style reports, model cards,
    custody records). Centralising this removes the
    ``path.parent.mkdir(...)`` + ``path.write_text(...)`` pair from every
    caller (RF-DRY-004 / G1).
    """
    ensure_parent(path)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding=encoding,
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    try:
        os.replace(tmp_path, path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


# Sort-key spec from prompts/phase15-optimizations/v0.4.0.md lines 1604-1620.
# Kept module-level so the routing is data, not control flow — and so a future
# artifact kind only requires adding a row, not editing logic.
_ARTIFACT_SORT_KEYS: dict[str, tuple[str, ...]] = {
    "change_points": ("feature_name", "timestamp", "effect_size_cohens_d"),
    "hypothesis_tests": ("feature_name", "test_name"),
    "convergence_windows": ("start_date", "end_date"),
}


def stable_sort_artifact_list(items: list[Any], *, kind: str) -> list[Any]:
    """Sort a list of artifact records by a stable, semantic key (Phase 15 H2).

    Two parallel runs of the same analysis must produce byte-identical JSON
    artifacts. Object identity / dict insertion order leak into the wire
    format unless we explicitly sort list-valued fields. ``kind`` selects the
    per-list key from :data:`_ARTIFACT_SORT_KEYS`. ``KeyError`` on an unknown
    ``kind`` is intentional — undefined kinds must not silently pass.

    Items can be Pydantic models or plain dicts; both are read via ``getattr``
    + ``Mapping.get`` so the same call works either side of a ``model_dump``.
    """
    sort_fields = _ARTIFACT_SORT_KEYS[kind]

    def _key(record: Any) -> tuple[str, ...]:
        if isinstance(record, Mapping):
            return tuple(str(record.get(f, "")) for f in sort_fields)
        return tuple(str(getattr(record, f, "")) for f in sort_fields)

    return sorted(items, key=_key)


__all__ = [
    "ensure_dir",
    "ensure_parent",
    "stable_sort_artifact_list",
    "write_json_artifact",
    "write_text_atomic",
]
