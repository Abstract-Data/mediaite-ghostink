# Deployments

## Current State

This repository is currently a local-first pipeline scaffold. There is no production deployment target committed yet.

## Environments

- `dev`: primary working environment for feature iteration
- `staging`: restricted validation environment with stricter change controls

## Release Readiness Checklist

Before promoting a version:

1. `uv sync`
2. `uv run ruff check .`
3. `uv run ruff format --check .`
4. `uv run pytest tests/ -v`
5. `uv run pytest tests/evals/ -v` (when eval tests exist)
6. Verify `uv run forensics all` produces expected artifacts in `data/`

## Packaging and Versioning

- Package metadata lives in `pyproject.toml`.
- CLI entry point is `forensics = "forensics.cli:main"`.
- Follow semantic versioning in `[project].version`.

## CI Expectations

When CI is enabled/expanded, it should enforce:

- Ruff lint/format checks
- Unit/integration/eval test execution
- Coverage threshold from `pyproject.toml`

## Future Deployment Notes

If an API/service deployment is introduced later:

- Add runtime-specific runbooks here.
- Document environment variables in `.env.example`.
- Preserve current pipeline command compatibility where possible.
