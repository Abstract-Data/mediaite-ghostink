# Abstract Data Documentation Theme — Reference

<!--
  Auto-generated from the SKILL.md sources under .claude/skills/.
  Edit those and run `bun run sync-skills` to regenerate.
  Do not hand-edit this file — changes will be overwritten.
-->

> **Note:** GitHub Copilot applies these instructions globally to every Chat
> interaction in this repo. The workflows below are procedural — Copilot can
> guide the user through them but cannot natively run interactive prompts.
> Use Claude Code or Cursor for fully automated execution.

## Available workflows

- **abstract-data-setup** — detection + configuration + generator wiring
- **abstract-data-docs-author** — read source code, write narrative docs

When a user request matches one of these, follow the relevant workflow below.

---

## Setup workflow (`abstract-data-setup`)

### When this applies

Set up the Abstract Data Documentation Theme (built on Astro Starlight) for a project. Detect source code across stacks (Python, TypeScript, Next.js, TanStack, OpenAPI, Prisma, Drizzle), audit docstring coverage for Python, sniff docstring style (Google/NumPy/Sphinx), detect or pick a logo asset, ask configuration questions (modules/entry points, motion, credit, version), wire up config files (scripts/python-autodoc.json, scripts/ts-autodoc.json, astro.config.mjs sidebar + plugin options, package.json scripts), and optionally install a docstring-coverage pre-commit hook. Use when the user says "set up docs", "configure docs", "wire up Python autodoc", "wire up TypeScript autodoc", "scan my project for docs", "set up Abstract Data docs", "add API reference", "audit docstrings", or similar phrases inside a docs project that uses @abstractdata/starlight-theme (the npm package name; product is the Abstract Data Documentation Theme).

### Procedure

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

---

## Docs Author workflow (`abstract-data-docs-author`)

### When this applies

Read a project's source code and write substantive narrative documentation alongside the auto-generated API reference. Use when the user says "flesh out the docs", "write better docs", "the API pages are too thin", "enrich the docs", "author the docs", "explain this codebase", "fill out the documentation", "the autodoc pages need more context", or similar phrases inside a project that uses @abstractdata/starlight-theme. Typically invoked by abstract-data-setup after generators have produced bare-signatures pages, but can also be invoked standalone when a user says their docs are too sparse.

### Procedure

# Abstract Data Documentation Theme — Docs Author

Read a project's source code and *write* documentation. Complements the auto-generated mechanical API reference (signatures, type hints, structure produced by pydoc-markdown / TypeDoc) by adding narrative prose, motivation, examples, and cross-references — the things mechanical autodoc can never produce well, especially when the source's docstrings are thin.

This skill **enriches**, never **replaces**, the mechanical autodoc output. Always preserve the auto-generated signatures section. Layer prose above it.

## When to invoke

Run this skill when:

- The user says "flesh out the docs", "write better docs", "the API pages are too thin", "enrich the docs", or similar.
- The `abstract-data-setup` skill has just finished generating mechanical autodoc pages that read as terse/empty.
- The user has run `bun run docs:python` (or `docs:ts`) and asks "now make these readable."

If the cwd doesn't have `@abstractdata/starlight-theme` in `package.json` deps, stop and point the user at `bun create @abstractdata/docs`. If `src/content/docs/api/` doesn't exist or is empty, run the setup skill first (or tell the user to).

## Operating principles

1. **Enrich, don't replace.** Always preserve the existing auto-generated content (signatures, type hints, structure). Layer your prose *before* it (as a "Module overview" preface) or *after* it (as "Examples", "Related", "See also" sections). Never delete the mechanical scaffold.

2. **Be honest about uncertainty.** If you're inferring intent from a function name without good context, say so. Phrases like "appears to handle…" are better than confident wrong claims.

3. **Read tests for examples.** If the project has tests, they're the most reliable source of usage patterns. Quote test code (lightly cleaned up) for examples whenever possible — it's true by construction.

4. **Token-budget discipline.** Don't try to read the whole codebase in one pass. Loop module by module, smallest first. Each iteration's context is just one module's source + that module's existing autodoc page. For 30-module projects, that's 30 small conversations, not one giant one.

5. **Idempotent.** If a page already has an "Overview" preface (you wrote one before), refresh it rather than appending a second. Look for marker comments or distinctive heading patterns.

6. **Don't hallucinate features.** If the source code doesn't do something, don't write that it does. The reader will trust your prose; lying is worse than terse pages.

## Workflow

### Phase 1 — Discover the project

