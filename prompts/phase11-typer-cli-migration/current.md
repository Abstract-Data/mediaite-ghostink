# Phase 11: Typer CLI Migration

Version: 0.1.0
Status: pending
Last Updated: 2026-04-20
Model: gpt-5-3-codex
Depends on: Phase 5 (existing argparse CLI with scrape, extract, analyze wired up)

## Objective

Replace the argparse-based CLI (`src/forensics/cli.py`) with Typer, preserving all existing behavior and pre-wiring the command surface for Phases 6–10. After this prompt, `uv run forensics --help` renders a rich help page via Typer, all existing commands work identically, and future phase flags (`--drift`, `--convergence`, `--probability`, `--notebook`, etc.) are defined as stubs ready to be implemented.

The key design principle is **one file per subcommand group** under `src/forensics/cli/`. Shared helpers (config fingerprint, placeholder guard, logging setup) move to `_helpers.py`. The root app is assembled in `__init__.py`. Existing async pipeline functions stay untouched — only the argument parsing and dispatch layer changes.

## Pre-flight

```bash
cd "$(git rev-parse --show-toplevel)"
uv sync
uv run ruff check .
uv run pytest tests/ -v
```

Confirm all tests pass before starting. The current CLI at `src/forensics/cli.py` is ~410 lines of argparse with 5 subcommands (`scrape`, `extract`, `analyze`, `report`, `all`). Read it before editing.

## Non-goals

- Refactoring the scrape dispatch logic (the boolean flag combination routing is tested and correct — preserve it exactly)
- Implementing Phase 6/7/8/9/10 logic (only define the flags as stubs)
- Changing any pipeline function signatures or behavior
- Adding click or other CLI frameworks alongside Typer

## 1. CLI Surface Area (Complete Inventory)

This is the full set of commands and flags the migration must support. Commands marked **[existing]** are already implemented in argparse; **[new]** are specified in phase prompts but not yet wired to real logic.

```
forensics --help
forensics --version

forensics scrape                                    [existing] full pipeline
forensics scrape --discover                         [existing]
forensics scrape --discover --force-refresh         [existing]
forensics scrape --metadata                         [existing]
forensics scrape --fetch                            [existing]
forensics scrape --fetch --dry-run                  [existing]
forensics scrape --dedup                            [existing]
forensics scrape --archive                          [existing]

forensics extract                                   [existing]
forensics extract --author SLUG                     [existing]
forensics extract --skip-embeddings                 [existing]
forensics extract --probability                     [new, Phase 9]
forensics extract --probability --no-binoculars     [new, Phase 9]
forensics extract --probability --device cpu|cuda   [new, Phase 9]

forensics analyze                                   [existing, partial]
forensics analyze --changepoint                     [existing]
forensics analyze --timeseries                      [existing]
forensics analyze --drift                           [new, Phase 6]
forensics analyze --convergence                     [new, Phase 7]
forensics analyze --compare                         [new, Phase 7]
forensics analyze --ai-baseline                     [new, Phase 6]
forensics analyze --ai-baseline --skip-generation   [new, Phase 6]
forensics analyze --author SLUG                     [existing]
forensics analyze --verify-corpus                   [new, Phase 10]

forensics report                                    [stub]
forensics report --notebook NN                      [new, Phase 8]
forensics report --format html|pdf                  [new, Phase 8]
forensics report --verify                           [new, Phase 8]

forensics all                                       [stub]
```

## 2. File Structure

### New files (create all of these)

```
src/forensics/
    cli/                         ← NEW package (replaces cli.py)
        __init__.py              ← Typer app assembly, version callback, main()
        _helpers.py              ← config_fingerprint, guard_placeholder_authors, logging setup
        scrape.py                ← scrape subcommand group
        extract.py               ← extract subcommand
        analyze.py               ← analyze subcommand
        report.py                ← report subcommand
```

### Files to delete

