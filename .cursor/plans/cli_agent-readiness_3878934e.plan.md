---
name: CLI agent-readiness
overview: "Implement all 10 items from [prompts/cli-agent-readiness/current.md](prompts/cli-agent-readiness/current.md): shared JSON envelope + root flags, stdout/stderr sweep, semantic exit codes, `commands` discovery, examples on every command, structured `fail()`, TUI/non-interactive and lock/dedup behavior, scrape transient exit 4, tests and mandatory docs—without renaming top-level commands, changing the `forensics` script entry, or changing `text` as the default output format."
todos:
  - id: item-1
    content: Add _envelope.py + state + root flags; preflight/dedup envelope; test_cli_envelope + fix preflight JSON tests
    status: completed
  - id: item-2-3
    content: status()/stream sweep; _exit.py + docs/EXIT_CODES.md + Typer epilog; replace typer.Exit literals
    status: completed
  - id: item-4-5
    content: commands + walk + text tree; with_examples on all CLI commands; tests commands_dump + help_examples
    status: completed
  - id: item-6-8
    content: _errors.fail refactor; lock overwrite + non-interactive TUI + dedup CONFLICT; failure envelope tests
    status: completed
  - id: item-9
    content: Scraper transient classification + scrape CLI exit 4 + test_scrape_transient_classification
    status: pending
  - id: item-7-10-docs
    content: forensics-cli SKILL (clone) + CLAUDE.md; HANDOFF/RUNBOOK/GUARDRAILS; suite-wide test fixes; verification + gitnexus
    status: pending
isProject: false
---

# CLI agent-readiness — full implementation plan

Source of truth: [prompts/cli-agent-readiness/current.md](prompts/cli-agent-readiness/current.md) (matches `v0.1.0.md`). Governance: [AGENTS.md](AGENTS.md) (`uv run`, stage boundaries), [docs/GUARDRAILS.md](docs/GUARDRAILS.md) (new Sign per prompt). Before edits on shared symbols, run GitNexus `impact` upstream per [.cursor/rules/gitnexus-before-refactor.mdc](.cursor/rules/gitnexus-before-refactor.mdc); before PR, `gitnexus_detect_changes` + `npx gitnexus analyze --embeddings`.

## Plan-mode task routing (per workspace Plan Mode protocol)

| Task ID | Title | Exec mode | Model | Est. tokens |
|---------|--------|-----------|--------|---------------|
| TASK-1 | Items 1–3 foundation (envelope, state, exit codes, preflight/dedup) | sequential | claude-sonnet-4-6 | ~50K |
| TASK-2 | Item 2 sweep + Item 6 `fail()` + Item 8 TUI/lock/dedup | sequential[after: TASK-1] | claude-sonnet-4-6 | ~200K |
| TASK-3 | Items 4–5 commands + examples decorator | sequential[after: TASK-2] | claude-sonnet-4-6 | ~50K |
| TASK-4 | Item 9 scrape transient + scrape CLI | sequential[after: TASK-2] | claude-sonnet-4-6 | ~50K |
| TASK-5 | Item 10 test suite + docs + SKILL mirror | sequential[after: TASK-3,TASK-4] | claude-sonnet-4-6 | ~50K |

Model rationale: default code-gen / multi-file CLI refit; no Max/1M unless a single agent hits context pressure on `analyze.py` + `scrape.py` together.

## Architecture (after implementation)

```mermaid
flowchart TB
  subgraph root [Root callback]
    O[--output text|json]
    NI[--non-interactive]
    Y[--yes]
    NP[--no-progress]
    O --> State[ForensicsCliState]
    NI --> State
    Y --> State
    NP --> State
    State --> SP[show_progress forced false if json]
  end
  subgraph helpers [New modules]
    Env[_envelope.py success failure emit status]
    Exit[_exit.py ExitCode IntEnum]
    Err[_errors.py fail ctx]
  end
  subgraph cmds [Commands]
    C1[preflight validate export ...]
  end
  root --> cmds
  Env --> cmds
  Exit --> Err
  Err --> cmds
```

## Item 1 — JSON envelope + global `--output` / `--non-interactive` / `--yes`

**New:** [src/forensics/cli/_envelope.py](src/forensics/cli/_envelope.py) — `SCHEMA_VERSION`, `success`, `failure`, `emit` (exact contract in prompt). Add `status(line, *, ctx_or_state)` (or `output_format: Literal["text","json"]` parameter) so **json mode suppresses** human status lines per Item 2; import `typer` for `typer.echo(..., err=True)` when text.

