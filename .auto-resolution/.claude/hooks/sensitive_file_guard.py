#!/usr/bin/env python3
from __future__ import annotations

from _hook_utils import deny, extract_paths, normalize_text, read_payload

SENSITIVE_MARKERS = (
    ".env",
    "secrets",
    "credentials",
    "id_rsa",
    "id_ed25519",
    "service-account",
    "private.key",
)


def main() -> None:
    payload = read_payload()
    raw_text = normalize_text(payload).lower()
    paths = [path.lower() for path in extract_paths(payload)]
    sensitive_paths = [
        path for path in paths if any(marker in path for marker in SENSITIVE_MARKERS)
    ]

    if not sensitive_paths:
        return

    deny(
        "Blocked operation on a sensitive file path.",
        (
            "Sensitive file guard triggered. Use `.env.example` placeholders and keep "
            "secrets out of "
            f"repo paths. Matched paths: {', '.join(sensitive_paths)} | payload: {raw_text[:800]}"
        ),
    )


if __name__ == "__main__":
    main()
