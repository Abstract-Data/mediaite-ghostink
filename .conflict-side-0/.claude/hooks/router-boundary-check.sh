#!/usr/bin/env bash
# PostToolUse hook — Router Boundary Check
# Warns on direct DB operations in router/api layer.
# Severity: WARNING

set -euo pipefail

TOOL_NAME="${TOOL_NAME:-}"
FILE_PATH="${FILE_PATH:-}"

[[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]] || exit 0
[[ "$FILE_PATH" == *.py ]] || exit 0

# Only check router/api layer paths
ROUTER_PATTERNS="router/|routers/|api/|endpoints/"
if ! echo "$FILE_PATH" | grep -qE "$ROUTER_PATTERNS"; then
  exit 0
fi

VIOLATIONS=$(grep -nE "(session\.(exec|execute|query|add|delete|commit|flush|refresh)|\.select\(|\.insert\(|\.update\(|\.delete\()" "$FILE_PATH" 2>/dev/null || true)

if [[ -n "$VIOLATIONS" ]]; then
  echo "⚠️  ROUTER BOUNDARY WARNING: Direct DB operations in router layer"
  echo "   File: $FILE_PATH"
  echo ""
  echo "   Violations:"
  echo "$VIOLATIONS" | while IFS= read -r line; do
    echo "     $line"
  done
  echo ""
  echo "   Route handlers should delegate to service/repository layers."
  echo "   Move DB operations to services/ or repositories/."
fi
