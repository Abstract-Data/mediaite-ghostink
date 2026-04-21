#!/usr/bin/env bash
# PostToolUse hook — Environment Variable Leak Prevention
# Warns on os.environ usage outside config.py/settings.py.
# Severity: WARNING

set -euo pipefail

TOOL_NAME="${TOOL_NAME:-}"
FILE_PATH="${FILE_PATH:-}"

[[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]] || exit 0
[[ "$FILE_PATH" == *.py ]] || exit 0

# Allow config files to use os.environ
if echo "$FILE_PATH" | grep -qE "(config\.py|settings\.py|conftest\.py)"; then
  exit 0
fi

# Skip tests
if echo "$FILE_PATH" | grep -qE "tests?/"; then
  exit 0
fi

VIOLATIONS=$(grep -nE "(os\.environ|os\.getenv|environ\.get)" "$FILE_PATH" 2>/dev/null || true)

if [[ -n "$VIOLATIONS" ]]; then
  echo "⚠️  ENV VARIABLE LEAK WARNING: os.environ used outside config layer"
  echo "   File: $FILE_PATH"
  echo ""
  echo "   Violations:"
  echo "$VIOLATIONS" | while IFS= read -r line; do
    echo "     $line"
  done
  echo ""
  echo "   Centralize environment access in config.py using pydantic-settings:"
  echo "     from forensics.config import settings"
  echo "     value = settings.MY_SETTING"
fi