```
src/forensics/cli.py             ← old argparse module (replaced by cli/ package)
```

### Files to rewrite

```
tests/integration/test_cli.py              ← Typer CliRunner tests
tests/integration/test_cli_scrape_dispatch.py  ← async dispatch tests adapted for Typer
```

### Files to update (minor edits)

```
pyproject.toml                   ← add typer[all] dependency
AGENTS.md                        ← CLI line: argparse → Typer
HANDOFF.md                       ← append completion block
```

### Files that do NOT change

```
src/forensics/__main__.py        ← `from forensics.cli import main` still resolves
pyproject.toml [project.scripts] ← `forensics = "forensics.cli:main"` still resolves
```

Design decisions:

- **One file per subcommand group** keeps each module <150 lines and independently testable.
- **`_helpers.py`** holds shared logic so subcommand modules don't import each other.
- **`__init__.py`** is the assembly point — it imports each subcommand module and registers them with the root app. This is the only file that knows about all subcommands.
- **Async commands** use `asyncio.run()` inside the Typer callback, same as today. Typer doesn't natively support async, so the pattern is: Typer calls a sync function, which calls `asyncio.run(async_impl(...))`.
- **Scrape uses `add_typer()`**, others use `app.command()`. Scrape is a sub-app because it has `invoke_without_command=True` (bare `forensics scrape` = full pipeline). The other commands are simple functions registered directly on the root app.

## 3. Add Typer Dependency

Add to `[project.dependencies]` in `pyproject.toml`:

```toml
"typer[all]>=0.15.0",
```

Do NOT remove any existing dependencies. Run `uv sync` after editing.

## 4. Root App (`src/forensics/cli/__init__.py`)

```python
"""Typer CLI for the AI Writing Forensics pipeline."""

from __future__ import annotations

import importlib.metadata
import logging
from typing import Annotated, Optional

import typer

app = typer.Typer(
    name="forensics",
    help="AI Writing Forensics Pipeline",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        version = importlib.metadata.version("mediaite-ghostink")
        typer.echo(f"forensics {version}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True,
                     help="Show version and exit"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable DEBUG logging"),
    ] = False,
) -> None:
    """AI Writing Forensics Pipeline."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


# --- Register subcommands ---
from forensics.cli.scrape import scrape_app  # noqa: E402
from forensics.cli.extract import extract  # noqa: E402
from forensics.cli.analyze import analyze  # noqa: E402
from forensics.cli.report import report  # noqa: E402

app.add_typer(scrape_app, name="scrape")
app.command(name="extract")(extract)
app.command(name="analyze")(analyze)
app.command(name="report")(report)


@app.command(name="all")
def run_all() -> None:
    """Run full pipeline end-to-end: scrape → extract → analyze → report."""
    logger = logging.getLogger(__name__)
    logger.warning("Full pipeline orchestration not yet implemented")


def main() -> None:
    """Entrypoint called by pyproject.toml [project.scripts]."""
    app()
```

## 5. Shared Helpers (`src/forensics/cli/_helpers.py`)

Extract shared logic from the old `cli.py`:

```python
"""Shared CLI helpers — config fingerprint, placeholder guard, logging."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from forensics.config import get_project_root
from forensics.config.settings import ForensicsSettings

logger = logging.getLogger(__name__)

_PLACEHOLDER_SLUGS = frozenset({"placeholder-target", "placeholder-control"})


def config_fingerprint() -> str:
    """Short hash of the active TOML config file for ``analysis_runs``."""
    raw = os.environ.get("FORENSICS_CONFIG_FILE", "").strip()
    candidates = [Path(raw).expanduser()] if raw else []
    candidates.append(get_project_root() / "config.toml")
    for path in candidates:
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return digest[:48]
    return "no_config_file"


def guard_placeholder_authors(settings: ForensicsSettings) -> None:
    """Reject template slugs before any live scrape stage (P3-SEC-3).

    Raises typer.BadParameter if placeholder authors detected.
    """
    import typer

    if any(a.slug in _PLACEHOLDER_SLUGS for a in settings.authors):
        raise typer.BadParameter(
            "config.toml still uses template authors (slug placeholder-target / "
            "placeholder-control). Replace them with real author rows before scraping."
        )
```

