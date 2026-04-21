#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REQUIRED_METADATA = [
    "Version",
    "Last Updated",
    "Environment",
    "Model",
]

REQUIRED_SECTIONS = [
    "## Project Profile",
    "## Agent Scope",
    "## Commands",
    "## Working Rules",
    "## Tool Permissions by Mode",
    "## Conflict Resolution Hierarchy",
    "## Notion References",
]

STAGING_REQUIRED_SECTIONS = [
    "## Staging Scope",
    "## Allowed Commands",
    "## Blocked Actions",
    "## Staging Evaluation Gate",
]


def validate_agents_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"{path}: file not found"]

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    for field in REQUIRED_METADATA:
        pattern = re.compile(rf"^#\s*{re.escape(field)}\s*:", re.MULTILINE)
        if not pattern.search(content):
            errors.append(f"{path}: missing metadata field `{field}`")

    required_sections = (
        STAGING_REQUIRED_SECTIONS if path.name.lower() == "agents.staging.md" else REQUIRED_SECTIONS
    )

    for section in required_sections:
        if section not in content:
            errors.append(f"{path}: missing required section `{section}`")

    if lines:
        expected_heading = (
            "# AGENTS.staging.md" if path.name.lower() == "agents.staging.md" else "# AGENTS.md"
        )
        if not lines[0].startswith(expected_heading):
            errors.append(f"{path}: first heading should be `{expected_heading}`")

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    files = sorted(root.glob("AGENTS*.md"))
    if not files:
        print("No AGENTS*.md files found.")
        return 1

    all_errors: list[str] = []
    for file in files:
        all_errors.extend(validate_agents_file(file))

    if all_errors:
        print("AGENTS governance lint failed:")
        for err in all_errors:
            print(f"- {err}")
        return 1

    print("AGENTS governance lint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
