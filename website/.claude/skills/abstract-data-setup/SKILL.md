---
name: abstract-data-setup
description: Set up the Abstract Data Documentation Theme (built on Astro Starlight) for a project. Detect source code across stacks (Python, TypeScript, Next.js, TanStack, OpenAPI, Prisma, Drizzle), audit docstring coverage for Python, sniff docstring style (Google/NumPy/Sphinx), detect or pick a logo asset, ask configuration questions (modules/entry points, motion, credit, version), wire up config files (scripts/python-autodoc.json, scripts/ts-autodoc.json, astro.config.mjs sidebar + plugin options, package.json scripts), and optionally install a docstring-coverage pre-commit hook. Use when the user says "set up docs", "configure docs", "wire up Python autodoc", "wire up TypeScript autodoc", "scan my project for docs", "set up Abstract Data docs", "add API reference", "audit docstrings", or similar phrases inside a docs project that uses @abstractdata/starlight-theme (the npm package name; product is the Abstract Data Documentation Theme).
---

# Abstract Data Documentation Theme — Setup

Bootstrap the Abstract Data Documentation Theme — the branded docs system Abstract Data uses across client projects, built on Astro Starlight and shipped as the npm package `@abstractdata/starlight-theme`. Round 2 covers Python and TypeScript autodoc with full automation, plus detection-and-recipe handling for Next.js, TanStack Router, OpenAPI, Prisma, and Drizzle.

## When to invoke

Run this skill when the user says "set up docs", "configure docs", "wire up Python autodoc", "wire up TypeScript autodoc", "scan my project for docs", "audit docstrings", or similar inside a project that has `@abstractdata/starlight-theme` in its `package.json`. If the cwd doesn't have that dep, stop and point them at `bun create @abstractdata/docs`.

## Workflow

Use interactive prompts for every choice — never assume.

### Phase 1 — Confirm context

Read `package.json`. Verify `@abstractdata/starlight-theme` is in deps; verify `astro.config.mjs` and `src/content/docs/` exist. Stop with a clear message if any check fails. Don't ask the user to confirm — just announce findings and move on.

### Phase 2 — Locate the source project(s)

Ask via interactive prompt: where does the source project live?
- "This directory" — docs ARE the source (rare)
- "Parent directory (..)" — docs sit inside the source repo
- "Sibling directory" — separate repos at the same level
- "Custom path" — prompt for it

Validate the path exists. Reprompt on invalid.

### Phase 3 — Detect all stack signals

In the source path, scan for these signals in parallel. Report what you find before asking any per-stack questions.

**Python:**
- `pyproject.toml`, `setup.py`, `requirements.txt`, `Pipfile`
- `src/<pkg>/__init__.py` or `<pkg>/__init__.py`

**TypeScript library:**
- `tsconfig.json` AND `package.json` with `main`/`exports`/`types` fields
- `src/index.ts` or similar entry point

**Next.js:**
- `next.config.{js,mjs,ts}`
- `app/` directory (App Router) or `pages/` directory (Pages Router)
- `next` in dependencies

**TanStack Router / Start:**
- `@tanstack/react-router`, `@tanstack/react-start`, or `@tanstack/start` in dependencies
- `src/routes/` directory
- `src/routeTree.gen.ts` (generated route tree)

**OpenAPI:**
- `openapi.yaml`, `openapi.json`, `swagger.yaml`, `swagger.json`
- Files matching `*.openapi.{yaml,json}`

**Prisma:**
- `prisma/schema.prisma`

**Drizzle:**
- `drizzle.config.{ts,js}`
- Files in a `schema/` directory exporting `pgTable` / `mysqlTable` / `sqliteTable`

**Logo asset (in the docs project, not the source):**
- `src/assets/*.{png,svg,jpg,jpeg,webp}` — anything that looks like a logo (`logo.*`, `*-logo.*`, `brand.*`)

Display the detection summary in a table:

```
Stack          Detected   Action
Python         yes        will offer Python autodoc
TypeScript     yes        will offer TypeScript autodoc
Next.js        no         —
TanStack       yes        recipe-only (no auto-config)
OpenAPI        no         —
Prisma         yes        recipe-only (no auto-config)
Drizzle        no         —
Logo           1 file     will confirm choice
```

