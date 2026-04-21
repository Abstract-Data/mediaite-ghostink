#!/usr/bin/env python3
from __future__ import annotations

from datetime import UTC, datetime

from _hook_utils import append_log, get_shell_command, read_payload


def main() -> None:
    payload = read_payload()
    command = get_shell_command(payload)
    if not command:
        return

    exit_code = payload.get("exit_code", payload.get("code", "unknown"))
    timestamp = datetime.now(UTC).isoformat()
    append_log("command_audit.log", f"{timestamp} exit={exit_code} command={command}")


if __name__ == "__main__":
    main()
