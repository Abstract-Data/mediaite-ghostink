# CLI Agent-Readiness — Full Implementation

Version: 0.1.0
Status: active
Last Updated: 2026-04-26
Model: claude-opus-4-7

---

## Mission

Retrofit the `forensics` CLI so that every command is a *deterministic, machine-readable protocol* fit for AI-agent consumption — without breaking the existing human UX. Source audit: this project's CLI audit against "CLI Best Practices for AI Agents" (`/Users/johneakin/Downloads/CLI Best Practices for AI Agents.md`). Of the 10 principles in that document, this prompt closes the 7 highest-leverage gaps.

Nothing is deferred. Every item below ships in a single working branch with passing tests, updated docs (`HANDOFF.md`, `docs/RUNBOOK.md`, `docs/GUARDRAILS.md`, new `docs/EXIT_CODES.md`, new `.claude/skills/forensics-cli/SKILL.md`), and `gitnexus_detect_changes` confirmation. Items are independently mergeable but ordered by dependency: complete them in sequence.

The branch must NOT modify the `forensics` Python script entry point in `pyproject.toml`, NOT rename existing top-level commands, and NOT change `text` as the default `--output` format. All changes are additive.

## Pre-flight (run once)

1. `git checkout -b cli-agent-readiness`
2. `uv sync`
3. `uv run pytest tests/ -v --no-cov` — capture baseline pass count
4. `uv run ruff check .` — baseline
5. `uv run forensics --help > /tmp/help_baseline.txt` — capture text-format help, will diff at the end to verify human UX preserved
6. `npx gitnexus analyze --embeddings` if the index is stale
7. For every symbol you touch in the items below, run `gitnexus_impact({target: "<symbol>", direction: "upstream"})` first

## Conventions used in this prompt

- **JSON envelope** — every machine-readable response uses one of two flat shapes:

  ```json
  // success
  { "ok": true, "type": "<command-id>", "schemaVersion": 1, "data": { ... } }
  // failure
  { "ok": false, "type": "<command-id>", "schemaVersion": 1,
    "error": { "code": "<snake_case>", "message": "...", "suggestion": "...", ...extra } }
  ```

- **`<command-id>`** is the dotted command path: `analyze`, `analyze.section_profile`, `dedup.recompute_fingerprints`, `preflight`, etc.
- **Exit codes** follow the schema in item 3.
- **stdout = data, stderr = everything else.** Never mix. A successful `--output json` invocation produces *exactly one JSON object on stdout* followed by a newline, and nothing else on stdout.

---

## CRITICAL — order-dependent foundation

### Item 1 — JSON envelope helpers + global `--output` plumbing

**Target:** new `src/forensics/cli/_envelope.py`; modifications to `src/forensics/cli/state.py` and `src/forensics/cli/__init__.py`.

**Required behavior:** introduce a single envelope module that every other item depends on. Thread the chosen output format through `ForensicsCliState` so subcommands consume it uniformly.

**Implementation:**

1. Create `src/forensics/cli/_envelope.py`:

   ```python
   """Stable JSON envelope for ``forensics`` machine-readable output.

   Contract: a successful ``--output json`` invocation MUST emit exactly
   one JSON object on stdout and nothing else. Logs, progress, warnings,
   and errors go to stderr.
   """

   from __future__ import annotations

   import json
   import sys
   from typing import Any, Final

   SCHEMA_VERSION: Final[int] = 1

   def success(cmd: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
       return {
           "ok": True,
           "type": cmd,
           "schemaVersion": SCHEMA_VERSION,
           "data": data or {},
       }

   def failure(
       cmd: str,
       code: str,
       message: str,
       *,
       suggestion: str | None = None,
       **extra: Any,
   ) -> dict[str, Any]:
       err: dict[str, Any] = {"code": code, "message": message, **extra}
       if suggestion is not None:
           err["suggestion"] = suggestion
       return {
           "ok": False,
           "type": cmd,
           "schemaVersion": SCHEMA_VERSION,
           "error": err,
       }

   def emit(payload: dict[str, Any]) -> None:
       """Write the envelope to stdout as one sorted-key JSON line."""
       sys.stdout.write(json.dumps(payload, sort_keys=True))
       sys.stdout.write("\n")
       sys.stdout.flush()
   ```