## 6. Scrape Subcommand (`src/forensics/cli/scrape.py`)

This is the most complex subcommand — it has 7 boolean flags with combinatorial dispatch. Preserve the exact same dispatch logic from the old `_async_scrape`. The `_dispatch` async function is the testable core.

```python
"""Scrape subcommand — WordPress discovery, metadata collection, HTML fetch."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer

from forensics.cli._helpers import config_fingerprint, guard_placeholder_authors
from forensics.config import get_project_root, get_settings
from forensics.config.settings import ForensicsSettings
from forensics.scraper.crawler import collect_article_metadata, discover_authors
from forensics.scraper.dedup import deduplicate_articles
from forensics.scraper.fetcher import archive_raw_year_dirs, fetch_articles
from forensics.storage.export import export_articles_jsonl
from forensics.storage.repository import insert_analysis_run

logger = logging.getLogger(__name__)

scrape_app = typer.Typer(help="Crawl and fetch articles for configured authors")


def _export_jsonl(db_path: Path, root: Path) -> int:
    out = root / "data/articles.jsonl"
    return export_articles_jsonl(db_path, out)


async def _discover_only(
    settings: ForensicsSettings, manifest_path: Path, *, force_refresh: bool,
) -> int:
    n = await discover_authors(settings, force_refresh=force_refresh)
    if n:
        logger.info("discover: wrote %d author(s) to %s", n, manifest_path)
    else:
        logger.info(
            "discover: skipped (manifest exists). Use --force-refresh to overwrite. path=%s",
            manifest_path,
        )
    return 0


async def _metadata_only(
    db_path: Path, settings: ForensicsSettings, manifest_path: Path,
) -> int:
    if not manifest_path.is_file():
        logger.error(
            "author manifest not found: %s (run `forensics scrape --discover` first)",
            manifest_path,
        )
        return 1
    inserted = await collect_article_metadata(db_path, settings)
    logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
    return 0


async def _fetch_only(
    db_path: Path, settings: ForensicsSettings, *, dry_run: bool,
) -> int:
    n = await fetch_articles(db_path, settings, dry_run=dry_run)
    suffix = " (dry-run)" if dry_run else ""
    logger.info(
        "fetch: %s %d article(s)%s",
        "would fetch" if dry_run else "processed",
        n,
        suffix,
    )
    return 0


async def _fetch_dedup_export(
    db_path: Path, root: Path, settings: ForensicsSettings, *, dry_run: bool,
) -> int:
    n = await fetch_articles(db_path, settings, dry_run=dry_run)
    logger.info("fetch: processed %d article(s)%s", n, " (dry-run)" if dry_run else "")
    if not dry_run:
        dup_ids = deduplicate_articles(db_path)
        logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
        ex = _export_jsonl(db_path, root)
        logger.info("export: wrote %d article(s) to data/articles.jsonl", ex)
    return 0


async def _discover_and_metadata(
    db_path: Path, settings: ForensicsSettings, manifest_path: Path, *, force_refresh: bool,
) -> int:
    n_authors = await discover_authors(settings, force_refresh=force_refresh)
    if n_authors:
        logger.info("discover: wrote %d author(s) to %s", n_authors, manifest_path)
    else:
        logger.info("discover: skipped or unchanged (%s)", manifest_path)
    if not manifest_path.is_file():
        logger.error("author manifest missing after discover: %s", manifest_path)
        return 1
    inserted = await collect_article_metadata(db_path, settings)
    logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
    return 0


async def _full_pipeline(
    db_path: Path, root: Path, settings: ForensicsSettings,
    manifest_path: Path, *, force_refresh: bool,
) -> int:
    n_authors = await discover_authors(settings, force_refresh=force_refresh)
    if n_authors:
        logger.info("discover: wrote %d author(s) to %s", n_authors, manifest_path)
    else:
        logger.info("discover: skipped or unchanged (%s)", manifest_path)
    if not manifest_path.is_file():
        logger.error("author manifest missing after discover: %s", manifest_path)
        return 1
    inserted = await collect_article_metadata(db_path, settings)
    logger.info("metadata: inserted %d new article row(s) into %s", inserted, db_path)
    fetched = await fetch_articles(db_path, settings, dry_run=False)
    logger.info("fetch: processed %d article(s)", fetched)
    dup_ids = deduplicate_articles(db_path)
    logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
    ex = _export_jsonl(db_path, root)
    logger.info("export: wrote %d article(s) to data/articles.jsonl", ex)
    return 0


async def _dispatch(
    *,
    discover: bool,
    metadata: bool,
    fetch: bool,
    dedup: bool,
    archive: bool,
    dry_run: bool,
    force_refresh: bool,
) -> int:
    """Route flag combinations to the appropriate pipeline function.

    This is the testable core — all integration tests call this directly.
    """
    settings = get_settings()
    root = get_project_root()
    manifest_path = root / "data/authors_manifest.jsonl"
    db_path = root / "data/articles.db"

    if dry_run and not fetch:
        logger.error("--dry-run is only valid with --fetch")
        return 1

    # Guard placeholders for commands that hit the network
    if discover or metadata or fetch or not (discover or metadata or fetch or dedup or archive):
        guard_placeholder_authors(settings)

    try:
        insert_analysis_run(
            db_path, config_hash=config_fingerprint(), description="forensics scrape",
        )
    except OSError as exc:
        logger.warning("Could not record analysis_runs row: %s", exc)

    d, m, f, dd, ar = discover, metadata, fetch, dedup, archive

    if ar and not d and not m and not f and not dd:
        n = archive_raw_year_dirs(root, db_path)
        logger.info("archive: compressed %d year directory(ies) under data/raw/", n)
        return 0
    if dd and not d and not m and not f and not ar:
        dup_ids = deduplicate_articles(db_path)
        logger.info("dedup: marked %d article(s) as near-duplicates", len(dup_ids))
        return 0
    if f and not d and not m and not dd and not ar:
        return await _fetch_only(db_path, settings, dry_run=dry_run)
    if f and dd and not d and not m and not ar:
        return await _fetch_dedup_export(db_path, root, settings, dry_run=dry_run)
    if d and not m and not f and not dd and not ar:
        return await _discover_only(settings, manifest_path, force_refresh=force_refresh)
    if m and not d and not f and not dd and not ar:
        return await _metadata_only(db_path, settings, manifest_path)
    if d and m and not f and not dd and not ar:
        return await _discover_and_metadata(
            db_path, settings, manifest_path, force_refresh=force_refresh,
        )
    if not (d or m or f or dd or ar):
        return await _full_pipeline(
            db_path, root, settings, manifest_path, force_refresh=force_refresh,
        )

    logger.error(
        "unsupported flag combination for scrape "
        "(try individual --discover, --metadata, --fetch, --dedup, --archive)"
    )
    return 1


@scrape_app.callback(invoke_without_command=True)
def scrape(
    discover: Annotated[
        bool, typer.Option("--discover", help="Run WordPress author discovery only"),
    ] = False,
    metadata: Annotated[
        bool, typer.Option("--metadata", help="Collect article metadata only"),
    ] = False,
    fetch: Annotated[
        bool, typer.Option("--fetch", help="Fetch HTML and extract article text only"),
    ] = False,
    dedup: Annotated[
        bool, typer.Option("--dedup", help="Run near-duplicate detection only"),
    ] = False,
    archive: Annotated[
        bool, typer.Option("--archive", help="Compress data/raw/{year}/ to tar.gz"),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="With --fetch: report count without HTTP"),
    ] = False,
    force_refresh: Annotated[
        bool, typer.Option("--force-refresh", help="With --discover: overwrite manifest"),
    ] = False,
) -> None:
    """Crawl and fetch articles for configured authors."""
    rc = asyncio.run(
        _dispatch(
            discover=discover,
            metadata=metadata,
            fetch=fetch,
            dedup=dedup,
            archive=archive,
            dry_run=dry_run,
            force_refresh=force_refresh,
        )
    )
    raise typer.Exit(code=rc)
```

