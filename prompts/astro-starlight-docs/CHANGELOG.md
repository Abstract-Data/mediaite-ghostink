# Changelog — Astro Starlight Documentation Site

## [0.1.0] — 2026-05-06

**Model:** claude-opus-4-7
**Status:** active
**Bump reason:** initial release.

### Added

- Initial prompt for standing up Astro Starlight as the unified
  documentation site for `mediaite-ghostink`. Stage:
  developer-and-operator docs **plus** an embedded copy of the
  Quarto-rendered bound forensic report under `/report/`. Replaces the
  prior Cloudflare Pages deploy of the Quarto book.
- Scope-boundary section at the top of the prompt clarifying that
  Quarto sources (`_quarto.yml`, `index.qmd`, `notebooks/`) remain
  read-only — CI invokes `quarto render` but does not edit Quarto
  inputs. Analysis-stage code, feature extractors, the data model, and
  `config.toml` are also read-only.
- Nine required steps: create `website/` at the repo root via the
  official Starlight template; author `astro.config.mjs` with
  `site: 'https://abstract-data.github.io'`, `base: '/mediaite-ghostink'`,
  manual sidebar, Mermaid integration, and a `Forensic report` sidebar
  entry pointing at `/report/`; build a `website/scripts/sync-docs.mjs`
  Node script that copies an explicit allow-list of canonical markdown
  from `docs/` into `website/src/content/docs/synced/` with
  derived YAML frontmatter and link rewriting (in-tree links to
  Starlight slugs, out-of-tree links to absolute GitHub URLs); build
  `scripts/generate_cli_docs.py` (Python, Typer-app introspection)
  emitting `docs/cli/*.md`; hand-author `index.mdx` and
  `getting-started.mdx`; **anchor the work to the Starlight components
  reference (`https://starlight.astro.build/components/using-components/`)
  and configuration reference (`https://starlight.astro.build/reference/configuration/`)
  with a required-components checklist (`Steps`, `Aside`, `FileTree`,
  `Tabs` on the getting-started page; `CardGrid`, `LinkCard`, `Aside`
  on the landing page) and an explicit list of in-scope vs. out-of-scope
  configuration knobs**; add Makefile targets `docs-cli`, `docs-dev`,
  `docs-build`; replace the existing
  `.github/workflows/deploy.yml` with a new
  `.github/workflows/deploy-docs.yml` that renders Quarto into
  `website/public/report` then builds and deploys Astro to
  GitHub Pages on push to `main` (with PR build-only validation);
  update `docs/RUNBOOK.md`, `docs/GUARDRAILS.md`, `README.md`, and
  `HANDOFF.md`.
- Acceptance criteria (13 items) including a Quarto-source invariants
  check, a CI-workflow invariants check covering the six workflows
  that must remain untouched, a deletion check on `deploy.yml`,
  reproducibility checks on the CLI doc generator and sync script,
  and a component-usage check that greps the hand-authored MDX pages
  for the required Starlight components and confirms imports come
  from `@astrojs/starlight/components`.
- Verification commands enforce that Quarto sources and analysis
  stages are byte-identical, the sync script and CLI generator are
  idempotent, the local Astro build succeeds, the embedded Quarto
  report renders into `website/dist/report/`, and every sidebar entry
  resolves to an HTML file in `website/dist/`.
- Out-of-scope list explicitly prohibits Quarto edits, importing the
  full `docs/` tree (only an allow-list is in scope), importing
  `prompts/` or `evals/`, migrating `README.md` into Starlight,
  modifying any other CI workflow, performing GitHub repo settings
  changes (those are HANDOFF maintainer actions), and adding
  versioning, i18n, analytics, or alternative search backends —
  Pagefind built-in is the chosen baseline.
- Rollback path restores the deleted `deploy.yml` and re-enables the
  Cloudflare Pages deploy as the safety net.
- Locked design decisions captured up front:
  `website/` subdirectory in this repo (not a separate repo);
  GitHub Pages deploy (not Cloudflare); `docs/` remains canonical
  with build-time copy and frontmatter injection (not a move);
  Quarto embedded under `/report/` (not linked out); existing
  Cloudflare Pages deploy retired; CLI auto-generation in scope for
  v0.1.0; Pagefind built-in search; v0.1.0 doc scope is core
  operator docs (`ARCHITECTURE`, `RUNBOOK`, `TESTING`,
  `GUARDRAILS`, `DEPLOYMENTS`, `EXIT_CODES`) plus all ADRs.
