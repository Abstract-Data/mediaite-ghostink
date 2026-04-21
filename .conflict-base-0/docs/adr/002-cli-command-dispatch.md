# ADR-002: CLI Command Dispatch Pattern

- **Status:** Accepted
- **Date:** 2026-04-20
- **Deciders:** John Eakin
- **Trigger:** All three review reports flagged `_async_scrape` in `cli.py` as a critical code smell — 117 lines, ~18 cyclomatic complexity, 7 mutually exclusive flag-combination branches with duplicated workflow logic (RF-CPLX-001, P2-CQ-2, Dev Assessment §2).

## Context

The `scrape` subcommand in `src/forensics/cli.py` accepts five boolean flags (`--discover`, `--metadata`, `--fetch`, `--dedup`, `--archive`) plus `--dry-run`. The current implementation handles flag combinations with sequential `if` blocks that compute boolean expressions from the 5 flags:

```python
d = bool(args.discover)
m = bool(args.metadata)
# ...
only_archive = arch and not d and not m and not f and not ded
if only_archive:
    # 4 lines of workflow
    return 0

only_dedup = ded and not d and not m and not f and not arch
if only_dedup:
    # 6 lines of workflow
    return 0

# ... 5 more blocks
```

This pattern has three problems:

1. **Combinatorial explosion.** Adding Phase 4–7 flags (extract, analyze, report) would require handling exponentially more combinations.
2. **Duplicated workflow steps.** The `discover + metadata` sequence appears in 3 branches. The `fetch + dedup + export` sequence appears in 2.
3. **Single-letter variable names.** `d`, `m`, `f`, `ded`, `arch` reduce readability in the boolean expressions.

## Decision

Replace the flag-combination dispatch with a **command registry pattern** where each pipeline operation is a callable with declared dependencies.

### Design

```python
from dataclasses import dataclass
from collections.abc import Callable, Awaitable
from typing import Any

@dataclass
class PipelineStep:
    name: str
    execute: Callable[..., Awaitable[str]]  # returns summary message
    depends_on: list[str] = field(default_factory=list)

# Registry of all pipeline steps
STEPS: dict[str, PipelineStep] = {
    "discover": PipelineStep(
        name="discover",
        execute=run_discover,
    ),
    "metadata": PipelineStep(
        name="metadata",
        execute=run_metadata,
        depends_on=["discover"],
    ),
    "fetch": PipelineStep(
        name="fetch",
        execute=run_fetch,
        depends_on=["metadata"],
    ),
    "dedup": PipelineStep(
        name="dedup",
        execute=run_dedup,
    ),
    "archive": PipelineStep(
        name="archive",
        execute=run_archive,
    ),
}
```

The dispatch logic becomes:

```python
async def _async_scrape(args: argparse.Namespace) -> int:
    requested = [name for name, flag in _parse_flags(args).items() if flag]
    if not requested:
        requested = list(STEPS.keys())  # --all behavior

    plan = resolve_execution_plan(requested, STEPS)

    for step_name in plan:
        step = STEPS[step_name]
        logger.info("Running step: %s", step_name)
        summary = await step.execute(args)
        logger.info("%s: %s", step_name, summary)

    return 0
```

### Step Function Contract

Each step function has the same signature:

```python
async def run_discover(args: argparse.Namespace) -> str:
    """Discover authors from WordPress API. Returns summary message."""
    # ... 10-20 lines of focused logic
    return f"wrote {n} author(s) to {manifest_path}"
```

### Benefits for Phase 4–7

Adding new pipeline stages (extract, analyze, report) is a single registration:

```python
STEPS["extract"] = PipelineStep(
    name="extract",
    execute=run_extract,
    depends_on=["fetch"],
)
```

No modification to the dispatch logic required.

## Alternatives Considered

### Strategy pattern with classes

A class-per-command approach (e.g., `DiscoverCommand`, `MetadataCommand`) was considered but rejected as over-engineered for this use case. The commands don't need polymorphic behavior — they're sequential steps with simple dependencies. A registry of functions is simpler and more Pythonic.

### Click or Typer

Replacing argparse with Click or Typer would provide built-in command grouping. Rejected because argparse is already wired through the codebase, and the dispatch pattern solves the problem without adding a dependency.

## Consequences

- **Eliminates** the 117-line God Function.
- **Eliminates** duplicated workflow sequences across branches.
- **Enables** Phase 4–7 stages to slot in with zero dispatch logic changes.
- **Requires** extracting 5–7 focused step functions from `_async_scrape`.
- **Requires** replacing all `print()` calls with `logger` calls (aligns with P2-CQ-1).
- Each step function should be independently testable.

## Migration Path

1. Extract step functions from the existing `_async_scrape` branches (keep old code as fallback behind a flag).
2. Build the STEPS registry and `resolve_execution_plan`.
3. Replace `_async_scrape` dispatch with the registry loop.
4. Remove old code once tests pass.

Estimated effort: 3–4 hours.

## Related

- GUARDRAILS.md: Sign "God function exceeding 50 lines in CLI/orchestration"
- Code Review Report: P2-CQ-1, P2-CQ-2
- Refactoring Report: RF-CPLX-001 (Critical)