**Update:** [src/forensics/cli/state.py](src/forensics/cli/state.py) — add `output_format`, `non_interactive`, `assume_yes`; document interaction with `show_progress`.

**Update:** [src/forensics/cli/__init__.py](src/forensics/cli/__init__.py) `_root` — add options from prompt (lines ~119–145 in spec); set `ctx.obj = ForensicsCliState(show_progress=not no_progress and output != "json", ...)`.

**Preflight:** Remove per-command `output` from `preflight()`; use `get_cli_state(ctx).output_format`. JSON path: `emit(success("preflight", _preflight_payload_dict))` where `data` holds current `_preflight_json_envelope` fields (`checks`, `has_failures`, …). Keep text branch behavior; route status lines to stderr (Item 2).

**Tests:** New [tests/unit/test_cli_envelope.py](tests/unit/test_cli_envelope.py) per prompt; update [tests/unit/test_cli_preflight_json.py](tests/unit/test_cli_preflight_json.py) to invoke `["--output", "json", "preflight"]` and assert envelope shape (`ok`, `type`, `schemaVersion`, `data.*`) and byte-stable canonical `json.dumps(..., sort_keys=True)` for `data` inner payload if you keep deterministic regression.

**Dedup:** [src/forensics/cli/dedup.py](src/forensics/cli/dedup.py) — accept `ctx`, branch on `get_cli_state(ctx).output_format`: text = human summary to **stdout** (data); json = `emit(success("dedup.recompute_fingerprints", summary))`. Thread `ctx` into callback.

**Option ordering:** Document in RUNBOOK: global format flags **before** subcommand: `uv run forensics --output json preflight`. Subcommand-local `--output` (e.g. [analyze section-profile](src/forensics/cli/analyze.py) path, [export](src/forensics/cli/__init__.py) DuckDB path) remains valid **after** the subcommand name (no collision with root literal).

## Item 2 — Stdout = data, stderr = logs

**Sweep** all `typer.echo` under [src/forensics/cli/](src/forensics/cli/) (grep-driven, not only listed lines). Rules from prompt:

- Status / warnings / errors → stderr in text mode; **suppressed** (or logger-only) in json mode except final `emit`/`fail`.
- Primary command output → stdout in text; json → envelope `data`.

**Priority files (from grep):** [__init__.py](src/forensics/cli/__init__.py), [survey.py](src/forensics/cli/survey.py), [analyze.py](src/forensics/cli/analyze.py) (lines ~726–803 and callbacks), [calibrate.py](src/forensics/cli/calibrate.py), [migrate.py](src/forensics/cli/migrate.py), [report.py](src/forensics/cli/report.py), [dedup.py](src/forensics/cli/dedup.py), [scrape.py](src/forensics/cli/scrape.py).

**Survey JSON:** Build `success("survey", {"qualified": ..., "disqualified": ..., "report": ...})` for `--output json` on real run and dry-run paths; serialize dataclasses/models via `model_dump` / dict helpers as needed.

**Section-profile / section-contrast:** Add `ctx`; json mode `emit(success(...))` with structured fields; progress lines → stderr or suppressed in json.

**Tests:** [tests/unit/test_cli_stream_separation.py](tests/unit/test_cli_stream_separation.py) — subprocess `["--output", "json", ...]`; assert single JSON object on stdout; stderr lines do not start with `{`; cover `preflight`, `validate`, `lock-preregistration --yes`, `dedup recompute-fingerprints --limit 0`, `commands`, and special-case `analyze --help` (Rich may use stdout; assert relaxed rule per prompt).

## Item 3 — Semantic exit codes

**New:** [src/forensics/cli/_exit.py](src/forensics/cli/_exit.py) — `ExitCode` enum exactly as spec.

**New:** [docs/EXIT_CODES.md](docs/EXIT_CODES.md) — table + retry guidance (4 vs 5 vs 2/3).

**Wire:** Replace literal `raise typer.Exit(code=N)` across CLI with `raise typer.Exit(code=int(ExitCode.X))` per mapping table in prompt. Key files: [__init__.py](src/forensics/cli/__init__.py), [dedup.py](src/forensics/cli/dedup.py), [analyze.py](src/forensics/cli/analyze.py), [extract.py](src/forensics/cli/extract.py), [migrate.py](src/forensics/cli/migrate.py), [report.py](src/forensics/cli/report.py), [scrape.py](src/forensics/cli/scrape.py). **Migrate:** map “no pending migrations” → `CONFLICT` (5) per table; parent dir missing → classify as `AUTH_OR_RESOURCE` (3) or `GENERAL` per your inspection of severity.