2. Extend `ForensicsCliState` (`src/forensics/cli/state.py`) with:

   ```python
   output_format: Literal["text", "json"] = "text"
   non_interactive: bool = False
   assume_yes: bool = False
   ```

   Keep the existing `show_progress` field. When `output_format == "json"`, `show_progress` is forced to `False` regardless of the `--no-progress` flag — Rich progress bars on stderr would still pollute the terminal session for an agent.

3. Move the existing per-command `--output` option from `preflight` to the root callback in `src/forensics/cli/__init__.py:55`:

   ```python
   output: Annotated[
       Literal["text", "json"],
       typer.Option(
           "--output",
           help=(
               "text (default): human-readable lines on stdout. "
               "json: one JSON envelope object on stdout (logs to stderr)."
           ),
       ),
   ] = "text",
   non_interactive: Annotated[
       bool,
       typer.Option(
           "--non-interactive",
           help="Disable TUI fallbacks and refuse any prompt; auto-fail if a prompt would block.",
       ),
   ] = False,
   yes: Annotated[
       bool,
       typer.Option(
           "--yes",
           "-y",
           help="Bypass any confirmation prompt.",
       ),
   ] = False,
   ```

   Persist into state in `_root`:

   ```python
   ctx.obj = ForensicsCliState(
       show_progress=not no_progress and output != "json",
       output_format=output,
       non_interactive=non_interactive,
       assume_yes=yes,
   )
   ```

4. Delete the per-command `--output` option from `preflight` (`__init__.py:165-171`); switch its body to consult `get_cli_state(ctx).output_format`. Replace the existing `_preflight_json_envelope` body with an `emit(success("preflight", {...}))` call when JSON; keep the text branch unchanged.

5. Update `dedup recompute-fingerprints` (`src/forensics/cli/dedup.py:39`) to consult the root state instead of always emitting JSON. Default text output prints the human-readable summary; JSON emits the envelope. Preserves backward compatibility for any caller that already pipes from this command, because text becomes the new default — but keep an explicit `--output json` opt-in as the path the existing test exercises (`tests/unit/test_dedup_recompute.py` if it exists; check before changing the assertion).

**Acceptance test:** add `tests/unit/test_cli_envelope.py`:

- `success("foo", {"x": 1})` returns the documented dict shape with `schemaVersion == 1`
- `failure("foo", "bad", "boom", suggestion="try X", retry_after_ms=100)` returns `{"ok": False, "type": "foo", "schemaVersion": 1, "error": {"code": "bad", "message": "boom", "suggestion": "try X", "retry_after_ms": 100}}`
- `emit(...)` writes exactly one JSON line to stdout, sort_keys=True, ending in `\n`
- `forensics --output json preflight` exits with one JSON object on stdout, nothing else on stdout, all log lines on stderr (capture both streams via `pytest.capsys`)

---

### Item 2 — Stdout = data, stderr = logs (sweep)

**Target:** every `typer.echo(...)` call in `src/forensics/cli/` that emits a status line, warning, or error.

**Required behavior:** in `--output text` mode, status lines and errors go to stderr (`err=True`) so a human still sees them. In `--output json` mode, they are suppressed in favor of the JSON envelope. Data only ever goes to stdout.

**Implementation:**

1. Add a thin helper in `_envelope.py`:

   ```python
   def status(line: str, *, err: bool = True) -> None:
       """Human status line. Defaults to stderr to keep stdout clean."""
       typer.echo(line, err=err)
   ```

2. Audit and rewrite the following sites (verified via `grep -rn "typer.echo" src/forensics/cli/`). For each, the rule is: **if the line is metadata/status/warning/error, route to stderr; if it is the command's primary output (a path, a count, a record), route to stdout *only* in text mode and into the JSON envelope in json mode.**

   Sites to fix (non-exhaustive, complete the grep before declaring done):

   - `src/forensics/cli/__init__.py:191-198` — preflight text branch (status lines → stderr)
   - `src/forensics/cli/__init__.py:213-214` — `lock-preregistration` ("Pre-registration locked: …") → stderr; the lock path itself is the data and should go through the envelope
   - `src/forensics/cli/__init__.py:251` — `f"Config error: {exc}"` → use the structured failure helper from item 7; never to stdout
   - `src/forensics/cli/__init__.py:254-274` — validate output: status lines → stderr; the `n_authors` count + per-check results are the data
   - `src/forensics/cli/__init__.py:312` — "SQLite source not found" → stderr (and use failure envelope)
   - `src/forensics/cli/__init__.py:321-324` — export summary: counts are data; the trailing "Query with: duckdb …" tip is status → stderr
   - `src/forensics/cli/__init__.py:389-393, 405-409` — already use `err=True` ✓
   - `src/forensics/cli/survey.py:35-66` — qualified/disqualified summary: in text mode, the sectional text → stderr; the per-author table is data. In JSON mode, emit one envelope with `{"qualified": [...], "disqualified": [...], "report": {...}}`.
   - `src/forensics/cli/analyze.py:726-803` — section-profile / section-contrast progress lines → stderr; the structured result (sections, paths, counts, gate verdict) is data.
   - `src/forensics/cli/dedup.py:39` — already correct in JSON mode; in text mode, the JSON dump becomes a formatted summary on stdout.

