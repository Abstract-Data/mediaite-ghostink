#!/usr/bin/env bash
# PostToolUse hook — Hand-Built Data Path Check
# Warns when code constructs data/ paths manually instead of using AnalysisArtifactPaths.
# Severity: WARNING
#
# INSTALL: Copy to .claude/hooks/handbuilt-path-check.sh
# REGISTER: Add to .claude/hooks.json PostToolUse array:
#   {"name": "Hand-Built Data Path", "command": "bash .claude/hooks/handbuilt-path-check.sh", "severity": "warning"}

set -euo pipefail

TOOL_NAME="${TOOL_NAME:-}"
FILE_PATH="${FILE_PATH:-}"

[[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]] || exit 0
[[ "$FILE_PATH" == *.py ]] || exit 0

# Only check src/forensics/ production code
if ! echo "$FILE_PATH" | grep -qE "src/forensics/"; then
  exit 0
fi

# Skip the artifact paths module itself and config
if echo "$FILE_PATH" | grep -qE "(artifact_paths|analysis_paths|config/|tests?/)"; then
  exit 0
fi

# Look for hand-built data paths: / "data" / "features" etc.
VIOLATIONS=$(grep -nE '/"data"\s*/\s*"(features|analysis|reports|raw|pipeline|probability|baseline|drift)"' "$FILE_PATH" 2>/dev/null || true)

if [[ -n "$VIOLATIONS" ]]; then
  echo "⚠️  HAND-BUILT PATH WARNING: Manual data/ path construction detected"
  echo "   File: $FILE_PATH"
  echo ""
  echo "   Violations:"
  echo "$VIOLATIONS" | while IFS= read -r line; do
    echo "     $line"
  done
  echo ""
  echo "   Use AnalysisArtifactPaths methods instead."
  echo "   See GUARDRAILS Sign: Hand-Built Data Paths Instead of Centralized Helpers"
fi
