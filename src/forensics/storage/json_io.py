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
    if isinstance(payload, (list, tuple)):
        return [_to_jsonable(item) for item in payload]
    return payload


def write_json_artifact(
    path: Path,
    payload: Any,
    *,
    indent: int = 2,
) -> None:
    """Atomically write ``payload`` as JSON to ``path``.

    - Creates parent directories when absent.
    - Accepts plain primitives, dicts, lists, ``BaseModel`` instances, and
      lists/dicts containing them. Nested Pydantic models are normalised via
      :func:`_to_jsonable`.
    - Writes to a sibling tempfile then atomically renames over ``path`` so a
      crash mid-write cannot corrupt a pre-existing artifact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(_to_jsonable(payload), indent=indent, default=str)

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


__all__ = ["write_json_artifact"]
