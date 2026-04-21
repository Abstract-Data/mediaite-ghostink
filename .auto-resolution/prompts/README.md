# Prompt Library

**Project:** mediaite-ghostink
**Owner:** John Eakin / Abstract Data LLC
**Last updated:** 2026-04-20

---

## Purpose

This directory is the single source of truth for every prompt artifact used by agents working on this project. Prompts are version-controlled, immutable once released, and subject to the same review discipline as production code.

## Folder Conventions

```
prompts/
    README.md                      ← this file (library contract)
    core-agent/                    ← agent persona prompt
        current.md                 ← always a copy of the latest immutable version
        v0.1.0.md                  ← immutable snapshot
        v0.1.1.md                  ← immutable snapshot (next release)
        CHANGELOG.md               ← human-readable history
        versions.json              ← machine-readable version index
    phase1-scaffold-and-models/
        current.md
        v0.1.0.md
        CHANGELOG.md
        versions.json
    phase2-scraper-discovery/
        ...same pattern...
```

Every prompt family lives in its own directory. The top-level `phase*.md` files are convenience aliases; the canonical versioned artifacts live inside the subdirectories.

## Required Prompt Header Fields

Every versioned prompt file must begin with these fields:

```markdown
# {Prompt Title}

Version: X.Y.Z
Status: active | deprecated | draft
Last Updated: YYYY-MM-DD
Model: {target model, e.g. gpt-5-3-codex, claude-opus-4-6}
```

## Versioning Rules (Semver for Prompts)

Prompts follow semantic versioning. The version number communicates the nature of the change:

**MAJOR (X.0.0)** — Breaking behavioral change
- Mission or objective fundamentally redefined
- Guardrails removed or relaxed
- Target model changed to a different family
- Output format or contract changed in incompatible ways

**MINOR (0.X.0)** — New capability, backward-compatible
- New sections or instructions added
- Additional guardrails or validation steps
- New CLI flags or commands referenced
- Expanded scope within the same mission

**PATCH (0.0.X)** — Clarification or fix, no behavioral change
- Typo or wording fix
- Reordering for clarity
- Adding examples without changing instructions
- Fixing incorrect references (file paths, command names)

## Immutability Contract

1. **Once a `vX.Y.Z.md` file is committed, it is never modified.** Corrections require a new version.
2. **`current.md` must always be an exact copy of the latest `vX.Y.Z.md`.** No edits to `current.md` that aren't also in a versioned snapshot.
3. **`CHANGELOG.md` entries are append-only.** Each entry includes: version, date, model, summary of changes, and eval impact (if measured).
4. **`versions.json` is the machine-readable index.** Hooks and CI can read it to validate consistency.

## Release Workflow

### Creating a new version

1. Draft the new prompt content.
2. Determine the version bump (major/minor/patch) per the rules above.
3. Create the immutable snapshot: `prompts/{family}/vX.Y.Z.md`
4. Copy the snapshot to `prompts/{family}/current.md` (exact copy, no modifications).
5. Update `prompts/{family}/CHANGELOG.md` with the new entry.
6. Update `prompts/{family}/versions.json` to register the new version.
7. Commit all four files in a single commit.

### Rollback

To roll back to a previous version:
1. Copy `vX.Y.Z.md` (the target version) to `current.md`.
2. Add a CHANGELOG entry: "Rolled back to vX.Y.Z — reason: {why}".
3. Do NOT create a new version number for the rollback; just update `current.md` and the changelog.

### Deprecation

To deprecate a prompt:
1. Change the `Status:` header in the latest version to `deprecated`.
2. Create a new version with `Status: deprecated` if a successor exists, or leave the latest as-is if the prompt family is being retired.
3. Add a CHANGELOG entry explaining the deprecation.

## versions.json Schema

```json
{
  "family": "core-agent",
  "current_version": "0.1.0",
  "versions": [
    {
      "version": "0.1.0",
      "date": "2026-04-20",
      "status": "active",
      "model": "gpt-5-3-codex",
      "file": "v0.1.0.md",
      "changelog_entry": "Initial prompt for forensics pipeline agent."
    }
  ]
}
```

## Validation Checklist

Before committing any prompt change, verify:

- [ ] New `vX.Y.Z.md` file exists with correct header fields
- [ ] `current.md` is an exact copy of the new version
- [ ] `CHANGELOG.md` has a new entry with version, date, model, and summary
- [ ] `versions.json` has the new version registered with correct metadata
- [ ] Version bump follows semver rules (major/minor/patch)
- [ ] No existing `vX.Y.Z.md` files were modified

## Phase Prompts

Phase prompts (`phase1` through `phase8`) follow the same versioning contract as agent prompts. They define implementation specifications for each stage of the forensics pipeline build-out. Phase prompts are consumed by agents (human or AI) executing the implementation plan.

## Ownership

Prompt changes require the same review as code changes. The project maintainer listed in `AGENTS.md` is the final approver for prompt modifications.
