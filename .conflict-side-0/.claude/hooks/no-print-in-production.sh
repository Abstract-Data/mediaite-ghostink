#!/usr/bin/env bash
# PostToolUse hook — No print() in Production
# Warns on print() usage in src/app code (use logging instead).
# Severity: WARNING

set -euo pipefail

TOOL_NAME="${TOOL_NAME:-}"
FILE_PATH="${FILE_PATH:-}"

[[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]] || exit 0
[[ "$FILE_PATH" == *.py ]] || exit 0

# Skip tests, scripts, CLI, and notebooks
if echo "$FILE_PATH" | grep -qE "(tests?/|scripts?/|cli\.py|notebooks?/|__main__\.py)"; then
  exit 0
fi

# Only check src/app production code
if ! echo "$FILE_PATH" | grep -qE "(src/|app/)"; then
  exit 0
fi

VIOLATIONS=$(grep -nE "^\s*print\(" "$FILE_PATH" 2>/dev/null || true)

if [[ -n "$VIOLATIONS" ]]; then
  echo "⚠️  NO PRINT WARNING: print() found in production code"
  echo "   File: $FILE_PATH"
  echo ""
  echo "   Violations:"
  echo "$VIOLATIONS" | while IFS= read -r line; do
    echo "     $line"
  done
  echo ""
  echo "   Use structured logging instead:"
  echo "     import logging"
  echo "     logger = logging.getLogger(__name__)"
  echo "     logger.info('message')"
fi