If no source signals at all → exit politely.

### Phase 4 — Python: audit + style (only if Python detected)

#### 4a — Audit docstring coverage

Preferred tool: `interrogate` (`pipx install pydoc-markdown` first if not installed). Fall back to a Python AST one-liner. Categorize per-module:
- **≥ 80%** green
- **50-79%** yellow
- **< 50%** red

Show the table; don't editorialize.

#### 4b — Detect docstring style

Sample 10–20 docstrings, count distinctive markers (Google `Args:`/`Returns:`, NumPy `Parameters\n----`, Sphinx `:param x:`). Pick the leader if it has ≥60% of markers; otherwise call it "mixed."

### Phase 5 — TypeScript: entry-point detection (only if TS library detected)

Read `package.json` `main`/`exports`/`types` fields. Walk `src/` for `index.ts` files. Build a candidate list of entry points (one per public module surface).

Common shapes:
- Single entry: `src/index.ts` → one entry point
- Multi-entry: `package.json` `exports` lists multiple → one entry per exported subpath
- Monorepo: each package has its own entry

#### 5a — Audit TSDoc coverage

Mirror Phase 4a for TypeScript. Run TypeDoc in **validation-only** mode against the chosen entry points:

```bash
bunx typedoc \
  --plugin typedoc-plugin-markdown \
  --validation.notDocumented \
  --treatValidationWarningsAsErrors false \
  --emit none \
  <entryPoints>
```

Parse the resulting warnings — TypeDoc emits one line per undocumented symbol with `[warning]` prefix. Group by source file and report per-file coverage as a percentage of public exports that have at least one TSDoc block. Use the same color thresholds as the Python audit:

- **≥ 80%** green
- **50–79%** yellow
- **< 50%** red

If TypeDoc isn't installed yet, fall back to a quick AST sniff: count files in `src/` with `/**` blocks vs total exported declarations. Coarser, but no install required.

Show the table; don't editorialize. The result feeds Phase 12 (pre-commit hook offer).

### Phase 6 — Logo detection

Scan `src/assets/**/*.{png,svg,jpg,jpeg,webp}` recursively. Build candidate categories:

- **Topbar mark candidates**: filename matches `(logo|brand|mark|icon)\.(svg|png|webp)$` (case-insensitive). SVG preferred.
- **Light/dark pair**: filenames contain `light` or `dark` and otherwise match logo conventions (e.g. `logo-light.svg` + `logo-dark.svg`). Starlight supports both via `logo.light` + `logo.dark`.
- **Hero candidates**: any image larger than ~80KB or with `hero` / `splash` in the name — usually a bigger variant for the splash page.
- **Other images**: no logo conventions; treat as miscellaneous.

For each candidate, gather:
- File size in bytes
- Format (extension)
- Whether the filename indicates light/dark intent

Display a 4-7 line summary table:

```
File                              Size      Format     Suggested role
src/assets/logo.svg               12 KB     SVG        topbar mark (recommended)
src/assets/logo-light.svg         12 KB     SVG        topbar (light mode)
src/assets/logo-dark.svg          12 KB     SVG        topbar (dark mode)
src/assets/hero-mark.png          145 KB    PNG        splash hero image
```

Branch on what you found:

- **One mark + light/dark pair** → propose using the pair (Starlight handles auto-switching by `data-theme`)
- **One mark, no pair** → propose using it for both modes
- **Multiple marks, no clear winner** → multiselect: which for topbar? Which for hero? `multiSelect: true` interactive prompt.
- **Zero candidates** → ask: "I don't see a logo in `src/assets/`. Drop one in (SVG preferred, ~256x256 minimum), tell me where it is, or skip for now and configure manually later."

Format guidance to surface alongside the prompt:
- SVG renders crispest at any size; preferred for both topbar and hero.
- PNG works fine; 256×256 minimum for the topbar (Astro will downscale via the asset pipeline).
- JPG is fine for hero photos but bad for marks (compression artifacts on edges).
- Files > 200KB will bloat first-paint; suggest optimizing or using a smaller source.

### Phase 7 — Recommend documentation surfaces

For each detected stack, ask whether to wire it up. Stack questions are per-stack, not lumped together.