## 7. Extract Subcommand (`src/forensics/cli/extract.py`)

Adds Phase 9 probability flags as stubs alongside existing extract behavior:

```python
"""Extract subcommand — feature extraction pipeline."""

from __future__ import annotations

import logging
from typing import Annotated, Optional

import typer

from forensics.config import get_project_root, get_settings

logger = logging.getLogger(__name__)


def extract(
    author: Annotated[
        Optional[str],
        typer.Option("--author", metavar="SLUG", help="Limit to one author slug"),
    ] = None,
    skip_embeddings: Annotated[
        bool,
        typer.Option("--skip-embeddings", help="Skip sentence-transformer embeddings"),
    ] = False,
    probability: Annotated[
        bool,
        typer.Option("--probability", help="Extract probability features (perplexity, burstiness)"),
    ] = False,
    no_binoculars: Annotated[
        bool,
        typer.Option("--no-binoculars", help="With --probability: skip Binoculars scoring"),
    ] = False,
    device: Annotated[
        Optional[str],
        typer.Option("--device", help="Compute device: cpu or cuda (default: auto)"),
    ] = None,
) -> None:
    """Run feature extraction pipeline."""
    from forensics.features.pipeline import extract_all_features

    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"

    n = extract_all_features(
        db_path,
        settings,
        author_slug=author,
        skip_embeddings=skip_embeddings,
    )
    logger.info("extract: processed %d article(s)", n)

    if probability:
        # Phase 9 — probability features (stub until Phase 9 is implemented)
        logger.info(
            "extract: probability features requested (author=%s, binoculars=%s, device=%s)",
            author or "all",
            not no_binoculars,
            device or "auto",
        )
        logger.warning("Probability feature extraction not yet implemented (Phase 9)")
```