3. Replace every remaining `typer.echo(...)` (no `err=True`) that prints anything other than the command's documented data with `status(...)` from the helper.

**Acceptance test:** add `tests/unit/test_cli_stream_separation.py` parameterized over every command. For each, run with `--output json` and capture both streams via `subprocess.run(...).stdout` and `.stderr`. Assert:

- stdout decodes as exactly one JSON object (or zero lines for commands that have no semantic output)
- stderr contains no JSON-looking lines (no `{` at column 0)
- exit code matches the expected semantic code from item 3

Use a parametrize list of `(argv, expected_exit, expected_type)` tuples covering: `preflight`, `validate`, `lock-preregistration --yes`, `dedup recompute-fingerprints --limit 0`, `analyze --help` (special-case: help output is allowed on stderr), `commands` (item 4).

---

### Item 3 — Semantic exit codes

**Target:** new `docs/EXIT_CODES.md`; new `src/forensics/cli/_exit.py`; every `raise typer.Exit(code=...)` site.

**Required behavior:** exit codes follow the agent-friendly schema below and are documented as a contract.

| Code | Name | Meaning |
|---|---|---|
| `0` | `OK` | Success |
| `1` | `GENERAL_ERROR` | Unclassified failure |
| `2` | `USAGE_ERROR` | Missing/invalid flag, mutually-exclusive flags, malformed argument value |
| `3` | `AUTH_OR_RESOURCE` | Missing prerequisite resource (DB file, model file, Ollama unreachable, write-protected dir) |
| `4` | `TRANSIENT` | Network timeout, rate-limit, retryable I/O — agent should retry |
| `5` | `CONFLICT` | "Already exists / already done" (manifest present, lock held, fingerprints already current) |

**Implementation:**

1. Create `src/forensics/cli/_exit.py`:

   ```python
   from enum import IntEnum

   class ExitCode(IntEnum):
       OK = 0
       GENERAL_ERROR = 1
       USAGE_ERROR = 2
       AUTH_OR_RESOURCE = 3
       TRANSIENT = 4
       CONFLICT = 5
   ```

2. Create `docs/EXIT_CODES.md` with the table above plus a paragraph explaining that agents may safely retry on `4`, must treat `5` as "already in desired state, move on", and must not retry `1`, `2`, `3` without human intervention.

3. Reference `docs/EXIT_CODES.md` from the root `--help` epilog (Typer supports `epilog=` on the `Typer(...)` constructor).

4. Re-classify every existing `Exit(code=...)` site. Concrete mapping:

   | Site | Current | New |
   |---|---|---|
   | `__init__.py:201` (preflight failures) | 1 | `GENERAL_ERROR` (1) — keep |
   | `__init__.py:252` (config parse error) | 1 | `USAGE_ERROR` (2) |
   | `__init__.py:270` (validate failures) | 1 | `GENERAL_ERROR` (1) |
   | `__init__.py:313` (SQLite missing) | 1 | `AUTH_OR_RESOURCE` (3) |
   | `__init__.py:394` (dashboard non-TTY) | 1 | `USAGE_ERROR` (2) |
   | `__init__.py:410` (dashboard mutually-exclusive flags) | 2 | `USAGE_ERROR` (2) — keep |
   | `dedup.py:36` (DB missing) | 1 | `AUTH_OR_RESOURCE` (3) |
   | `analyze.py:239` (ai-baseline ValueError) | 1 | `GENERAL_ERROR` (1) |
   | `analyze.py:263` (missing AI baseline vectors) | 1 | `AUTH_OR_RESOURCE` (3) |
   | `analyze.py:416` (corpus hash mismatch) | 1 | `CONFLICT` (5) — corpus changed since custody snapshot |
   | `analyze.py:432` (preregistration gate) | 1 | `CONFLICT` (5) — pre-reg state conflicts with intended run |
   | `analyze.py:778` (no authors resolved) | 1 | `USAGE_ERROR` (2) |
   | `extract.py:62, 75` (extract failures) | 1 | inspect — likely `GENERAL_ERROR` (1) for parse failures, `AUTH_OR_RESOURCE` (3) if a parquet write target is missing |
   | `migrate.py:54` (migrate failures) | 1 | `CONFLICT` (5) if "no migration needed", else `GENERAL_ERROR` (1) |
   | `report.py:82, 84` | 1 | `GENERAL_ERROR` (1) unless Quarto missing → `AUTH_OR_RESOURCE` (3) |
   | `scrape.py:564` | rc | inherit; ensure HTTP timeout paths in `crawler.py` / `fetcher.py` route to `TRANSIENT` (4) |

   Replace every `raise typer.Exit(code=N)` literal with `raise typer.Exit(code=ExitCode.X)` so a future grep finds them all.