#### Python (if detected)

Interactive prompt with up to 4 options:
- "Top-level package only" (Recommended)
- "All green-coverage modules" (≥80%)
- "Specific submodules I'll pick" → multiselect
- "Everything" (warn about red-coverage modules)

#### TypeScript (if detected)

Interactive prompt:
- "Single root entry point (src/index.ts)" (Recommended for libs with one public API)
- "All paths in package.json `exports`" (Recommended for multi-entry libs)
- "I'll pick specific entry points" → free-form

#### Other detected stacks (Next.js, TanStack, OpenAPI, Prisma, Drizzle)

Don't auto-configure. Tell the user the recipe and let them follow up:

- **Next.js**: "I detected Next.js. There isn't a standard one-shot route documenter, but you can write a small build script that walks `app/` or `pages/` and emits a `routes.md`. Want me to draft one?"
- **TanStack Router**: "I detected TanStack Router. Generate a route map by importing `routeTree.gen.ts` and walking it in a build script. Want a starter?"
- **OpenAPI**: "I detected an OpenAPI spec. Recommend `@astrojs/starlight-openapi` for the cleanest integration. Want me to install it and wire it up?"
- **Prisma**: "I detected a Prisma schema. Try `prisma-markdown` for schema docs. Want me to add it to dev deps and wire a script?"
- **Drizzle**: "I detected a Drizzle config. There isn't a mature schema-to-markdown tool yet — most teams write their own walker over the schema exports. Want me to draft a starter?"

If the user says yes to any of these, fall back to free-form work — these aren't covered by the main config files.

### Phase 7.5 — Optional Starlight plugins

Three plugins are cheap, high-value DX wins for most docs sites. Don't auto-install — surface them as an interactive multi-select prompt with sensible per-project defaults. Skip the prompt entirely if the user has already declined them in a previous run (look for a `.abstractdata-setup.json` marker or for the plugins already being absent + the import already pruned).

For each, you decide the default based on signals you've already gathered:

- **`starlight-llms-txt`** — emits an `llms.txt` summary at `/llms.txt` (per [llmstxt.org](https://llmstxt.org)) so AI crawlers can ingest the site as plain Markdown rather than parsing rendered HTML. **Default: ON.** No real downside.
- **`@expressive-code/plugin-package-managers`** *(code-block plugin, not a Starlight plugin)* — auto-renders npm/pnpm/yarn/bun tabs from a single `npm install foo` code block. **Default: ON if** the README, quickstart, or any docs page contains `bun add`, `npm install`, `pnpm add`, or `yarn add`. **Default: OFF otherwise.**
- **`starlight-image-zoom`** — click-to-zoom on images. **Default: ON if** the docs project has more than ~5 images under `src/assets/` or `src/content/docs/**/*.{png,jpg,svg,webp}` (a heuristic for "this site uses screenshots"). **Default: OFF otherwise.**

Show the user the three options with their suggested defaults pre-checked, and let them un-check / toggle. For each accepted plugin:

1. Add to `dependencies` in `package.json`.
2. Add the import to `astro.config.mjs`.
3. Wire the plugin entry into the `plugins` array (or `expressiveCode.plugins` for the package-managers plugin).
4. Tell the user the bun command to run: `bun add <plugin-name>`.

Show the resulting diff before writing. Don't run `bun add` yourself — the user does it.

### Phase 8 — Gather brand + contributor-loop configuration

Read existing `astro.config.mjs`. If `motion`, `credit`, `version`, `lastUpdated`, and `editLink` are already set and the user hasn't asked to change them, skip this phase.

Otherwise, batch into one prompt:

1. Motion: full | calm (Recommended)
2. Credit: auto | hide
3. Version chip: show with version string | omit
4. **Last-updated timestamps** (Recommended on): renders a "Last updated" footer on each page using `git log`. Requires a git checkout at build time. Set `lastUpdated: true` if yes, omit otherwise.
5. **"Edit on GitHub" link** (Recommended on for OSS): renders an Edit link in the footer pointing at the source. Needs a repo URL — derive it from `package.json` `repository.url` or the source-project remote (`git remote get-url origin`). If found, write `editLink: { baseUrl: '<repo>/edit/<default-branch>/' }`; if not, leave the commented-out scaffold in place and tell the user how to fill it in.

Both items 4 and 5 are cheap, high-impact contributor-loop wins per the Astro/Starlight best-practices guide — default to enabling them unless the user opts out.

### Phase 9 — Configure logo

Two surfaces need updating:

**a) Topbar logo — `astro.config.mjs` `starlight.logo`**

First, look at what Phase 6 detected. Three branches:

1. **Phase 6 found a light/dark pair** (e.g. `logo-light.svg` + `logo-dark.svg`) → use the `{ light, dark }` form. Starlight auto-switches based on `data-theme`. Don't ask which to use as the default — both render at the right time.

2. **Phase 6 found a single mark** → use the single-`src` form. Optionally suggest the user create a dark variant later if the mark is colored in a way that won't survive a dark background.

3. **Phase 6 found nothing** → leave the existing commented `// logo: { ... }` block in `astro.config.mjs` and tell the user where to drop a logo file.

Then ask one final question (skip if you already know): does the logo include the project name as text/wordmark?

- **Yes** (logo + wordmark in one image) → `replacesTitle: true` — Starlight hides the text title and shows just the logo.
- **No** (just a mark/icon, no text) → `replacesTitle: false` — Starlight shows the mark beside the text title.

Then write the config:

```js
// Single mark
logo: {
  src: './src/assets/logo.svg',
  replacesTitle: false,
}

// Light/dark pair (preferred when Phase 6 found both files)
logo: {
  light: './src/assets/logo-light.svg',
  dark: './src/assets/logo-dark.svg',
  replacesTitle: true,
}
```

If a `logo:` block already exists in the config, edit it in place — don't add a duplicate. If `logo:` is in a comment or commented-out, uncomment and update.

**b) Splash hero image — `src/content/docs/index.mdx` `hero.image.file`**