Read these files (top-down, bail if absent):

- `package.json` — confirm `@abstractdata/starlight-theme` dep
- `astro.config.mjs` — confirm Starlight project
- `scripts/python-autodoc.json` and/or `scripts/ts-autodoc.json` — confirm autodoc has been wired
- `src/content/docs/api/` — list existing auto-generated pages
- The source project's `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md` if present
- Any `docs/adr/` directory or `ARCHITECTURE.md` — important context

Note the source project root (from `searchPath` in `python-autodoc.json` or `entryPoints` in `ts-autodoc.json`). All source reads go relative to that.

### Phase 1.5 — Inventory existing prose

Before profiling or writing anything new, build a manifest of prose that **already exists in the source project**. Most projects have a substantial amount of usable narrative scattered across `README.md`, `CHANGELOG.md`, ADRs, and existing docstrings — rewriting it from scratch wastes tokens and risks contradicting the source's own voice.

For each candidate file, read it once and produce a line-item inventory:

- **`README.md`** — for each `##` section, note: heading, ~10-word summary, candidate destination. Common reuse targets:
  - "Quick start" / "Installation" / "Getting started" → `src/content/docs/quickstart.md`
  - "Features" / "What it does" / "Why use this" → `src/content/docs/index.mdx` hero subtitle + `concepts.md` intro
  - "Architecture" / "How it works" / "Design" → `src/content/docs/concepts.md` body
  - "Configuration" / "Options" → a guide or the relevant module overview
  - "Examples" / "Usage" → split across module Example blocks
  - "Contributing" → leave in repo, link from docs sidebar
- **`CHANGELOG.md`** — note the most recent 1–3 entries. Don't import wholesale; harvest noteworthy feature additions for the concepts page ("Recent additions") or for module overviews ("Added in v0.4 to address …").
- **`docs/adr/*.md`** or **`ARCHITECTURE.md`** — for each ADR, note: title, decision, the 1–2 sentence rationale. ADRs are *gold* for the `concepts.md` page — they explain *why* the architecture looks the way it does. Quote the rationale, link out to the ADR for full context.
- **`CONTRIBUTING.md`** — usually stays in repo; mine for any "How to add a new X" sections that should become how-to guides under `src/content/docs/guides/`.
- **Existing module docstrings** — even if the autodoc page reads as thin, the source `.py` / `.ts` may have a leading module docstring with usable framing. Note which modules have them (Phase 6 will reuse the wording verbatim where appropriate).

Output the inventory as a brief plan to memory before moving on:

```
README sections worth lifting:
  - "## Quick start" → quickstart.md (verbatim, light edit)
  - "## How it works" → concepts.md intro (paraphrase)
  - "## Why httpx?" → core/http_scan module overview (paraphrase + link to ADR-007)

CHANGELOG highlights:
  - v0.4: Added BaseHttpScanModule (link to ADR-007)
  - v0.3: AI integration via Ollama (concepts.md "Optional integrations" section)

ADRs:
  - ADR-001 "Use httpx not requests" → quote in concepts.md
  - ADR-007 "BaseHttpScanModule" → quote in core/http_scan overview

Modules with usable existing docstrings: auditkit.core, auditkit.transport.curl_impersonate
```

