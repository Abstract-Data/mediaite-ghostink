#!/usr/bin/env bash
# PostToolUse hook — Domain Purity Check
# Warns when framework imports appear in domain/core/logic/services layers.
# Severity: WARNING

set -euo pipefail

TOOL_NAME="${TOOL_NAME:-}"
FILE_PATH="${FILE_PATH:-}"

[[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]] || exit 0
[[ "$FILE_PATH" == *.py ]] || exit 0

# Only check domain layer paths
DOMAIN_PATTERNS="domain/|core/|logic/|services/"
if ! echo "$FILE_PATH" | grep -qE "$DOMAIN_PATTERNS"; then
  exit 0
fi

# Framework imports that should NOT appear in domain layers
VIOLATIONS=$(grep -nE "^(from|import)\s+(fastapi|httpx|sqlmodel|sqlalchemy|starlette|uvicorn|pydantic_settings)" "$FILE_PATH" 2>/dev/null || true)

if [[ -n "$VIOLATIONS" ]]; then
  echo "⚠️  DOMAIN PURITY WARNING: Framework imports detected in domain layer"
  echo "   File: $FILE_PATH"
  echo ""
  echo "   Violations:"
  echo "$VIOLATIONS" | while IFS= read -r line; do
    echo "     $line"
  done
  echo ""
  echo "   Domain layers should only depend on stdlib, domain models, and pure libraries."
  echo "   Move framework-specific code to adapters/ or api/ layers."
fi