Default Starlight splash hero supports a separate (usually larger) image. Check the existing `index.mdx` frontmatter:

```yaml
hero:
  image:
    file: ../../assets/hero-mark.png
    alt: <project name>
```

If a hero candidate was identified in Phase 6, update this path. If the same logo serves both roles, point both at the same file. If the user wants to use the branded `<Hero>` MDX component (richer than the frontmatter hero), point them at the migration guide section that covers it.

**Verify after writing:**

After both surfaces are updated, encourage the user to run `bun dev` and visually confirm the logo renders correctly in both light and dark modes (toggle from the topbar). Common issues:
- Logo is white-on-white in light mode → need a dark variant or use the `light`/`dark` pair pattern
- Logo is way too small/large → adjust the source dimensions or add CSS overrides via `customCss`
- File path is wrong → relative paths in `astro.config.mjs` are relative to the project root, not the file itself

### Phase 10 — Write configs

Show diffs in your reasoning before writing.

#### a) `scripts/python-autodoc.json` (if Python wired up)

```json
{
  "searchPath": "<relative path>",
  "modules": [...],
  "outputDir": "src/content/docs/api"
}
```

#### b) `scripts/ts-autodoc.json` (if TypeScript wired up)

```json
{
  "entryPoints": [...],
  "tsconfig": "<relative path>",
  "outputDir": "src/content/docs/api/ts"
}
```

#### c) `astro.config.mjs`

Multi-edit:

1. Sidebar — ensure entries exist for each enabled generator:
   - `{ label: 'Python API', autogenerate: { directory: 'api' } }` — if Python
   - `{ label: 'TypeScript API', autogenerate: { directory: 'api/ts' } }` — if TS
2. Plugin call — update `motion`/`credit`/`version` from Phase 8.
3. Logo — update `logo.src` from Phase 9.

Don't duplicate sidebar entries. Don't add a second `abstractData(...)` plugin call.

#### d) `package.json`

Add scripts conditionally:
- `"docs:python": "node scripts/build-python-docs.mjs"` — if Python wired up
- `"docs:ts": "node scripts/build-ts-docs.mjs"` — if TS wired up

Update the `build` script to chain them:
```json
"build": "bun run docs:python && bun run docs:ts && astro check && astro build"
```
(Skip the chains for stacks not enabled.)

#### e) Required dev deps for TS

