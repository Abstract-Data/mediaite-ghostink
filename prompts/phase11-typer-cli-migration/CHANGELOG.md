# Changelog

## [0.1.0] - 2026-04-20
### Added
- Initial spec: migrate argparse CLI to Typer with one-file-per-subcommand package structure
- Complete CLI surface area inventory across all 10 phases
- `src/forensics/cli/` package: `__init__.py` (app assembly), `_helpers.py` (shared), `scrape.py`, `extract.py`, `analyze.py`, `report.py`
- Pre-wired stub flags for Phases 6-10: `--drift`, `--convergence`, `--compare`, `--ai-baseline`, `--skip-generation`, `--verify-corpus`, `--probability`, `--no-binoculars`, `--device`, `--notebook`, `--format`, `--verify`
- Test rewrites for Typer CliRunner (test_cli.py, test_cli_scrape_dispatch.py)
- `--version` and `--verbose` global options
