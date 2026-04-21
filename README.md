# mediaite-ghostink

Forensics pipeline scaffold for `scrape → extract → analyze → report`.

[![CI](https://github.com/Abstract-Data/mediaite-ghostink/actions/workflows/ci.yml/badge.svg)](https://github.com/Abstract-Data/mediaite-ghostink/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3130/)
[![uv](https://img.shields.io/badge/uv-package%20manager-5A0FC8?logo=uv&logoColor=white)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pytest](https://img.shields.io/badge/testing-pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Hypothesis](https://img.shields.io/badge/property%20tests-hypothesis-6A4D8F)](https://hypothesis.readthedocs.io/)
[![Coverage](https://img.shields.io/badge/coverage-pytest--cov%20%E2%80%94%20%E2%89%A560%25%20lines-informational)](https://github.com/Abstract-Data/mediaite-ghostink/blob/main/pyproject.toml)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![packaging](https://img.shields.io/badge/build-hatchling-3775A9)](https://github.com/pypa/hatch)

Pull requests get a **CI report** comment with pytest totals and line coverage (vs `main`) from [`ci-report.yml`](.github/workflows/ci-report.yml).

## Quickstart

```bash
uv sync
uv run forensics all
uv run pytest tests/ -v
```

### Quality

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v --cov=src --cov-report=term-missing
```