**Epilog:** Add `epilog=` on root `Typer(...)` in [__init__.py](src/forensics/cli/__init__.py) pointing to `docs/EXIT_CODES.md` (short path reference).

**TUI:** [src/forensics/tui/__init__.py](src/forensics/tui/__init__.py) — `main` / `main_dashboard` already return `int`; ensure dashboard path only passes through `ExitCode`-compatible values (0/1 today; align with Item 8 for usage errors).

**Tests:** [tests/unit/test_cli_exit_codes.py](tests/unit/test_cli_exit_codes.py) — subprocess fixtures per mapping row + Item 8 cases (below).

## Item 4 — `commands` self-discovery

**Add** `app.command(name="commands")` `list_commands(ctx)` in [__init__.py](src/forensics/cli/__init__.py) (or small `_commands.py` if `__init__.py` grows). Use `ctx.find_root().command`, walk `click.Group` recursively. **Fix examples source:** use `getattr(cmd.callback, "__forensics_examples__", [])` (Item 5 decorator attaches to callback, not Click’s `cmd.examples`). `to_info_dict`: verify against installed Click API (Typer ≥0.15); adjust if signature differs.

**Text mode:** implement `_render_command_tree` (indented tree).

**JSON:** `emit(success("commands", {"root": ...}))`.

**Tests:** [tests/unit/test_cli_commands_dump.py](tests/unit/test_cli_commands_dump.py) per prompt; assert `data.root.name == "forensics"` (or actual root command name), subcommands coverage, param keys, non-empty `examples` on `analyze` after Item 5.

## Item 5 — `@with_examples` on every command

**Implement** decorator in `_envelope.py` or new [src/forensics/cli/_decorators.py](src/forensics/cli/_decorators.py) per prompt (`__forensics_examples__`, append `Examples:` to `__doc__`).

**Apply** to every `app.command` / `add_typer` leaf / nested callback: [__init__.py](src/forensics/cli/__init__.py), [scrape.py](src/forensics/cli/scrape.py) (`ScrapeMode` matrix — one example per mode in [scrape.py](src/forensics/cli/scrape.py) lines 35–46), [survey.py](src/forensics/cli/survey.py), [calibrate.py](src/forensics/cli/calibrate.py), [analyze.py](src/forensics/cli/analyze.py) (root + `section-profile` + `section-contrast`), [dedup.py](src/forensics/cli/dedup.py), [extract.py](src/forensics/cli/extract.py), [report.py](src/forensics/cli/report.py), [migrate.py](src/forensics/cli/migrate.py) (`migrate` + `features migrate`), [features_app](src/forensics/cli/migrate.py), any other Typer apps under `cli/`.

**Tests:** [tests/unit/test_cli_help_examples.py](tests/unit/test_cli_help_examples.py) — walk Typer app + groups, `--help` contains `Examples:`; `commands` JSON has non-empty `examples` for every leaf (define “leaf” as commands with no subcommands or Typer `invoke_without_command` defaults as specified in test).

## Item 6 — `fail()` structured errors

**New:** [src/forensics/cli/_errors.py](src/forensics/cli/_errors.py) exactly as prompt; `fail` returns `typer.Exit` for `raise fail(...)`.

**Refactor** all `logger.error` + `typer.Exit` / bare messages to `raise fail(ctx, "<command-id>", "<code>", ..., exit_code=ExitCode..., suggestion=...)`. Pass `ctx` into `extract`, `report`, `migrate`, `setup`, `dashboard`, `lock_preregistration_cmd`, survey/analyze/dedup callbacks as needed. For [run_analyze](src/forensics/cli/analyze.py) (no `ctx`), use `get_cli_state(None)` inside `fail` for format (pipeline stays text-default) **or** add optional `ctx` parameter only to Typer entry path—prefer threading `ctx` from `analyze` callback into `run_analyze` for correct json failures when invoked from CLI.

**Validate / config parse:** `error.code == "config_invalid"`, exit `USAGE_ERROR` (2) per acceptance test in prompt.

**Tests:** [tests/unit/test_cli_failure_envelope.py](tests/unit/test_cli_failure_envelope.py) — tmp dir + malformed `config.toml`, assert JSON stdout + stderr text mode.

## Item 7 — SKILL.md + CLAUDE.md