5. The TUI dashboard inherits exit codes from `main_dashboard()`. Ensure that function returns a value compatible with `ExitCode` (audit `src/forensics/tui/__init__.py`).

**Acceptance test:** add `tests/unit/test_cli_exit_codes.py` with one case per row of the mapping table above. Use `subprocess.run` to invoke the command in a state that triggers each error path (use fixtures: a tmp project root with no `data/articles.db` to trigger `AUTH_OR_RESOURCE`, etc.). Assert the exact integer.

---

## HIGH — depends on items 1–3

### Item 4 — `commands --json` self-discovery

**Target:** new top-level command in `src/forensics/cli/__init__.py`.

**Required behavior:** dump the full command catalog as one JSON envelope so an agent can navigate the CLI without scraping `--help` for every subcommand.

**Implementation:**

```python
@app.command(name="commands")
def list_commands(ctx: typer.Context) -> None:
    """Dump the full command catalog (for agent discovery)."""
    import click

    state = get_cli_state(ctx)
    root = ctx.find_root().command  # the underlying Click group

    def walk(cmd: click.Command, path: list[str]) -> dict[str, object]:
        info = cmd.to_info_dict(ctx, latest_only=False)
        node: dict[str, object] = {
            "name": ".".join(path) if path else cmd.name,
            "help": (cmd.help or "").strip(),
            "params": [
                {
                    "name": p.name,
                    "type": getattr(p.type, "name", str(p.type)),
                    "required": bool(getattr(p, "required", False)),
                    "is_flag": bool(getattr(p, "is_flag", False)),
                    "default": p.default if not callable(p.default) else None,
                    "help": (getattr(p, "help", "") or "").strip(),
                    "choices": list(getattr(p.type, "choices", []) or []),
                }
                for p in cmd.params
                if p.name not in {"help"}
            ],
            "examples": getattr(cmd, "examples", []),
            "subcommands": [],
        }
        if isinstance(cmd, click.Group):
            for sub_name in sorted(cmd.commands):
                node["subcommands"].append(walk(cmd.commands[sub_name], [*path, sub_name]))
        return node

    payload = success("commands", {"root": walk(root, [])})
    if state.output_format == "json":
        emit(payload)
    else:
        # In text mode, render a flat indented tree.
        _render_command_tree(payload["data"]["root"], indent=0)
```

The `examples` attribute is set by a small decorator added in item 5; `getattr(... , [])` handles the fallback when no examples are attached.

**Acceptance test:** add `tests/unit/test_cli_commands_dump.py`:

- Run `forensics --output json commands` via subprocess
- Parse stdout as one JSON envelope
- Assert `payload["data"]["root"]["name"] == "forensics"`
- Assert every registered subcommand appears under `subcommands` (compare against `app.registered_groups` + `app.registered_commands`)
- Assert every `param` row has the documented keys
- Assert at least one command (e.g. `analyze`) carries a non-empty `examples` list (item 5 ensures this)

---

### Item 5 — Help-text examples on every command

**Target:** every `@app.command` and `@subapp.command` decorator with a callback that doesn't currently have an `Examples:` block.

**Required behavior:** every command's `--help` output ends with at least one realistic `Examples:` block. The same examples are exposed via `commands --json` (item 4).

**Implementation:**