If TS wired up, add to dev deps:
```bash
bun add -d typedoc typedoc-plugin-markdown
```

Tell the user to run this; don't run it yourself.

#### f) Tailor `src/content/docs/quickstart.md` to the detected stack

The scaffolded `quickstart.md` ships with both Python and TypeScript autodoc subsections wrapped in HTML comment markers:

```html
<!-- abstract-data-setup:python-autodoc -->
…Python instructions…
<!-- /abstract-data-setup:python-autodoc -->

<!-- abstract-data-setup:ts-autodoc -->
…TypeScript instructions…
<!-- /abstract-data-setup:ts-autodoc -->
```

After you've finalized the stack(s) for this project (Phase 7), edit `quickstart.md` to remove the irrelevant block:

- **Python only** → strip everything between `<!-- abstract-data-setup:ts-autodoc -->` and `<!-- /abstract-data-setup:ts-autodoc -->` (inclusive).
- **TypeScript only** → strip the Python block similarly.
- **Both** → leave both blocks; remove only the comment markers themselves so the published page is clean.
- **Neither** (no autodoc wired up) → strip both blocks plus the "## Add API reference" heading and intro paragraph.

This is idempotent: re-runs of the skill check whether the markers still exist before pruning. If the user has already removed the markers (or hand-edited the file), leave it alone — never re-inject content into a customized quickstart.

### Phase 11 — Optionally run generators

Per enabled generator, ask: "Generate now? [Yes / No]"

- Python → `bun run docs:python`
- TypeScript → `bun run docs:ts`

Pass through any tool-not-installed errors verbatim.

### Phase 11.5 — Offer docs-author dispatch (if generators ran)

After generation, scan `src/content/docs/api/` for **thin pages** — auto-generated files whose body (after frontmatter and the auto-rendered H1) is fewer than ~200 bytes, OR pages that consist of just signatures with no descriptive prose. These are the "what the heck is this?" pages — the source's docstrings are too sparse for the mechanical autodoc to produce useful output.

If any thin pages are found, surface this to the user:

> "I noticed N of the generated API pages are sparse — your source's docstrings are thin. The companion skill `abstract-data-docs-author` reads the source code itself and writes narrative prose to enrich those pages (module overview, usage example from tests, related-modules cross-references). Want me to invoke it now?"

If yes: hand off to the `abstract-data-docs-author` skill (Claude Code: load the skill at `.claude/skills/abstract-data-docs-author/SKILL.md`; Cursor: refer to `.cursor/rules/abstract-data-docs-author.mdc`). Pass along the project profile and detected stack info so the docs-author skill doesn't have to re-discover.

If no thin pages found, skip this phase silently. Don't push the docs-author skill on a project that doesn't need it.

### Phase 11.7 — Versioned API reference (only if source has 2+ tags)

Run `git -C <source-repo> tag --list 'v*' | wc -l` (or equivalent) on the **source** repo (not the docs project). If the result is < 2, skip this phase silently.

Otherwise, surface the choice:

> "I see your source has N tagged releases. Versioned API reference is supported four ways. Which do you want?"

Multi-choice prompt:

1. **Source-driven (Recommended for API-only versioning).** Adds a `versions` array to `python-autodoc.json` / `ts-autodoc.json`. Each rebuild checks out the source repo at each tag (via `git worktree add`), regenerates the API reference per tag into `<outputDir>/<safeTag>/`, and aliases the default version at the un-versioned URL. Cheap, composable, no branches to maintain. The bundled `<VersionPicker>` component renders a topbar dropdown.
2. **`starlight-versions` plugin** — opinionated, archives the entire site (guides + API). Pick this only if guides drift between versions too. Pre-1.0; expect rough edges.
3. **Branch-per-version** — each major version is a git branch deployed to a subdomain, the main branch's host (Vercel/CF) rewrites `/v2/*` → that subdomain. Best when teams already maintain per-version branches.
4. **Single version (no versioning).** Default if the user is unsure. Easy to add versioning later.

Default the recommendation to **option 1** when the project has Python or TypeScript autodoc wired (Phases 4/5 ran). Default to **option 2** when the docs project has substantial hand-written guides and the user expects them to differ per version.

If the user picks option 1:

a. Surface up to the 5 most recent tags as candidates. Ask which to publish — let them deselect noisy point releases. Mark the most recent as `default: true` unless the user picks a different one (e.g. an LTS tag).

b. Write the `versions` array into the appropriate autodoc JSON config. Example shape:

```jsonc
{
  "searchPath": "../../auditkit/src",
  "modules": [...],
  "outputDir": "src/content/docs/api",
  "versions": [
    { "tag": "v0.4.0", "label": "0.4 (latest)", "default": true },
    { "tag": "v0.3.2", "label": "0.3" },
    { "tag": "v0.2.0", "label": "0.2 (legacy)" }
  ]
}
```

c. **No override needed.** The `abstractData()` plugin already overrides `SocialIcons` to render `<VersionPicker>` next to the existing chip and social links. As soon as the autodoc orchestrator emits per-version pages with `version:` frontmatter, the picker appears in the topbar automatically — no user-side wiring, no `versions` prop to maintain. The picker walks the docs collection at build time, dedupes by tag, picks up the `versionDefault: true` flag for the default version. The autodoc JSON is the single source of truth.

If the autodoc base path differs from the default `/api` (e.g. `outputDir: "src/content/docs/api/ts"` for TypeScript-only sites), pass `apiBase` to the plugin so the picker constructs the right URLs:

```js
starlight({
  plugins: [
    abstractData({
      motion: 'calm',
      apiBase: '/api/ts',
    }),
  ],
})
```

d. **Verify the docs project's content schema accepts the version frontmatter fields.** Read `src/content.config.ts` and confirm the `docsSchema.extend` zod object includes:

```ts
version: z.string().optional(),
versionLabel: z.string().optional(),
versionDefault: z.boolean().optional(),
```

The `create-docs` template scaffold already ships with these. For projects upgraded via `bunx abstract-data-install-skills`, you'll need to add them — without these optional fields, Zod will reject the autodoc-emitted frontmatter and the build fails with `InvalidContentEntryDataError`.

e. Tell the user to run `bun run docs:python` (or `docs:ts`) to populate the per-version directories. The script handles the worktrees automatically.

f. **Optional curated override.** If the user wants to hide pre-release tags or reorder the dropdown, they can wire a user-level override of `SocialIcons` that imports `<VersionPicker>` and passes an explicit `versions` prop — that bypasses auto-discovery. Don't recommend this by default; auto-discovery keeps the autodoc JSON as the single source of truth.

If the user picks option 2 (`starlight-versions`):

- Install: `bun add starlight-versions`
- Add to `astro.config.mjs` plugins array
- Run the plugin's CLI to archive the current state
- Configure `starlight-versions.versions` to match the user's version list
- Note: this conflicts with option 1 — pick *one*.

If the user picks option 3 (branch-per-version):