## 8. Analyze Subcommand (`src/forensics/cli/analyze.py`)

The analyze subcommand grows the most. Existing `--changepoint` and `--timeseries` are wired to real logic; Phase 6/7/10 flags are stubs:

```python
"""Analyze subcommand — change-point, time-series, drift, convergence."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Optional

import typer

from forensics.cli._helpers import config_fingerprint
from forensics.config import get_project_root, get_settings
from forensics.storage.repository import insert_analysis_run

logger = logging.getLogger(__name__)


def analyze(
    changepoint: Annotated[
        bool,
        typer.Option("--changepoint", help="Run change-point detection (PELT/BOCPD)"),
    ] = False,
    timeseries: Annotated[
        bool,
        typer.Option("--timeseries", help="Run time-series decomposition"),
    ] = False,
    drift: Annotated[
        bool,
        typer.Option("--drift", help="Run embedding drift analysis (Phase 6)"),
    ] = False,
    convergence: Annotated[
        bool,
        typer.Option("--convergence", help="Cross-validate pipelines and run hypothesis tests (Phase 7)"),
    ] = False,
    compare: Annotated[
        bool,
        typer.Option("--compare", help="Control author comparison only (Phase 7)"),
    ] = False,
    ai_baseline: Annotated[
        bool,
        typer.Option("--ai-baseline", help="Generate synthetic AI baseline articles (Phase 6)"),
    ] = False,
    skip_generation: Annotated[
        bool,
        typer.Option("--skip-generation", help="With --ai-baseline: use existing baseline, re-embed only"),
    ] = False,
    verify_corpus: Annotated[
        bool,
        typer.Option("--verify-corpus", help="Verify corpus hash before analysis (Phase 10)"),
    ] = False,
    author: Annotated[
        Optional[str],
        typer.Option("--author", metavar="SLUG", help="Limit to one author slug"),
    ] = None,
) -> None:
    """Run analysis pipeline (change-point, drift, convergence, comparison)."""
    from forensics.analysis.changepoint import run_changepoint_analysis
    from forensics.analysis.timeseries import run_timeseries_analysis

    settings = get_settings()
    root = get_project_root()
    db_path = root / "data" / "articles.db"
    analysis_dir = root / "data" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # Determine which stages to run — if nothing specified, run all implemented
    any_specified = changepoint or timeseries or drift or convergence or compare or ai_baseline
    do_changepoint = changepoint or not any_specified
    do_timeseries = timeseries or not any_specified

    rid = insert_analysis_run(
        db_path,
        config_hash=config_fingerprint(),
        description="forensics analyze",
    )
    meta = {
        "run_id": rid,
        "run_timestamp": datetime.now(UTC).isoformat(),
        "config_hash": config_fingerprint(),
        "changepoint": do_changepoint,
        "timeseries": do_timeseries,
        "drift": drift or not any_specified,
        "convergence": convergence or not any_specified,
        "compare": compare,
        "ai_baseline": ai_baseline,
        "author": author,
    }
    (analysis_dir / "run_metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8",
    )

    if verify_corpus:
        logger.info("analyze: corpus verification requested (stub — Phase 10)")

    if do_changepoint:
        run_changepoint_analysis(
            db_path, settings, project_root=root, author_slug=author,
        )
    if do_timeseries:
        run_timeseries_analysis(
            db_path, settings, project_root=root, author_slug=author,
        )
    if drift or (not any_specified):
        logger.info("analyze: drift analysis (author=%s) — stub until Phase 6", author or "all")
    if ai_baseline:
        logger.info(
            "analyze: AI baseline generation (skip_generation=%s) — stub until Phase 6",
            skip_generation,
        )
    if convergence or (not any_specified):
        logger.info("analyze: convergence scoring — stub until Phase 7")
    if compare:
        logger.info("analyze: control comparison — stub until Phase 7")

    logger.info(
        "analyze: completed (changepoint=%s, timeseries=%s, drift=%s, author=%s)",
        do_changepoint, do_timeseries, drift or not any_specified, author or "all",
    )
```

