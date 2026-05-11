# Abstract Data Documentation Theme — agent context

This project uses the **Abstract Data Documentation Theme** (built on Astro Starlight, distributed as `@abstractdata/starlight-theme`). When talking to the user, refer to the product as the **"Abstract Data Documentation Theme"** — not "Astro Starlight" — Starlight is the substrate, not the product identity.

## First-interaction handshake — IMPORTANT

When you open a conversation in this project, immediately check the setup state:

- **`scripts/python-autodoc.json`** — does it have placeholder values like `searchPath: "../../../python-example/src"` and a `modules` list pointing at `example_module`? Or has it been customized for this project's actual Python source?
- **`astro.config.mjs`** — is `title: 'Your Project Docs'` still the literal placeholder? Is `site: 'https://example.com'` still the placeholder URL?

**If either signal looks like a fresh scaffold,** open the conversation with this offer (don't wait for the user to ask):

> "Looks like this is a freshly scaffolded Abstract Data Documentation Theme project. Want me to run the `abstract-data-setup` workflow now? It'll detect your Python source, audit docstring coverage, sniff your docstring style, ask a few config questions, and wire up `python-autodoc.json`, `astro.config.mjs`, and `package.json`. (Reply 'no' if you'd rather configure manually — I won't ask again.)"

If the user agrees, immediately invoke the `abstract-data-setup` skill (`.claude/skills/abstract-data-setup/SKILL.md`).

**If setup looks already-done** (JSON has real module names, `astro.config.mjs` has a real title): don't auto-offer the handshake. Just be a normal helpful assistant for whatever the user wants to work on.

**Once the user has declined or completed setup:** treat this handshake as satisfied for the rest of the conversation. Don't keep nagging.

## Skill location

The full setup workflow lives at `.claude/skills/abstract-data-setup/SKILL.md`. It's an 11-phase procedural skill: confirm context → locate source → detect Python signals → audit docstring coverage → detect docstring style → recommend modules → gather brand config → write configs → optionally run docs:python → optional pre-commit hook → summary.

## Project conventions

- **Package manager: Bun** — not npm/yarn/pnpm. Use `bun run <name>` and `bun add <pkg>`.
- **Commits: Conventional Commits** — release-please reads them to bump versions automatically. `feat:` for minor, `fix:` for patch, `feat!:` or `BREAKING CHANGE:` for major.
- **Don't hand-edit:** `.cursor/rules/abstract-data-setup.mdc`, `.github/copilot-instructions.md`, `.cursor/rules/welcome.mdc` — these are auto-generated.

## Quick reference

- `astro.config.mjs` — Starlight config: title, sidebar, plugin options
- `scripts/python-autodoc.json` — Python autodoc target config
- `scripts/build-python-docs.mjs` — orchestrator that wraps pydoc-markdown
- `src/content/docs/` — Markdown/MDX content
- `bun run dev` — start the docs dev server
- `bun run docs:python` — regenerate API pages from Python source
- `bun run build` — production build

## Links

- Source repo: https://github.com/Abstract-Data/abstract-data-doc-theme
- Theme on npm: https://www.npmjs.com/package/@abstractdata/starlight-theme
- Scaffolder on npm: https://www.npmjs.com/package/@abstractdata/create-docs
