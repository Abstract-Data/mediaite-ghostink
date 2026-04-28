# Contributing

Thank you for helping improve this repository. This document is for **human** contributors; automation and agent rules also live in [`AGENTS.md`](AGENTS.md).

## Prerequisites

- **Python 3.13** and **[uv](https://github.com/astral-sh/uv)** on your `PATH`.
- Clone the repo and install dev dependencies:

  ```bash
  uv sync --extra dev
  uv run python -m spacy download en_core_web_md
  ```

## Before you open a pull request

1. **Lint and format**

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   ```

2. **Tests**

   ```bash
   uv run pytest tests/ -v
   ```

   See [`docs/TESTING.md`](docs/TESTING.md) for markers, coverage expectations, and slow-test policy.

3. **Optional pre-commit**

   ```bash
   uv run pre-commit install
   uv run pre-commit run --all-files
   ```

## Session handoff

For any **multi-step** or non-trivial change, append a completion block to [`HANDOFF.md`](HANDOFF.md) using the template at the top of that file. When the completion log grows past roughly **200 lines**, archive older blocks to [`docs/archive/handoff-history.md`](docs/archive/handoff-history.md) in the same change set (see [`AGENTS.md`](AGENTS.md)).

## Internal coordination

The optional internal work queue lives in [`docs/TASK.md`](docs/TASK.md).

## Git workflow

Use conventional commits (`feat:`, `fix:`, `docs:`, …). If you use **GitButler**, follow [`.claude/skills/gitbutler/SKILL.md`](.claude/skills/gitbutler/SKILL.md) (mirrored under [`.cursor/skills/gitbutler/`](.cursor/skills/gitbutler/)).

## License

By contributing, you agree your contributions are licensed under the terms in [`LICENSE`](LICENSE).