## 9. Report Subcommand (`src/forensics/cli/report.py`)

All Phase 8 flags as stubs:

```python
"""Report subcommand — Quarto rendering and deployment."""

from __future__ import annotations

import logging
from typing import Annotated, Optional

import typer

logger = logging.getLogger(__name__)


def report(
    notebook: Annotated[
        Optional[str],
        typer.Option("--notebook", metavar="NN", help="Render specific notebook (e.g. 05)"),
    ] = None,
    format: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: html or pdf"),
    ] = None,
    verify: Annotated[
        bool,
        typer.Option("--verify", help="Verify corpus hash before rendering"),
    ] = False,
) -> None:
    """Generate forensic analysis report via Quarto."""
    logger.info(
        "report: rendering (notebook=%s, format=%s, verify=%s)",
        notebook or "all",
        format or "all",
        verify,
    )
    logger.warning("Report generation not yet implemented (Phase 8)")
```

## 10. Tests

### tests/integration/test_cli.py (rewrite)

Replace argparse `build_parser` tests with Typer CliRunner tests:

```python
"""Test Typer CLI accepts all stage commands and flags."""

from typer.testing import CliRunner

from forensics.cli import app

runner = CliRunner()


def test_cli_help_exits_cleanly() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "forensics" in result.output.lower() or "pipeline" in result.output.lower()


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "forensics" in result.output


def test_scrape_help() -> None:
    result = runner.invoke(app, ["scrape", "--help"])
    assert result.exit_code == 0
    for flag in ("--discover", "--metadata", "--fetch", "--dedup", "--archive", "--dry-run"):
        assert flag in result.output


def test_extract_help() -> None:
    result = runner.invoke(app, ["extract", "--help"])
    assert result.exit_code == 0
    for flag in ("--author", "--skip-embeddings", "--probability", "--no-binoculars", "--device"):
        assert flag in result.output


def test_analyze_help() -> None:
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    for flag in ("--changepoint", "--timeseries", "--drift", "--convergence", "--compare",
                 "--ai-baseline", "--author", "--verify-corpus"):
        assert flag in result.output


def test_report_help() -> None:
    result = runner.invoke(app, ["report", "--help"])
    assert result.exit_code == 0
    for flag in ("--notebook", "--format", "--verify"):
        assert flag in result.output


def test_all_help() -> None:
    result = runner.invoke(app, ["all", "--help"])
    assert result.exit_code == 0
```