When you reach Phases 5 and 6, **prefer lifting existing prose** (with light cleanup and proper attribution if it's a paraphrase from an ADR) over fabricating new wording. Always offer the user a side-by-side: "README says X, ADR says Y, here's the merged version — keep, edit, or rewrite?"

If the source project has *no* README beyond a one-liner and *no* ADRs, say so up front — the user should know the docs-author run will need to invent more, and that voice will be yours rather than the project's.

### Phase 2 — Profile the project

Spend 1–2 conversation turns building a project profile. Not a deep code read yet — orientation only:

- Read `README.md` (one document) — extract the elevator pitch, the core problem the project solves, the primary user.
- Read top-level CLI entry points or top-level `index.ts` exports — understand the public surface.
- Read `pyproject.toml` / `package.json` description fields and keywords.
- Skim test directory names (don't read full tests yet) — understand testing organization.

Write a **3–5 sentence project profile** to memory. This profile is the lens for every module-level write that follows. Examples:

> "auditkit is a security-audit CLI that scans websites for misconfigurations across 9 categories. It's modular: each scan module inherits from `ScanModule` and runs async via httpx. Heavy use of pydantic for data validation. AI integration via Ollama is optional."

Reuse this voice in every module overview you write.

### Phase 3 — Build the module map

For each existing page in `src/content/docs/api/`:

1. Read the page (current state — may be terse/empty).
2. Read the corresponding source file from the source project.
3. Note: file size, public symbols, imports (which other modules does it depend on?), test coverage (is there a `test_<module>.py`?).

Build an in-memory map: `{ pageName, sourcePath, publicSymbols, dependencies, hasTests, currentPageBytes }`. Smallest pages first — they're cheapest to enrich and the user gets early wins.

### Phase 4 — Find usage examples

For each module with tests, locate 1–2 representative test cases. Look for:

- Tests with descriptive names (`test_login_browser_with_valid_credentials`)
- Tests that exercise the public API directly (not internal helpers)
- Short tests (under ~20 lines) — easier to inline as examples

Note these locations. You'll quote them in Phase 6.

### Phase 5 — Write narrative pages

Before per-module work, write the high-leverage **narrative pages** that don't exist yet. Check first — if `src/content/docs/concepts.md` (or similar) already has user-written content, leave it alone. Otherwise, draft:

- **`src/content/docs/concepts.md`** — architecture overview. 300–600 words. Source the structure from imports + ADRs + your project profile. Cover: core abstractions, data flow, key types, extension points.

- **`src/content/docs/guides/getting-started.md`** *(if not present)* — distilled from README quickstart. Should be hands-on, end with the user having run a thing.

- **`src/content/docs/guides/<workflow>.md`** — for each repeated test pattern, write a how-to. Examples: "Adding a new scan module", "Configuring authentication", "Writing custom callbacks". One workflow per file.

Don't generate every possible guide — pick the 2–3 most valuable based on the project profile. Quality over quantity.

After writing, update `astro.config.mjs` sidebar to add a "Concepts" / "Guides" group if not present.

### Phase 6 — Module-by-module enrichment loop

For each module page in your map, smallest-first:

1. **Read the source file** (the actual `.py` / `.ts` file, not just docstrings). Understand what it does.
2. **Detect existing enrichment.** If the page already has a `<!-- abstract-data-docs-author:overview -->` comment marker, you wrote a preface before — refresh it instead of duplicating.
3. **Write a "Module overview" preface** (150–300 words) covering:
   - **What this module is** — one-sentence description tied to the project profile
   - **Why it exists** — what role does it play in the larger system
   - **When to use it** — typical entry point or trigger
   - **Key types or functions** — a 3–5 bullet list pointing at the most important public symbols
4. **Add an "Example" section** quoting a test case (cleaned up if needed). Wrap in a code block with the right language.
5. **Add a "Related" footer** linking 2–3 sibling modules (from the imports map). Format: `- [`module.name`](/api/module_name/)` — one-line description.
6. **Inject** the preface above the existing auto-generated content. Keep the example and related sections after.
7. **Save** with the marker comments so the next run is idempotent:

```markdown
<!-- abstract-data-docs-author:overview -->
[your preface]
<!-- /abstract-data-docs-author:overview -->

[existing auto-generated content untouched]

<!-- abstract-data-docs-author:example -->
[example section]
<!-- /abstract-data-docs-author:example -->

<!-- abstract-data-docs-author:related -->
[related links]
<!-- /abstract-data-docs-author:related -->
```

After each module, **stop and confirm with the user** before continuing. Show the diff. Let them approve, edit, or reject. This is mandatory — never bulk-apply prose without per-module review.

### Phase 7 — Cross-reference pass

After all module pages enriched (or as many as the user opted into), do one final pass to cross-reference:

- Inside any page, if you mention another module by name, link it: ``` `auditkit.config.AuditConfig` ``` → `[\`auditkit.config.AuditConfig\`](/api/auditkit_config/#auditconfig-objects)`.
- Add a "Used by" reverse-lookup section to high-leverage modules — "this is imported by X, Y, Z".

This is the polish pass. Skip if the user is fatigued.

### Phase 8 — Summary

Write a 6–10 line markdown summary covering:

- Modules enriched / skipped
- Narrative pages written
- Total prose added (rough word count)
- Any modules where you got stuck or recommended manual follow-up
- Suggested next step (e.g., "Run `bun dev` and walk the new pages")

## Templates

Use these as starting points, not rigid forms.

### Module overview template (Python)

```markdown
**What this is:** [One-sentence description in the project's voice. E.g., "OAuth lifecycle helpers for jre-vidget's YouTube integration."]

**Why it exists:** [What role does it play. E.g., "Isolates browser-based auth from the CLI surface — no Rich, no video logic, no terminal state."]

**When to use it:** [Typical entry point. E.g., "Call `login_browser()` once during onboarding to mint a refresh token. Subsequent runs use `get_credentials()` to refresh on demand."]

**Key surfaces:**
- `login_browser(client_id, client_secret)` — interactive OAuth flow, returns `AuthConfig`
- `get_credentials(auth)` — refreshes on demand, returns `google.oauth2.credentials.Credentials`
- `AuthError` — raised when credentials are missing or unrefreshable
```

### Class/function preface template

For pages that document a single class or function (rare with pydoc-markdown's per-module output but happens), use:

```markdown
**Purpose:** [why this exists]

**Key behavior:** [what it does, 2-3 sentences]

**Common usage:**
```python
[short example]
```
```

### Example block template

```markdown
## Example

[1-line context: "Logging in for the first time:"]

```python
[10-15 lines of cleaned test code or synthesized usage]
```

[1-line outcome: "After this, `auth.refresh_token` is set and persisted via `write_config_safely`."]
```

## Where dynamic `<head>` / metadata belongs

If during the Phase 5 narrative-page work you find yourself wanting to inject something dynamic into `<head>` — JSON-LD structured data (`Article`, `BreadcrumbList`, `SoftwareSourceCode`), per-page Open Graph image URLs, breadcrumb meta tags, or any computed-from-frontmatter `<meta>` tag — **the right layer is route middleware, not a component override.**

Starlight ≥ 0.32 lets you mutate `Astro.locals.starlightRoute.head` from a function exported by a file referenced as `routeMiddleware:` in `astro.config.mjs`. This is much cleaner than overriding the `<Head>` component because it composes with other plugins, doesn't break when Starlight bumps versions, and lets you read the current page's frontmatter before deciding what to inject.

Sketch:

```ts
// src/routeData.ts
import { defineRouteMiddleware } from '@astrojs/starlight/route-data';

export const onRequest = defineRouteMiddleware((context) => {
  const route = context.locals.starlightRoute;
  // route.entry.data is the frontmatter; route.headings is the TOC tree.
  route.head.push({
    tag: 'script',
    attrs: { type: 'application/ld+json' },
    content: JSON.stringify({
      '@context': 'https://schema.org',
      '@type': 'Article',
      headline: route.entry.data.title,
      description: route.entry.data.description,
    }),
  });
});
```

```js
// astro.config.mjs
starlight({
  routeMiddleware: './src/routeData.ts',
  // …
})
```

If the user explicitly wants any of these features (JSON-LD, dynamic OG images, breadcrumb meta), point them at this file as the place to wire it. Don't override the `<Head>` component just to inject computed meta — that's an anti-pattern documented in the Starlight migration notes for ≥ 0.33.

## What this skill does NOT do

- **Doesn't rewrite source code.** That's a different operation. If the user wants to add docstrings to the source, that's `abstract-data-setup`'s Phase 4 territory (audit + suggest enrichment), not this skill's.
- **Doesn't generate API reference from scratch.** That's pydoc-markdown / TypeDoc's job. This skill *layers on top of* that output.
- **Doesn't guess at private symbols.** Only document the public API surface. Helper functions with leading underscores are skipped.
- **Doesn't auto-commit.** Writes files, leaves git up to the user.

## Files this skill reads

- The docs project's `package.json`, `astro.config.mjs`, `scripts/python-autodoc.json` / `scripts/ts-autodoc.json`, existing `src/content/docs/api/*.md`.
- The source project's `README.md`, source files (`.py` / `.ts`), test files, ADRs, `pyproject.toml`/`package.json`.

## Files this skill writes

- `src/content/docs/api/*.md` — enriched (preface + example + related sections injected around existing autodoc).
- `src/content/docs/concepts.md` — narrative architecture overview (only if not already user-authored).
- `src/content/docs/guides/*.md` — per-workflow how-to (only if not already user-authored).
- `astro.config.mjs` — sidebar updates to add new groups for Concepts / Guides.

## Notes for the agent

- **Never bulk-apply.** Always confirm per-module before writing.
- **Token discipline.** Read one module's source per loop iteration. Don't try to hold the whole codebase in context.
- **Preserve markers.** The HTML comment markers (`<!-- abstract-data-docs-author:overview -->`) are how the next run finds and refreshes existing prose. Don't strip them.
- **When stuck:** if you can't form a coherent preface for a module (the source is too thin or too obscure), say so and skip. Don't write nonsense.
- **The mechanical autodoc is the floor.** Your job is to raise the ceiling.

---