**Create** [.claude/skills/forensics-cli/SKILL.md](.claude/skills/forensics-cli/SKILL.md) with full markdown from prompt (≥60 lines).

**Copy** byte-identical to [.cursor/skills/forensics-cli/SKILL.md](.cursor/skills/forensics-cli/SKILL.md).

**Update** [CLAUDE.md](CLAUDE.md) Key Documentation bullet per prompt.

## Item 8 — `--non-interactive` / `--yes` / dedup CONFLICT

- [__init__.py](src/forensics/cli/__init__.py) `setup_wizard` / `dashboard_cmd`: if `state.non_interactive`, `raise fail(..., "tty_required", exit_code=USAGE_ERROR)` before TUI import; merge with existing dashboard `--no-progress` check so codes match mapping (USAGE_ERROR 2).
- **Lock:** [lock_preregistration](src/forensics/preregistration.py) always writes; CLI must check `_default_lock_path()` (or settings-relative path) **before** call: if exists and not `state.assume_yes`, `fail(..., exit_code=CONFLICT, suggestion=...)`. If `--yes`, overwrite (current behavior).
- **Dedup:** When `summary["recomputed"] == 0` and `errors == 0` **and** schema columns present (avoid treating “missing columns” as idempotent success if you add a distinct check), exit `CONFLICT` (5) with envelope `success` carrying `recomputed: 0` **or** use `failure` with code `already_current`—prompt asks exit 5 with `data.recomputed=0`; prefer `emit(success(...))` + `raise typer.Exit(5)` or unify with `fail` if you encode success body + non-zero exit (cleaner: `fail` variant or dedicated helper). Document idempotence in help.

**Tests:** extend `test_cli_exit_codes.py` per prompt bullets.

## Item 9 — HTTP transient → exit 4

**Classify** errors in scrape pipeline: in [crawler.py](src/forensics/scraper/crawler.py) / [fetcher.py](src/forensics/scraper/fetcher.py) (where rows append to `scrape_errors.jsonl`), tag transient vs permanent: `httpx.TimeoutException`, `ReadTimeout`, `ConnectTimeout`; `HTTPStatusError` with 5xx → transient; else permanent.

**Plumb** summary bool or counts up through `dispatch_scrape` → [scrape.py](src/forensics/cli/scrape.py) CLI: if run finished with **no successful rows**, **≥1 failure**, and **all failures transient**, `raise typer.Exit(ExitCode.TRANSIENT)`; else preserve existing `rc` mapping.

**Document** in `_envelope.py` module docstring: `retry_after_ms` convention for transient failures.

**Tests:** [tests/unit/test_scrape_transient_classification.py](tests/unit/test_scrape_transient_classification.py) per prompt.

## Item 10 — Fix all existing tests + integration

Run full suite; fix assertions for stderr vs stdout, exit codes, `["--output","json",...]` ordering, dedup default text, help examples. Explicitly grep/update: [tests/integration/test_cli.py](tests/integration/test_cli.py), [tests/unit/test_cli_preflight_json.py](tests/unit/test_cli_preflight_json.py), any `test_dedup*`, CliRunner invocations.

Run `uv run pytest tests/ -m integration -v --no-cov` if markers exist.

## Mandatory documentation (prompt + CLAUDE session rules)

- [HANDOFF.md](HANDOFF.md) — completion block “CLI agent-readiness retrofit” with items 1–10, files, verification commands.
- [docs/RUNBOOK.md](docs/RUNBOOK.md) — “Headless / agent invocation” section → EXIT_CODES, `--output json --non-interactive`, SKILL path.
- [docs/GUARDRAILS.md](docs/GUARDRAILS.md) — Sign on stdout/stderr + JSON contract.
- [docs/EXIT_CODES.md](docs/EXIT_CODES.md) — from Item 3.

## Verification protocol (before merge)

Per prompt: `ruff check`, `ruff format --check`, `pytest` with coverage vs baseline, additive-only `forensics --help` diff, stream loop + `jq` on listed commands, `commands` subcommand count, GitNexus analyze + `detect_changes`.

## Risks / correctness (conflict resolution hierarchy)

- **Correctness:** `commands` walker must match Click/Typer internals; verify on CI Python 3.13.
- **Data integrity:** scrape exit semantics must not mask real failures; only apply TRANSIENT when **all** failures are transient **and** no success (per prompt).
- **Compatibility:** dedup default output flip to text is an intentional breaking change for JSON-only pipes; mitigated by `--output json` (document in HANDOFF / out-of-scope section of prompt).