1. Add a tiny decorator in `src/forensics/cli/_envelope.py` (or a new `_decorators.py`):

   ```python
   def with_examples(*examples: str):
       """Attach realistic CLI examples to a Typer command callback.

       The list is appended to the help epilog AND exposed via
       ``forensics commands --json`` for agent discovery.
       """
       def decorate(fn):
           fn.__forensics_examples__ = list(examples)
           original_help = (fn.__doc__ or "").rstrip()
           example_block = "\n\nExamples:\n" + "\n".join(f"  $ {e}" for e in examples)
           fn.__doc__ = original_help + example_block
           return fn
       return decorate
   ```

   Wire `commands --json` to read `fn.__forensics_examples__` and propagate to the `examples` field.

2. Add `@with_examples(...)` to every command. Required examples (minimum one per command):

   - `preflight`:
     - `forensics --output json preflight`
     - `forensics preflight --strict`
   - `validate`:
     - `forensics validate --check-endpoints`
   - `lock-preregistration`:
     - `forensics lock-preregistration --yes`
   - `export`:
     - `forensics export --output data/forensics_2026-04-26.duckdb`
   - `all`:
     - `forensics all`
     - `forensics --output json all`
   - `dashboard`:
     - `forensics dashboard --survey --skip-scrape`
   - `setup`:
     - `forensics setup`
   - `commands`:
     - `forensics --output json commands | jq '.data.root.subcommands[].name'`
   - `analyze`:
     - `forensics analyze --author isaac-schorr`
     - `forensics analyze --compare-pair isaac-schorr,john-doe`
     - `forensics analyze --parallel-authors --max-workers 4`
   - `analyze section-profile`:
     - `forensics analyze section-profile`
   - `analyze section-contrast`:
     - `forensics analyze section-contrast --author colby-hall`
   - `scrape` (root + flag combinations): one example per `ScrapeMode` documented in `scrape.py:35-46`
   - `dedup recompute-fingerprints`:
     - `forensics --output json dedup recompute-fingerprints --limit 100`
   - `survey`, `extract`, `report`, `migrate`, `features`, `calibrate`: one realistic example each — derive from existing flag set.

**Acceptance test:** add `tests/unit/test_cli_help_examples.py` that walks `app.registered_commands` and the registered Typer groups, invokes each with `--help`, and asserts the output contains the literal string `"Examples:"`. Also assert that `commands --json` returns a non-empty `examples` list for every leaf command.

---

### Item 6 — Structured error envelope helper + global error handler

**Target:** new `src/forensics/cli/_errors.py`; rewrite of every `logger.error(...) → raise typer.Exit(code=X)` pattern.

**Required behavior:** every command failure produces (a) a stderr human-readable line in text mode OR (b) a JSON failure envelope on stdout in json mode, then exits with the semantic code from item 3.

**Implementation:**

1. Create `src/forensics/cli/_errors.py`:

   ```python
   from __future__ import annotations

   import logging
   import typer

   from forensics.cli._envelope import emit, failure
   from forensics.cli._exit import ExitCode
   from forensics.cli.state import get_cli_state

   logger = logging.getLogger(__name__)

   def fail(
       ctx: typer.Context,
       cmd: str,
       code: str,
       message: str,
       *,
       exit_code: ExitCode = ExitCode.GENERAL_ERROR,
       suggestion: str | None = None,
       **extra: object,
   ) -> typer.Exit:
       """Emit a structured failure and return a typer.Exit ready to raise."""
       state = get_cli_state(ctx)
       if state.output_format == "json":
           emit(failure(cmd, code, message, suggestion=suggestion, **extra))
       else:
           prefix = f"ERROR ({code}): {message}"
           typer.echo(prefix, err=True)
           if suggestion:
               typer.echo(f"  → {suggestion}", err=True)
           if extra:
               for k, v in extra.items():
                   typer.echo(f"  {k}: {v}", err=True)
       logger.error("%s: %s (%s)", cmd, message, code)
       return typer.Exit(code=int(exit_code))
   ```

   Note: `fail` *returns* (not raises) the `typer.Exit` so the call site reads `raise fail(ctx, ...)` — Python's exception chaining stays clean.

