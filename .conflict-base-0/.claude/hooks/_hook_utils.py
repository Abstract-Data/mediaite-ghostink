#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_LOG_DIR = REPO_ROOT / ".claude" / "hooks" / "logs"


def read_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {}


def emit(payload: dict[str, Any] | None = None) -> None:
    print(json.dumps(payload or {}))


def deny(user_message: str, agent_message: str) -> None:
    emit({"permission": "deny", "user_message": user_message, "agent_message": agent_message})
    sys.exit(2)


def ask(user_message: str, agent_message: str) -> None:
    emit({"permission": "ask", "user_message": user_message, "agent_message": agent_message})
    sys.exit(0)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return str(value)


def extract_strings(data: Any) -> list[str]:
    values: list[str] = []
    if isinstance(data, str):
        values.append(data)
    elif isinstance(data, dict):
        for key, value in data.items():
            values.extend(extract_strings(key))
            values.extend(extract_strings(value))
    elif isinstance(data, list):
        for item in data:
            values.extend(extract_strings(item))
    return values


def extract_paths(data: Any) -> list[str]:
    candidates = extract_strings(data)
    path_like = []
    for candidate in candidates:
        if "/" in candidate or candidate.startswith("."):
            path_like.append(candidate.strip())
    return sorted(set(path_like))


def get_shell_command(payload: dict[str, Any]) -> str:
    for key in ("command", "shell_command", "input", "tool_input"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested = value.get("command")
            if isinstance(nested, str):
                return nested
    return ""


def run_command(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd or REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def is_probably_binary(path: str) -> bool:
    return bool(re.search(r"\.(png|jpg|jpeg|gif|pdf|zip|gz|bin|sqlite|db)$", path, re.IGNORECASE))


def ensure_log_dir() -> None:
    HOOK_LOG_DIR.mkdir(parents=True, exist_ok=True)


def append_log(filename: str, line: str) -> None:
    ensure_log_dir()
    (HOOK_LOG_DIR / filename).open("a", encoding="utf-8").write(line + os.linesep)
