---
name: Config Full Run
overview: Fix `config.toml` so the study has one target author, Colby Hall, and all other configured named writers as controls while preserving shared-byline exclusion. Then validate the config/preflight path and regenerate the preregistration lock now that you approved that data-file write.
todos:
  - id: normalize-roster
    content: Update `config.toml` author roles, remove placeholder author, and fix Zachary Leeman archive URL.
    status: completed
  - id: run-validation
    content: Run `uv run forensics validate` and `uv run forensics preflight`; fix config-caused failures.
    status: completed
  - id: lock-preregistration
    content: Run `uv run forensics lock-preregistration` and confirm the generated lock is real.
    status: completed
  - id: append-handoff
    content: Append the required completion block to `HANDOFF.md`.
    status: completed
isProject: false
---

# Config Full Run Plan

## Scope And Rules
- Applies AGENTS.md constraints: keep the change incremental, preserve scrape/extract/analyze/report stage boundaries, use `uv run` for Python commands, and append a `HANDOFF.md` completion block for this multi-step task.
- Writes allowed by your clarification: `config.toml`, `HANDOFF.md`, and `data/preregistration/preregistration_lock.json` from `uv run forensics lock-preregistration`.
- Do not edit `.cursor/plans/*.plan.md`.
- No symbol/function/class edits are planned, so GitNexus impact analysis is not needed for code symbols.

## Current Finding
`config.toml` currently marks every named author except Zachary Leeman as `target`, includes `placeholder-target`, and gives Zachary Leeman the placeholder archive URL. `[survey].exclude_shared_bylines = true` is already correct and should stay unchanged.

## Implementation Steps
Task ID: TASK-1
Title: Normalize author roster
Exec mode: sequential
Model: gpt-5-4
Model rationale: Small config edit with correctness-sensitive forensic semantics; current model is sufficient.
Est. tokens: <10K
Risk: LOW
- In `config.toml`, keep `Colby Hall` / `colby-hall` as the only `role = "target"`.
- Change Ahmad Austin, Alex Griffing, Charlie Nash, David Gilmour, Isaac Schorr, Jennifer Bowers Bahney, Joe DePaolo, Michael Luciano, Sarah Rumpf, and Zachary Leeman to `role = "control"`.
- Remove the `Placeholder Target` `[[authors]]` block entirely.
- Set Zachary Leeman `archive_url` to `https://www.mediaite.com/author/zachary-leeman/`.
- Keep all baseline windows at `2020-01-01` through `2023-12-31`.
- Keep `[survey].exclude_shared_bylines = true` and do not add `mediaite` or `mediaite-staff` rows.

Task ID: TASK-2
Title: Validate config and environment
Exec mode: sequential[after: TASK-1]
Model: gpt-5-4
Model rationale: Validation requires interpreting command output and optional dependency warnings.
Est. tokens: <10K
Risk: LOW
- Run `uv run forensics validate`.
- Run `uv run forensics preflight`.
- If either fails on config-author issues, fix `config.toml` and rerun.
- If optional checks warn, report them separately: likely Ollama, spaCy `en_core_web_md`, Quarto, sentence-transformers, or chain-of-custody corpus/archive expectations.

Task ID: TASK-3
Title: Lock preregistration
Exec mode: sequential[after: TASK-2]
Model: gpt-5-4
Model rationale: Command should run only after thresholds/config parse cleanly.
Est. tokens: <10K
Risk: MEDIUM
- Run `uv run forensics lock-preregistration` after validation so `data/preregistration/preregistration_lock.json` becomes a real lock for the current thresholds.
- Confirm the lock file is no longer an unfilled template and note that future analysis threshold changes will require relocking or exploratory mode.

Task ID: TASK-4
Title: Record handoff
Exec mode: sequential[after: TASK-3]
Model: gpt-5-4
Model rationale: Documentation hygiene update using the repo’s existing handoff format.
Est. tokens: <10K
Risk: LOW
- Append a concise completion block to `HANDOFF.md` listing touched files, validation outputs, decisions, unresolved optional environment warnings, and next steps.

## Validation Commands
- `uv run forensics validate`
- `uv run forensics preflight`
- `uv run forensics lock-preregistration`

## Acceptance Check
- `config.toml` has no `placeholder-target` or `placeholder-control` in `[[authors]]`.
- Exactly one configured author has `role = "target"`: Colby Hall.
- All other configured named writers are `role = "control"`.
- No `mediaite` or `mediaite-staff` author rows exist.
- `exclude_shared_bylines = true` remains in `[survey]`.
- Validation/preflight pass, or only documented optional warnings remain.