2. Rewrite every existing `logger.error(...) → raise typer.Exit(code=N)` site to use `fail`. Examples:

   ```python
   # __init__.py:251 (was: typer.echo(...) + raise typer.Exit(code=1))
   raise fail(ctx, "validate", "config_invalid",
              f"Could not parse config.toml: {exc}",
              exit_code=ExitCode.USAGE_ERROR,
              suggestion="run: forensics preflight to see which check failed")

   # analyze.py:432 (preregistration gate)
   raise fail(ctx, "analyze", "preregistration_not_locked",
              preregistration.message,
              exit_code=ExitCode.CONFLICT,
              suggestion="run: forensics lock-preregistration --yes "
                         "(or pass --exploratory to bypass)")

   # dedup.py:36
   raise fail(ctx, "dedup.recompute_fingerprints", "database_missing",
              f"SQLite database not found: {db_path}",
              exit_code=ExitCode.AUTH_OR_RESOURCE,
              suggestion="run: forensics scrape --discover --metadata "
                         "to populate data/articles.db")
   ```

3. Pass `ctx: typer.Context` to every command callback that doesn't already accept it (most do — verify). For commands implemented as plain functions (`extract`, `report`, `migrate`), add the `ctx` parameter.

4. Replace bare `raise typer.Exit(code=1)` lines that have NO accompanying user-facing message — these are silent failures and must be classified.

**Acceptance test:** add `tests/unit/test_cli_failure_envelope.py`:

- Run `forensics --output json validate` against a tmp project with a malformed `config.toml`
- Assert stdout is one JSON envelope with `ok=False`, `error.code == "config_invalid"`, `error.suggestion` present
- Assert exit code 2
- Same in text mode: assert `ERROR (config_invalid):` on stderr, suggestion line follows, exit code 2

---

### Item 7 — Project SKILL.md for the forensics CLI

**Target:** new `.claude/skills/forensics-cli/SKILL.md` and mirror `.cursor/skills/forensics-cli/SKILL.md`; CLAUDE.md update.

**Required behavior:** a workflow/priority/structure layer that `--help` cannot provide, so an agent landing in this repo can pick the right command sequence without trial-and-error.

**Implementation:**

1. Create `.claude/skills/forensics-cli/SKILL.md` with these sections (full content, not placeholders):

   ```markdown
   # Forensics CLI Skill

   ## Capabilities
   The `forensics` CLI runs a 4-stage pipeline: scrape → extract → analyze → report.
   - Scrape: WordPress discovery, metadata, HTML fetch, dedup, archive
   - Extract: lexical/content/probability features → parquet
   - Analyze: change-point, time-series, drift, convergence, comparison
   - Report: rendered analysis artifacts (Quarto + JSON)

   Discoverability:
   - `forensics --help` — top-level groups
   - `forensics --output json commands` — full machine-readable catalog
   - `docs/EXIT_CODES.md` — exit-code contract

   ## Workflows

   ### Fresh end-to-end run (no prior state)
   1. `forensics preflight --strict` — exit 0 required
   2. `forensics lock-preregistration --yes`
   3. `forensics all`
   4. Output: `data/reports/`

   ### Single-author refresh after corpus update
   1. `forensics scrape --metadata --author SLUG`
   2. `forensics extract --author SLUG`
   3. `forensics analyze --author SLUG`

   ### Compare two authors without changing config
   `forensics analyze --compare-pair TARGET,CONTROL`

   ### Migrating simhash fingerprints after D-01 (NFKC v2)
   `forensics --output json dedup recompute-fingerprints`
   Reads JSON: `.data.recomputed`, `.data.skipped`, `.data.errors`.

   ### Headless / agent invocation
   Always pass `--output json --non-interactive`. Inspect exit code first:
   - 0: success — parse `.data`
   - 4: transient — retry with exponential backoff (start 5s)
   - 5: conflict — read `.error.suggestion`, decide to skip or override
   - 2/3: do not retry; surface to user

   ## Guardrails
   - `forensics dashboard` and `forensics setup` are TUI-only. With `--non-interactive` they exit code 2 immediately. Never invoke from an agent.
   - `forensics analyze` without `--exploratory` requires a locked preregistration. Lock first via `lock-preregistration --yes`.
   - Shared-byline accounts (`mediaite`, `mediaite-staff`) are blocked unless `--include-shared-bylines`.
   - All writes go under `data/`. Never write outside.

   ## Trigger conditions
   | Symptom | Workflow |
   |---|---|
   | Fresh checkout, empty `data/` | Fresh end-to-end run |
   | One author's articles changed | Single-author refresh |
   | Need ad-hoc target↔control comparison | Compare two authors |
   | Old simhashes (pre-D-01) in DB | Migrate simhash fingerprints |
   | CI / scheduled job | Headless agent invocation |
   ```