### tests/integration/test_cli_scrape_dispatch.py (rewrite)

The dispatch tests now test the `_dispatch` async function directly from `forensics.cli.scrape`:

```python
"""Exercise scrape flag dispatch (no live HTTP) via Typer."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from forensics.cli import scrape as scrape_mod
from forensics.config import get_settings


@pytest.mark.asyncio
async def test_scrape_dry_run_requires_fetch(
    tmp_path: Path, forensics_config_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    rc = await scrape_mod._dispatch(
        discover=False, metadata=False, fetch=False,
        dedup=False, archive=False, dry_run=True, force_refresh=False,
    )
    assert rc == 1


@pytest.mark.asyncio
async def test_scrape_archive_only(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scrape_mod, "archive_raw_year_dirs", lambda root, db: 2)
    with caplog.at_level(logging.INFO, logger="forensics.cli.scrape"):
        rc = await scrape_mod._dispatch(
            discover=False, metadata=False, fetch=False,
            dedup=False, archive=True, dry_run=False, force_refresh=False,
        )
    assert rc == 0
    assert "archive: compressed 2" in caplog.text


@pytest.mark.asyncio
async def test_scrape_dedup_only(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scrape_mod, "deduplicate_articles", lambda db: ["a", "b"])
    with caplog.at_level(logging.INFO, logger="forensics.cli.scrape"):
        rc = await scrape_mod._dispatch(
            discover=False, metadata=False, fetch=False,
            dedup=True, archive=False, dry_run=False, force_refresh=False,
        )
    assert rc == 0
    assert "dedup: marked 2" in caplog.text


@pytest.mark.asyncio
async def test_scrape_fetch_dry_run(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_fetch(db_path, settings, *, dry_run=False, **kw):
        assert dry_run is True
        return 5

    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scrape_mod, "fetch_articles", fake_fetch)
    with caplog.at_level(logging.INFO, logger="forensics.cli.scrape"):
        rc = await scrape_mod._dispatch(
            discover=False, metadata=False, fetch=True,
            dedup=False, archive=False, dry_run=True, force_refresh=False,
        )
    assert rc == 0
    assert "would fetch 5" in caplog.text


@pytest.mark.asyncio
async def test_scrape_unsupported_flags(
    tmp_path: Path, forensics_config_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    rc = await scrape_mod._dispatch(
        discover=True, metadata=False, fetch=True,
        dedup=False, archive=False, dry_run=False, force_refresh=False,
    )
    assert rc == 1


@pytest.mark.asyncio
async def test_scrape_discover_zero_authors(
    tmp_path: Path,
    forensics_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_discover(settings, *, force_refresh=False, **kw):
        return 0

    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(scrape_mod, "discover_authors", fake_discover)
    with caplog.at_level(logging.INFO, logger="forensics.cli.scrape"):
        rc = await scrape_mod._dispatch(
            discover=True, metadata=False, fetch=False,
            dedup=False, archive=False, dry_run=False, force_refresh=False,
        )
    assert rc == 0
    assert "discover: skipped" in caplog.text


@pytest.mark.asyncio
async def test_scrape_metadata_missing_manifest(
    tmp_path: Path, forensics_config_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    rc = await scrape_mod._dispatch(
        discover=False, metadata=True, fetch=False,
        dedup=False, archive=False, dry_run=False, force_refresh=False,
    )
    assert rc == 1


PLACEHOLDER_TOML = """
[[authors]]
name = "Placeholder Target"
slug = "placeholder-target"
outlet = "mediaite.com"
role = "target"
archive_url = "https://www.mediaite.com/author/placeholder-target/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[scraping]
"""


@pytest.mark.asyncio
async def test_scrape_rejects_placeholder_authors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import typer

    cfg = tmp_path / "bad.toml"
    cfg.write_text(PLACEHOLDER_TOML.strip() + "\n", encoding="utf-8")
    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(cfg))
    get_settings.cache_clear()
    monkeypatch.setattr(scrape_mod, "get_project_root", lambda: tmp_path)
    with pytest.raises(typer.BadParameter, match="placeholder"):
        await scrape_mod._dispatch(
            discover=True, metadata=False, fetch=False,
            dedup=False, archive=False, dry_run=False, force_refresh=False,
        )
    get_settings.cache_clear()
```

