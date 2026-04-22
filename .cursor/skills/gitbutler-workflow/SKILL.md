---
name: gitbutler-workflow
description: "Abstract Data / Notion playbook: GitButler virtual branches for parallel agents, JSON status workflow (--json --status-after), per-file branch assignment, absorb. Use with the core gitbutler skill — does not replace it."
---

# GitButler workflow (Notion playbook add-on)

This skill **adds** team playbook guidance on top of the core GitButler CLI skill (`.claude/skills/gitbutler/SKILL.md`). Use both: the core skill for day‑to‑day `but` patterns (`-fv`, `--status-after`, conflict flow, stacking); this file for **parallel‑agent** framing and an alternate **JSON** inspection style when you want machine‑parseable status.

**Notion sources**

- Setup template (skill file + install notes): [GitButler Skill File (Claude Code + Cursor)](https://www.notion.so/34a7d7f56298816eae8be56c8fd8c4aa)
- Playbook: [GitButler: Virtual Branches for Parallel Agent Work](https://www.notion.so/34a7d7f56298816fa6d2cd77b6cebfc8)

---

## Why virtual branches

Multiple branches can coexist in **one working directory** — one dev server, one DB, one set of services. Branching is decided at **commit** time (which files go to which branch), not by cloning worktrees.

### When GitButler vs worktrees (summary)

| Scenario | Prefer GitButler | Prefer worktrees |
|----------|------------------|-------------------|
| DB / Redis / shared services | Yes — no infra duplication | Often no — duplicated envs |
| Tasks touch **different** files | Yes | Yes |
| Tasks modify the **same** file | No — race risk | Yes |
| Different build config per task | No | Yes |
| Heavy tests with conflicting DB side effects | Often no | Yes |
| Large monorepo (`node_modules`, builds) | Yes — less disk | More disk |

---

## JSON workflow (from Notion template)

Some agents prefer structured output:

1. **Before mutations:** `but status --json` — IDs change after operations; refresh when in doubt.
2. **On mutations:** append `--json --status-after` for structured output plus updated workspace state.
3. Use **CLI IDs** from JSON (branches `fe`, commits `1b`, files `g0`, hunks `j0`) in command arguments when that style fits the session.

Example: split one session across branches:

```bash
but status --json

but commit fe -m "Add /api/v1/usage endpoint" --changes g0,h0 --json --status-after
but commit do -m "Document usage API endpoint" --changes i0 --json --status-after
```

**Absorb** (auto‑target amend for a fix touching old commits):

```bash
but absorb <file-id> --json --status-after
```

Other mutations (same `--json --status-after` idea): `but squash`, `but reword`, `but undo`, `but push`, `but pr new`, etc.

---

## Multi‑agent, one directory

1. Tasks must mostly touch **different files** (hard boundary for same working tree).
2. Each agent uses its own virtual branch; commits use `--changes` so only intended files land on each branch.
3. Same‑file parallel edits → use worktrees or sequence work — not virtual branches alone.

---

## Relationship to the core skill

- Core skill: human‑readable `but status -fv`, detailed recipes (stacking, `but resolve`, dependency locks, `references/`).
- This add‑on: Notion **playbook** narrative, **when to use** virtual branches, and **JSON** variants for tooling.

If `but status --json` and `but status -fv` disagree in your CLI version, treat the core skill as the default for this repo unless you confirm JSON output is stable for your `but` version.
