# Changelog — Mintlify Component & Developer Documentation Setup

## [0.1.0] — 2026-04-24

**Model:** claude-opus-4-7
**Status:** active
**Bump reason:** initial release.

### Added

- Initial prompt for standing up Mintlify as the developer / component
  documentation platform for the `mediaite-ghostink` software. Stage:
  developer-docs only — explicitly **NOT** a replacement for the Quarto
  bound forensic report, which remains the client-facing deliverable
  built independently from `quarto.yml`, `notebooks/`, and `data/reports/`.
- Scope-boundary section at the top of the prompt restating the Quarto
  separation, with explicit prohibition on touching `quarto.yml`,
  `index.qmd`, `notebooks/`, `data/reports/`, or the existing
  `.github/workflows/deploy.yml`.
- Nine required steps: create `mintlify/` at repo root, author
  `docs.json` with navigation tabs (Get Started / Components /
  Operations / Decision Records / Prompts) mirroring the gitnexus
  component areas, build a `scripts/build_mintlify_content.py` that
  derives MDX pages from `docs/`, `docs/adr/`, and `prompts/*/current.md`
  (canonical sources never duplicated), hand-author the introduction
  and quickstart with a `<Note>` linking to the Quarto report, follow a
  consistent component-page template (`<CardGroup>` source/test links,
  `<ParamField>` inputs/outputs, `<CodeGroup>` config examples,
  `<AccordionGroup>` for methods), local dev via `mint dev`, deploy
  via Mintlify hosted with content directory set to `mintlify/`, add
  `.github/workflows/mintlify-lint.yml` for `mint broken-links` on PRs.
- Acceptance criteria (10 items) including a Quarto-invariants check
  (`git diff --stat` of `quarto.yml`, `notebooks/`, `data/reports/`,
  `.github/workflows/deploy.yml` must be empty) and bidirectional
  cross-linking (Mintlify links to Quarto report; both sites surface
  each other).
- Verification commands enforce reproducibility (re-running the build
  script produces no diffs), local site responds, broken-link check
  passes, and Mintlify navigation entries all have backing MDX files.
- Out-of-scope list explicitly prohibits Quarto edits, consolidating
  the Quarto report into Mintlify, hosting Quarto HTML inside Mintlify,
  and touching analysis-stage code or `config.toml` thresholds.
- Rollback path leaves the Quarto deploy as the safety net.