- This is mostly a deployment-platform concern. Suggest the Knip pattern (Vercel rewrites) and link them at [webpro.nl/scraps/versioned-docs-with-starlight-and-vercel](https://webpro.nl/scraps/versioned-docs-with-starlight-and-vercel). Don't try to wire this yourself — too platform-specific.

If the user picks option 4 (none): skip silently, leave `versions` field absent from the autodoc config.

**Site version vs. API version** — they're different. The `version` chip in the theme's plugin call (e.g. `version: 'v1.0.0'`) is the *site's own* marketing version. The `versions` array in autodoc configs is the *documented API's* versions. A site might be at `v1.2.0` while documenting API `v0.4.0` — that's normal, don't conflate them.

### Phase 12 — Optional pre-commit hook (per-stack)

Fires only if Phase 4a (Python) or Phase 5a (TypeScript) found modules below the 80% coverage threshold.

**Python branch** — if Phase 4a found yellow/red modules, offer:

- Tool: `interrogate` (lightweight, no project changes beyond the hook entry).
- Config: append a `[tool.interrogate]` table to `pyproject.toml` setting `fail-under = 80`, `exclude = ["tests"]`, etc.
- `.pre-commit-config.yaml`: add the `econchick/interrogate` repo with the chosen revision.

**TypeScript branch** — if Phase 5a found yellow/red entry points, offer either:

- **Local script hook (preferred)**: a one-liner `pre-commit` config that runs the docs build script with `--validation.notDocumented` and fails the commit if any new warnings appear. No extra dependencies beyond `typedoc` (already a dev dep).

  ```yaml
  # .pre-commit-config.yaml fragment
  - repo: local
    hooks:
      - id: tsdoc-coverage
        name: TSDoc coverage
        entry: bunx typedoc --plugin typedoc-plugin-markdown --validation.notDocumented --treatValidationWarningsAsErrors true --emit none
        language: system
        types: [ts]
        pass_filenames: false
  ```

- **`tsdoc-coverage` package** (if the user prefers a dedicated tool): npm install `tsdoc-coverage` as a dev dep and wire it as the hook entry instead. Threshold defaults to 80% to match the Python side.

In both stacks: show the user the exact config diff before writing. The pre-commit hook lives in the **source repo**, not the docs repo — extra caution since it's a different project.

### Phase 12.5 — Confirm `starlight-links-validator` is wired

The template ships with `starlight-links-validator` already installed and registered as a Starlight plugin. Verify both during this phase:

1. Read the docs project's `package.json` — confirm `starlight-links-validator` is in `dependencies` (or `devDependencies`).
2. Read `astro.config.mjs` — confirm the plugin is referenced inside `plugins: [...]` on the `starlight(...)` call.
3. Read the docs project's CI workflow (`.github/workflows/*.yml` or equivalent) — confirm `bun run build` (or `astro build`) runs on PRs. The links validator runs as part of the build, so a build-on-PR workflow is enough; no separate step needed.

If any of those three pieces are missing, surface the gap and offer to add it. The plugin's failure mode is "fail the build on any broken internal link" — exactly what you want for CI.

For migrating projects (running `bunx abstract-data-install-skills` rather than scaffolding via `bun create @abstractdata/docs`), the plugin will not be installed automatically. Tell the user:

```bash
bun add starlight-links-validator
```

then add `starlightLinksValidator()` to the `plugins` array in `astro.config.mjs`. Show the diff.

### Phase 13 — Summary

6–10 line markdown summary covering: detected stacks, what got wired up per stack, logo update, mode (motion/credit/version), files updated, generated counts (if Phase 11 ran), next steps.

## Idempotency

- Don't duplicate sidebar entries — check before adding.
- Don't append to `modules`/`entryPoints` arrays — replace cleanly.
- Don't add a second `abstractData(...)` call — update the existing one.
- Don't overwrite content under `src/content/docs/` (only `api/` pages, regenerated by the script).
- Don't add a second logo line — replace.

## Out of scope (this round)

- TanStack route detection auto-config (recipe-only)
- Next.js route map auto-config (recipe-only)
- Prisma schema-doc auto-config (recipe-only)
- Drizzle schema-doc auto-config (recipe-only — no mature tooling)
- README/CHANGELOG/ADR auto-import into the sidebar

## Files this skill reads / writes

**Reads (docs project):** `package.json`, `astro.config.mjs`, `src/assets/`.
**Reads (source project):** `pyproject.toml`, `setup.py`, source tree, `tsconfig.json`, `next.config.*`, dependency manifests, schema files, OpenAPI specs.

**Writes (docs project):** `scripts/python-autodoc.json`, `scripts/ts-autodoc.json`, `astro.config.mjs` (edits), `package.json` (scripts only).

**Writes (source project, with explicit pre-commit consent only):** `.pre-commit-config.yaml`, `pyproject.toml` (dev deps section), `requirements-dev.txt`, or `package.json` (TS dev deps for `tsdoc-coverage` if chosen).

## Notes for the agent

- Be conservative with edits. Show diffs in your reasoning before writing.
- Phase 12 modifies a different repo than the docs project — extra caution.
- For TypeScript: TypeDoc requires `typescript` AND `typedoc` AND `typedoc-plugin-markdown`. If any are missing, the orchestrator will tell the user via the script output. Don't try to install them yourself unless the user explicitly asks.
- For OpenAPI: prefer `@astrojs/starlight-openapi` (mature plugin) over building from scratch.
- Keep conversation tight: detection in 1–3 sentences, audit table 5–8 lines, questions one round at a time, summary 6–10 lines.
