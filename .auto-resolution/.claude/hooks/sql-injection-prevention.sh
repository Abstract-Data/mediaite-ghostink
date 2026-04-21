#!/usr/bin/env bash
# PostToolUse hook — SQL Injection Prevention
# Catches f-strings, concat, .format(), % in text() calls.
# Severity: BLOCKER

set -euo pipefail

TOOL_NAME="${TOOL_NAME:-}"
FILE_PATH="${FILE_PATH:-}"

[[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]] || exit 0
[[ "$FILE_PATH" == *.py ]] || exit 0

# Skip test files — tests may intentionally test SQL building
if echo "$FILE_PATH" | grep -qE "tests?/"; then
  exit 0
fi

VIOLATIONS=$(grep -nE '(text\(f"|text\(f'"'"'|text\([^)]*\+|text\([^)]*\.format\(|text\([^)]*%\s)' "$FILE_PATH" 2>/dev/null || true)

if [[ -n "$VIOLATIONS" ]]; then
  echo "🚫 SQL INJECTION BLOCKER: Unsafe string interpolation in SQL text()"
  echo "   File: $FILE_PATH"
  echo ""
  echo "   Violations:"
  echo "$VIOLATIONS" | while IFS= read -r line; do
    echo "     $line"
  done
  echo ""
  echo "   Use parameterized queries instead:"
  echo "     ✅ text('SELECT * FROM users WHERE id = :id').bindparams(id=user_id)"
  echo "     ❌ text(f'SELECT * FROM users WHERE id = {user_id}')"
  echo ""
  echo "   This is a BLOCKER — do not proceed until fixed."
  exit 1
fi