2. Mirror to `.cursor/skills/forensics-cli/SKILL.md` (byte-identical copy — match existing precedent for `gitbutler` and `gitnexus` skills).

3. Add to `CLAUDE.md` Key Documentation list:

   ```markdown
   - `.claude/skills/forensics-cli/SKILL.md` — agent-facing workflows, exit-code reference, headless invocation guide (mirrored under `.cursor/skills/forensics-cli/`)
   ```

**Acceptance:** no test file. Manual verification: `wc -l .claude/skills/forensics-cli/SKILL.md` ≥ 60 lines; `diff .claude/skills/forensics-cli/SKILL.md .cursor/skills/forensics-cli/SKILL.md` returns empty.

---

## MEDIUM — depends on items 1, 3, 6

### Item 8 — `--yes` / `--non-interactive` enforcement on TUI and destructive commands

**Target:** `src/forensics/cli/__init__.py` (`setup`, `dashboard`, `lock-preregistration`).

**Required behavior:**

- `setup` and `dashboard` exit code 2 (`USAGE_ERROR`) immediately when `state.non_interactive` is True, with a structured failure envelope explaining "this command requires a TTY". Existing dashboard TTY check (`__init__.py:388-394`) becomes the new path with the proper exit code and envelope.
- `lock-preregistration` refuses to overwrite an existing lock unless `--yes` is passed; new exit code `CONFLICT` (5) with `suggestion="re-run with --yes to overwrite the existing lock"` when a lock exists and `--yes` was not provided.
- `dedup recompute-fingerprints` is already idempotent; document it as such in `--help` text and exit `CONFLICT` (5) with `data.recomputed=0` when no rows needed update — agents can branch on the code without parsing the count.

**Implementation:** straightforward conditionals in each callback. Reuse the `fail` helper from item 6.

**Acceptance test:** add cases to `tests/unit/test_cli_exit_codes.py`:

- `forensics --non-interactive setup` → exit 2
- `forensics --non-interactive dashboard` → exit 2
- `forensics --non-interactive --output json setup` → JSON envelope with `error.code == "tty_required"` on stdout, exit 2
- `forensics lock-preregistration` (no `--yes`, lock exists) → exit 5
- `forensics lock-preregistration --yes` (lock exists) → overwrites, exit 0

---

### Item 9 — Wire HTTP transient errors to exit code 4

**Target:** `src/forensics/scraper/crawler.py`, `src/forensics/scraper/fetcher.py`, and the `scrape` CLI callback that translates the `rc` into `Exit(code=rc)` (`scrape.py:564`).

**Required behavior:** when the scrape stage exits because of HTTP timeouts or 5xx responses (i.e. retryable), the CLI exits `TRANSIENT` (4). Permanent failures (4xx, parse errors, missing config) keep their existing classification.

**Implementation:**

1. In the per-row error path that already routes to `scrape_errors` JSONL, classify by exception type. Existing `httpx.HTTPError` subclasses: `TimeoutException`, `ReadTimeout`, `ConnectTimeout` → transient; `HTTPStatusError` with `5xx` → transient; everything else → permanent.

2. Plumb a `had_transient_only` boolean (or `error_summary` dict) up to the CLI callback. If the run completed with at least one row failure AND every failure was transient AND no rows succeeded, exit `TRANSIENT` (4). Otherwise keep current behavior.

3. Document in `_envelope.py` failure helper that `retry_after_ms` is the conventional extra field for `TRANSIENT` failures and should be populated when the upstream emits a `Retry-After` header.

**Acceptance test:** add `tests/unit/test_scrape_transient_classification.py` that monkey-patches the HTTP fetcher to raise `httpx.ReadTimeout` for every request, runs the scrape callback, and asserts exit code 4 (not 1).

---

### Item 10 — Update existing tests for the contract

**Target:** existing tests that asserted the old behavior.

**Required behavior:** any test that asserted `typer.echo` text on stdout for status lines must be updated to expect stderr. Any test that asserted exit code 1 for one of the re-classified errors must update.

**Implementation:** run the full test suite after items 1–9 and fix every failure. Common updates:

- `tests/unit/test_cli_preflight_json.py` — already expects JSON on stdout; verify the global `--output` plumbing didn't break the byte-stable assertion.
- `tests/unit/test_dedup_recompute*.py` — if any — update to expect text-default with `--output json` opt-in.
- Any test asserting `result.stdout` contains a status string → update to `result.stderr`.

---

## Documentation updates (mandatory per `CLAUDE.md`)

- **`HANDOFF.md`** — append a completion block titled "CLI agent-readiness retrofit" listing all 10 items with file lists and verification commands.
- **`docs/RUNBOOK.md`** — add a "Headless / agent invocation" section pointing at `docs/EXIT_CODES.md`, the `--output json --non-interactive` flag pair, and `.claude/skills/forensics-cli/SKILL.md`.
- **`docs/GUARDRAILS.md`** — add a Sign: "Mixing data and logs on stdout breaks agent parsing. Every CLI command must route metadata, status lines, warnings, and errors to stderr; only the command's documented data goes on stdout. The `--output json` envelope is the contract."
- **`docs/EXIT_CODES.md`** — created in item 3.
- **`.claude/skills/forensics-cli/SKILL.md`** — created in item 7.
- **`CLAUDE.md`** — single-line addition under Key Documentation referencing the new SKILL.md.

## Verification protocol (run before opening PR)

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run pytest tests/ -v --cov=src --cov-report=term-missing` — coverage must not regress versus baseline captured in pre-flight.
4. `uv run pytest tests/ -m integration -v --no-cov` if the integration job from PR #94 remediation has landed.
5. **Human-UX preservation check:** `uv run forensics --help > /tmp/help_after.txt && diff /tmp/help_baseline.txt /tmp/help_after.txt`. The diff must be additive only (new flags, new examples) — no removed help text, no flag renames.
6. **Stream-separation check:** for every leaf command, run with `--output json` and assert exactly one JSON line on stdout via:

   ```bash
   for cmd in preflight validate "lock-preregistration --yes" \
              "dedup recompute-fingerprints --limit 0" commands; do
     uv run forensics --output json $cmd > /tmp/out.json 2> /tmp/err.txt
     test "$(wc -l < /tmp/out.json)" = "1" || { echo "FAIL stdout lines: $cmd"; exit 1; }
     jq -e '.schemaVersion == 1' /tmp/out.json > /dev/null || { echo "FAIL schema: $cmd"; exit 1; }
   done
   ```

7. **Self-discovery check:** `uv run forensics --output json commands | jq '.data.root.subcommands | length'` returns ≥ 6 (scrape, survey, calibrate, features, analyze, dedup) plus root commands.
8. `npx gitnexus analyze --embeddings`
9. `gitnexus_detect_changes({scope: "all"})` — verify the changed-symbol set matches the items above.

## Out of scope (explicitly)

- **Renaming top-level commands** to fold `extract`, `report`, `migrate`, `lock-preregistration`, `export`, `validate`, `preflight`, `all` into noun groups. Discussed in the audit; deferred to a separate prompt because it would break every existing operator script and CI invocation.
- **NDJSON streaming output.** No command currently produces a multi-record stream that would benefit; revisit if `commands` or `survey` grow large enough.
- **Server-side filtering / `--fields`-style projection.** Optional; revisit when an agent first hits a context-window pressure incident.
- **Authentication flows (RFC 8628 / device grant).** This CLI talks to a public WordPress endpoint and a local Ollama; no auth surface to harden.
- **Backwards-compat shims for callers that piped `dedup recompute-fingerprints` stdout.** This PR keeps `--output json` available; a caller relying on the previous always-JSON behavior must add the explicit flag.

If a remediation item appears to require any of the above, stop and surface the dependency in `HANDOFF.md` rather than expanding the branch.

## Definition of done

- All 10 items above implemented and tested.
- `uv run pytest tests/ -v --cov=src` passes with coverage ≥ baseline.
- Stream-separation and self-discovery checks (verification protocol §6, §7) pass.
- `docs/EXIT_CODES.md`, `.claude/skills/forensics-cli/SKILL.md`, `.cursor/skills/forensics-cli/SKILL.md` exist and are referenced from `CLAUDE.md`.
- `HANDOFF.md`, `docs/RUNBOOK.md`, `docs/GUARDRAILS.md` updated.
- `gitnexus_detect_changes` confirms the affected scope matches the items above.
- PR description enumerates each item with file:line and the commit that closed it.
- Human-UX diff (`/tmp/help_after.txt` vs baseline) is additive-only.
