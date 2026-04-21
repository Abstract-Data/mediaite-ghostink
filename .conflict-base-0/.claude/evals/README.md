# Evals Directory

This directory contains evaluation configurations for testing agent behavior.

## Purpose

Evals verify that the AI agent (Claude Code or similar) produces correct, safe, and consistent outputs when working on the mediaite-ghostink project.

## Structure

Place eval YAML files in this directory. Each eval should test a specific agent capability:

- `pipeline_commands.yaml` — verify agent uses correct CLI commands
- `data_safety.yaml` — verify agent respects data safety guardrails
- `code_quality.yaml` — verify agent produces code meeting quality standards

## Running Evals

```bash
uv run pytest tests/evals/ -v
```
