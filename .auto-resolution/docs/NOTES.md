# NOTES.md — Cross-Platform Development Notes

## Project: mediaite-ghostink

This file captures platform-specific notes for developers using different AI tools (Claude Code, Cursor, Windsurf, etc.) on this project.

## Claude Code

- Primary agent config: `AGENTS.md` (dev mode)
- Staging constraints: `AGENTS.staging.md`
- Hooks: `.claude/hooks.json` (5 PostToolUse hooks)
- Session management: `.claude/settings.json`
- Evals: `.claude/evals/`

## Cursor

- If using Cursor, create `.cursor/rules/` with project-specific .mdc rules
- Reference AGENTS.md standards in rule files
- Use glob-scoped rules for stage-specific guidance

## General Notes

- Always use `uv run` for Python execution — never bare `python`
- Pipeline stages are architecturally sacred — do not merge or bypass
- Embedding model is pinned to `all-MiniLM-L6-v2` — do not upgrade without re-running all analysis
- WordPress API scraping uses rate limiting with jitter — do not remove delays
