#!/usr/bin/env bash
# PostToolUse hook — Function Length Guard
# Warns when a function in src/forensics/ exceeds 50 lines.
# Functions with "# complexity: justified" are exempt.
# Severity: WARNING
#
# INSTALL: Copy to .claude/hooks/function-length-guard.sh
# REGISTER: Add to .claude/hooks.json PostToolUse array:
#   {"name": "Function Length Guard", "command": "bash .claude/hooks/function-length-guard.sh", "severity": "warning"}

set -euo pipefail

TOOL_NAME="${TOOL_NAME:-}"
FILE_PATH="${FILE_PATH:-}"

[[ "$TOOL_NAME" == "Write" || "$TOOL_NAME" == "Edit" ]] || exit 0
[[ "$FILE_PATH" == *.py ]] || exit 0

# Only check src/forensics/ production code
if ! echo "$FILE_PATH" | grep -qE "src/forensics/"; then
  exit 0
fi

# Skip test files
if echo "$FILE_PATH" | grep -qE "tests?/"; then
  exit 0
fi

# Use Python to count function body lines (excluding blanks, comments, docstrings)
OUTPUT=$(python3 -c "
import sys

with open(sys.argv[1], 'r') as f:
    lines = f.readlines()

in_func = False
func_name = ''
func_start = 0
func_lines = 0
justified = any('# complexity: justified' in l for l in lines)
violations = []

for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if stripped.startswith('def ') or stripped.startswith('async def '):
        if in_func and func_lines > 50:
            violations.append((func_name, func_start, func_lines))
        func_name = stripped.split('(')[0].replace('def ', '').replace('async ', '')
        func_start = i
        func_lines = 0
        in_func = True
        continue
    if in_func:
        if stripped and not stripped.startswith('#') and stripped not in ('\"\"\"', \"'''\"):
            func_lines += 1

if in_func and func_lines > 50:
    violations.append((func_name, func_start, func_lines))

if violations and not justified:
    for name, start, count in violations:
        print(f'  {name} (line {start}): {count} lines')
" "$FILE_PATH" 2>/dev/null || true)

if [[ -n "$OUTPUT" ]]; then
  echo "⚠️  FUNCTION LENGTH WARNING: Function(s) exceed 50 lines"
  echo "   File: $FILE_PATH"
  echo ""
  echo "$OUTPUT"
  echo ""
  echo "   Decompose per GUARDRAILS Sign: God Function Exceeding 50 Lines"
  echo "   If justified (e.g., algorithm), add '# complexity: justified' comment to the file"
fi