## 11. Documentation Updates

### AGENTS.md

Change in Project Profile section:

```
- **CLI:** argparse (`uv run forensics`)
```
→
```
- **CLI:** Typer (`uv run forensics`)
```

### HANDOFF.md

Append a completion block after migration is done, per the template.

## Implementation Notes

1. **The old `cli.py` dispatch logic is complex.** The boolean flag combination routing in `_async_scrape` is tested and correct — preserve it exactly in `_dispatch()`. Do not simplify or refactor the flag combinations.

2. **Async pattern.** Typer doesn't support async commands natively. The pattern is: Typer callback (sync) → `asyncio.run(async_impl(...))`. This is the same pattern the old argparse CLI used.

3. **Scrape uses `add_typer()`, others use `app.command()`.** Scrape is a sub-app because it needs `invoke_without_command=True` (bare `forensics scrape` = full pipeline). The other commands are simple functions registered directly on the root app.

4. **The placeholder guard now raises `typer.BadParameter`** instead of `ValueError`. Tests must catch `typer.BadParameter`, not `ValueError`.

5. **Import paths stay the same.** `from forensics.cli import main` still works because `cli/` is a package with `main()` in `__init__.py`. The `pyproject.toml` entry point `forensics.cli:main` does not change. `__main__.py` does not change.

6. **Phase 6/7/8/9/10 flags are stubs.** They log a warning and return. This is intentional — the flags are defined now so that future phase prompts don't need to touch the CLI structure when they're implemented. Only `--changepoint`, `--timeseries`, scrape flags, and extract (non-probability) are wired to real logic today.

7. **Delete old `cli.py` only after verifying all tests pass with the new package.** Run `uv run forensics --help` and `uv run python -m forensics --help` before deleting.

8. **After deleting, verify no references remain:**

```bash
grep -r "build_parser\|from forensics.cli import\|import argparse" src/ tests/ --include="*.py"
```

The only expected match is `from forensics.cli import` in `__main__.py` and test files — these should resolve to the new package.

## Validation

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v --cov=forensics --cov-report=term-missing

# Smoke test all commands:
uv run forensics --help
uv run forensics --version
uv run forensics scrape --help
uv run forensics extract --help
uv run forensics analyze --help
uv run forensics report --help
uv run forensics all --help
uv run python -m forensics --help

# Verify no argparse references remain:
grep -r "build_parser\|argparse" src/ tests/ --include="*.py"
# Expected: zero matches
```
