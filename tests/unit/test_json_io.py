"""Unit tests for the shared ``write_json_artifact`` helper (B1 / RF-DRY-001)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from forensics.storage.json_io import _to_jsonable, write_json_artifact


class _Sample(BaseModel):
    name: str
    score: float


def test_write_json_artifact_creates_parents(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "subdir" / "out.json"
    write_json_artifact(target, {"a": 1})
    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def test_write_json_artifact_serialises_single_model(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    write_json_artifact(target, _Sample(name="x", score=0.5))
    assert json.loads(target.read_text(encoding="utf-8")) == {"name": "x", "score": 0.5}


def test_write_json_artifact_serialises_list_of_models(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    payload = [_Sample(name="a", score=0.1), _Sample(name="b", score=0.9)]
    write_json_artifact(target, payload)
    result = json.loads(target.read_text(encoding="utf-8"))
    assert result == [{"name": "a", "score": 0.1}, {"name": "b", "score": 0.9}]


def test_write_json_artifact_handles_datetime_default_str(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    ts = datetime(2026, 4, 22, 10, 30, tzinfo=UTC)
    write_json_artifact(target, {"when": ts})
    result = json.loads(target.read_text(encoding="utf-8"))
    # ``default=str`` routes datetime through ``str(ts)`` — timezone-stamped ISO.
    assert "2026-04-22" in result["when"]


def test_write_json_artifact_atomic_replace(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    target.write_text("stale", encoding="utf-8")
    write_json_artifact(target, {"fresh": True})
    # No leftover .tmp siblings.
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".out.json.")]
    assert leftovers == []
    assert json.loads(target.read_text(encoding="utf-8")) == {"fresh": True}


def test_to_jsonable_recurses_into_nested_containers() -> None:
    payload = {
        "top": _Sample(name="x", score=0.5),
        "nested": [_Sample(name="a", score=0.1), {"inner": _Sample(name="b", score=0.2)}],
    }
    out = _to_jsonable(payload)
    assert out == {
        "top": {"name": "x", "score": 0.5},
        "nested": [
            {"name": "a", "score": 0.1},
            {"inner": {"name": "b", "score": 0.2}},
        ],
    }


def test_write_json_artifact_respects_indent(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    write_json_artifact(target, {"a": 1}, indent=4)
    text = target.read_text(encoding="utf-8")
    assert '    "a": 1' in text


def test_write_json_artifact_cleans_tmp_when_rename_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,  # noqa: F821
) -> None:
    """A cross-FS rename (or any ``OSError``) must not leave a stray ``.tmp`` sibling."""
    import os as os_mod

    target = tmp_path / "out.json"

    real_replace = os_mod.replace

    def failing_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated cross-fs rename")

    monkeypatch.setattr("forensics.storage.json_io.os.replace", failing_replace)

    import pytest as pytest_mod

    with pytest_mod.raises(OSError):
        write_json_artifact(target, {"oops": True})

    # The failure bubbles up but the tempfile sibling is cleaned up.
    siblings = [p for p in tmp_path.iterdir() if p.name.startswith(".out.json.")]
    assert siblings == []

    # Sanity: restore replace and verify a subsequent successful write still works.
    monkeypatch.setattr("forensics.storage.json_io.os.replace", real_replace)
    write_json_artifact(target, {"ok": True})
    assert target.is_file()
