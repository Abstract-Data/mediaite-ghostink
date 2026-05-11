#!/usr/bin/env node
/**
 * build-ts-docs.mjs
 *
 * Generates Starlight-compatible Markdown API reference from a
 * TypeScript project's source via TypeDoc + typedoc-plugin-markdown.
 *
 * Reads `scripts/ts-autodoc.json` for configuration:
 *   - entryPoints:       array of TS entry files (e.g. ["../../my-lib/src/index.ts"])
 *   - tsconfig:          path to the project's tsconfig.json
 *   - outputDir:         where the generated .md pages land
 *   - githubPages:       pass through to TypeDoc
 *   - skipErrorChecking: pass through to TypeDoc
 *   - repoUrl:           (optional) base URL for "View on GitHub" footer
 *   - repoBranch:        (optional) default 'main'
 *   - versions:          (optional) array of { tag, label, default } for versioned docs.
 *                        When present, each tag triggers an independent build
 *                        from a `git worktree` checkout into <outputDir>/<safeTag>/.
 *                        The default version is also aliased at the un-versioned
 *                        URL so existing links keep resolving.
 *
 * For each module, TypeDoc emits a markdown file. The orchestrator
 * post-processes each one to add Starlight `title:` frontmatter, a `version:`
 * field when versioned, and a stale-version banner on non-default builds.
 *
 * Run:
 *   bun run docs:ts
 *
 * Requires:
 *   bun add -d typedoc typedoc-plugin-markdown
 */
import { execSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(__dirname, '..');
const CONFIG_PATH = resolve(__dirname, 'ts-autodoc.json');

const c = {
  reset: '\x1b[0m', dim: '\x1b[2m', cyan: '\x1b[36m', gold: '\x1b[33m',
  red: '\x1b[31m', green: '\x1b[32m',
};
const log = (...a) => console.log(...a);
const die = (msg) => { console.error(`${c.red}error${c.reset} ${msg}`); process.exit(1); };

// ─── Load config ──────────────────────────────────────────────────────
if (!existsSync(CONFIG_PATH)) die(`Missing config: ${CONFIG_PATH}`);
const cfg = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));
if (!Array.isArray(cfg.entryPoints) || cfg.entryPoints.length === 0) {
  die('ts-autodoc.json: `entryPoints` must be a non-empty array.');
}

const ROOT_OUTPUT = resolve(PROJECT_ROOT, cfg.outputDir ?? 'src/content/docs/api/ts');
const ROOT_TSCONFIG = cfg.tsconfig ? resolve(PROJECT_ROOT, cfg.tsconfig) : null;

// ─── Verify TypeDoc available ─────────────────────────────────────────
log(`${c.dim}→ checking typedoc${c.reset}`);
try {
  execSync('npx --no-install typedoc --version', { cwd: PROJECT_ROOT, stdio: 'ignore' });
} catch {
  die(`typedoc not found. Install it as a dev dep:
    bun add -d typedoc typedoc-plugin-markdown
  Then re-run this script.`);
}

// ─── Versioning setup ────────────────────────────────────────────────
function findGitRoot(start) {
  let dir = start;
  while (true) {
    if (existsSync(join(dir, '.git'))) return dir;
    const parent = dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

const versions = Array.isArray(cfg.versions) ? cfg.versions : null;
let SOURCE_REPO_ROOT = null;
let ENTRY_POINTS_REL = null;
let TSCONFIG_REL = null;
if (versions) {
  if (versions.length === 0) die('`versions` is an empty array — set it to null/omit, or list at least one version.');
  if (!versions.some((v) => v.tag)) die('`versions[].tag` is required on every entry.');
  if (versions.filter((v) => v.default).length > 1) die('Only one `versions[].default: true` allowed.');
  if (!versions.some((v) => v.default)) {
    log(`${c.gold}warn${c.reset} no version marked default; treating the first one (${versions[0].tag}) as default`);
    versions[0].default = true;
  }
  // Use the first entry point to find the source git repo. All entries
  // must live under the same repo for versioned builds to make sense.
  const firstEntry = resolve(PROJECT_ROOT, cfg.entryPoints[0]);
  SOURCE_REPO_ROOT = findGitRoot(firstEntry);
  if (!SOURCE_REPO_ROOT) {
    die(`versions[] is configured but no .git directory was found above ${firstEntry}.\n  Versioned builds require the source to be a git checkout.`);
  }
  ENTRY_POINTS_REL = cfg.entryPoints.map((e) =>
    relative(SOURCE_REPO_ROOT, resolve(PROJECT_ROOT, e)),
  );
  TSCONFIG_REL = ROOT_TSCONFIG ? relative(SOURCE_REPO_ROOT, ROOT_TSCONFIG) : null;
  log(`${c.dim}→ source repo: ${SOURCE_REPO_ROOT}${c.reset}`);
  log(`${c.dim}→ entryPoints (rel): ${ENTRY_POINTS_REL.join(', ')}${c.reset}`);
}

// Make a tag filesystem-safe for use as a directory name. We have to be
// strict here: Astro's slug normalizer strips dots from URL segments
// (`0.1.0` → `010`), so if our directory names contain dots the URL the
// VersionPicker constructs won't match the rendered URL. Convert dots
// to dashes (and any other non-alphanumeric to dashes).
//   v0.3.0 → 0-3-0
//   v1.0.0-rc.1 → 1-0-0-rc-1
function safeTag(tag) {
  return tag.replace(/^v/, '').replace(/[^a-zA-Z0-9_-]/g, '-');
}

// ─── Per-build pipeline ──────────────────────────────────────────────
function buildOnce({ entryPoints, tsconfig, version }) {
  const outDir = version ? join(ROOT_OUTPUT, safeTag(version.tag)) : ROOT_OUTPUT;
  mkdirSync(outDir, { recursive: true });

  const tagPrefix = version ? `${c.cyan}[${version.label ?? version.tag}]${c.reset} ` : '';
  log(`${c.dim}→ ${tagPrefix}generating TypeScript API pages${c.reset}`);

  const args = [
    '--plugin', 'typedoc-plugin-markdown',
    '--out', outDir,
    '--readme', 'none',
    '--hideBreadcrumbs', 'true',
    '--hidePageHeader', 'true',
  ];
  if (tsconfig) args.push('--tsconfig', tsconfig);
  if (cfg.skipErrorChecking) args.push('--skipErrorChecking');
  for (const entry of entryPoints) args.push(entry);

  try {
    execSync(`npx typedoc ${args.map((a) => `"${a}"`).join(' ')}`,
      { cwd: PROJECT_ROOT, stdio: 'inherit' });
  } catch {
    log(`${c.red}error${c.reset} ${tagPrefix}typedoc failed; skipping this build`);
    return;
  }

  // Post-process every emitted .md
  log(`${c.dim}→ ${tagPrefix}adding Starlight frontmatter${c.reset}`);

  function walk(dir) {
    const out = [];
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) out.push(...walk(full));
      else if (entry.name.endsWith('.md')) out.push(full);
    }
    return out;
  }

  const pages = [];
  for (const file of walk(outDir)) {
    let content = readFileSync(file, 'utf8');
    if (content.startsWith('---\n')) continue;

    const h1 = content.match(/^# (.+?)$/m);
    const fallbackTitle = relative(outDir, file).replace(/\.md$/, '').replace(/[\\/_]/g, ' ');
    const title = (h1?.[1] ?? fallbackTitle).trim().replace(/\\_/g, '_');
    const body = h1 ? content.replace(h1[0] + '\n', '') : content;

    const desc = body.split('\n').find((l) => {
      const t = l.trim();
      if (!t) return false;
      if (/^#{1,6} /.test(t)) return false;
      if (t.startsWith('```')) return false;
      if (t.startsWith('|')) return false;
      if (/^[-*+] /.test(t)) return false;
      if (/^<[^>]+>/.test(t)) return false;
      return true;
    });
    const description = (desc ?? `API reference for \`${title}\`.`)
      .trim().replace(/`/g, '').replace(/"/g, "'").slice(0, 160);

    const fmLines = ['---', `title: ${title}`, `description: "${description}"`];
    if (version) {
      // Emit version metadata. `versionDefault: true` lets the bundled
      // <VersionPicker> auto-discover which version to pre-select without
      // duplicating the canonical list outside the autodoc JSON config.
      fmLines.push(`version: "${version.tag}"`);
      if (version.label) fmLines.push(`versionLabel: "${version.label}"`);
      if (version.default) fmLines.push(`versionDefault: true`);
    }
    fmLines.push('---', '');
    const frontmatter = fmLines.join('\n');
    pages.push({ file, title, description, body, frontmatter });
  }

  // Thin-page post-processor (TS)
  let bannered = 0, enriched = 0;
  const landingPage = pages.find((p) => /^(index|readme|globals|modules)\.md$/i.test(relative(outDir, p.file)));

  for (const page of pages) {
    const proseLines = page.body.split('\n').filter((l) => {
      const t = l.trim();
      if (!t) return false;
      if (/^#{1,6} /.test(t)) return false;
      if (t.startsWith('```')) return false;
      if (t.startsWith('|') || /^[-=]{3,}/.test(t)) return false;
      if (/^[-*+] /.test(t)) return false;
      if (/^<[^>]+>/.test(t)) return false;
      return true;
    }).length;
    const bodyChars = page.body.replace(/\s+/g, '').length;
    const isThin = bodyChars < 150 && proseLines < 1;

    let newBody = page.body;
    let touched = false;

    if (version && !version.default) {
      const defaultV = (cfg.versions ?? []).find((v) => v.default);
      const latestLabel = defaultV ? (defaultV.label ?? defaultV.tag) : 'latest';
      const apiBase = `/${cfg.outputDir.replace(/^src\/content\/docs\/?/, '').replace(/\/$/, '')}`;
      const sameRel = relative(outDir, page.file).replace(/\.md$/, '');
      const latestPath = defaultV
        ? `${apiBase}/${safeTag(defaultV.tag)}/${sameRel}/`
        : null;
      const link = latestPath ? `[${latestLabel} →](${latestPath})` : latestLabel;
      const stale = [
        '', `:::caution[Older version]`,
        `You're viewing **${version.label ?? version.tag}**. Latest is ${link}.`,
        ':::', '',
      ].join('\n');
      newBody = stale + newBody;
      touched = true;
    }

    if (page === landingPage) {
      const others = pages.filter((p) => p !== landingPage);
      if (others.length > 0) {
        const lines = ['', '## Submodules', ''];
        for (const sib of others) {
          const rel = relative(outDir, sib.file).replace(/\.md$/, '');
          const summary = sib.description && !sib.description.startsWith('API reference for')
            ? ` — ${sib.description}` : '';
          lines.push(`- [\`${sib.title}\`](./${rel}.md)${summary}`);
        }
        lines.push('');
        const submodulesSection = lines.join('\n');
        if (isThin) {
          newBody = newBody + `\nTop-level entry — see modules below for the full API surface.\n${submodulesSection}`;
        } else {
          newBody = newBody.replace(/\s+$/, '') + '\n' + submodulesSection;
        }
        enriched += 1;
        touched = true;
        log(`${c.green}  ✓${c.reset} ${tagPrefix}added Submodules to ${relative(outDir, page.file)}`);
      }
    } else if (isThin) {
      const noteBlock = [
        '', ':::note[This page is sparse]',
        `The auto-generated reference for \`${page.title}\` is short. Expanding the leading \`/** ... */\` TSDoc comment in the source (purpose, when to use it, a tiny example) would populate this page with real context.`,
        ':::', '',
      ].join('\n');
      newBody = noteBlock + newBody;
      bannered += 1;
      touched = true;
      log(`${c.gold}  ⚠${c.reset} ${tagPrefix}thin-page banner on ${relative(outDir, page.file)}`);
    }

    if (touched && cfg.repoUrl) {
      const branch = version ? version.tag : (cfg.repoBranch ?? 'main');
      const repo = cfg.repoUrl.replace(/\/$/, '');
      newBody = newBody.replace(/\s+$/, '') +
        `\n\n## See also\n\n- [View on GitHub](${repo}/tree/${branch})\n`;
    }

    writeFileSync(page.file, page.frontmatter + newBody);
  }

  log('');
  log(`${c.green}✓${c.reset} ${tagPrefix}Generated ${c.gold}${pages.length}${c.reset} TS API page${pages.length === 1 ? '' : 's'} in ${c.cyan}${relative(PROJECT_ROOT, outDir)}${c.reset}/`);
  if (enriched || bannered) log(`${c.dim}  ${enriched} landing page${enriched === 1 ? '' : 's'} enriched, ${bannered} thin page${bannered === 1 ? '' : 's'} flagged${c.reset}`);
}

// ─── Run: single-build or per-version with worktrees ──────────────────
const createdWorktrees = [];

function cleanup() {
  for (const wt of createdWorktrees) {
    try {
      execSync(`git -C "${SOURCE_REPO_ROOT}" worktree remove --force "${wt}"`, { stdio: 'ignore' });
    } catch {
      try { rmSync(wt, { recursive: true, force: true }); } catch {}
    }
  }
}
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

try {
  if (!versions) {
    buildOnce({
      entryPoints: cfg.entryPoints.map((e) => resolve(PROJECT_ROOT, e)),
      tsconfig: ROOT_TSCONFIG,
      version: null,
    });
  } else {
    for (const v of versions) {
      const wt = mkdtempSync(join(tmpdir(), `tsdoc-${safeTag(v.tag)}-`));
      createdWorktrees.push(wt);
      log(`${c.dim}→ git worktree add ${wt} ${v.tag}${c.reset}`);
      try {
        execSync(`git -C "${SOURCE_REPO_ROOT}" worktree add --detach "${wt}" "${v.tag}"`, { stdio: 'inherit' });
      } catch {
        log(`${c.red}error${c.reset} failed to create worktree for ${v.tag}; skipping`);
        continue;
      }
      const wtEntries = ENTRY_POINTS_REL.map((rel) => join(wt, rel));
      const wtTsconfig = TSCONFIG_REL ? join(wt, TSCONFIG_REL) : null;
      const missing = wtEntries.find((p) => !existsSync(p));
      if (missing) {
        log(`${c.gold}warn${c.reset} ${v.tag}: entry point ${missing} not found; skipping`);
        continue;
      }
      buildOnce({ entryPoints: wtEntries, tsconfig: wtTsconfig, version: v });
    }

    // Alias the default version at un-versioned URLs
    const defaultV = versions.find((v) => v.default);
    if (defaultV) {
      log(`${c.dim}→ aliasing ${defaultV.tag} as the default (un-versioned) build${c.reset}`);
      const wt = mkdtempSync(join(tmpdir(), `tsdoc-default-`));
      createdWorktrees.push(wt);
      try {
        execSync(`git -C "${SOURCE_REPO_ROOT}" worktree add --detach "${wt}" "${defaultV.tag}"`, { stdio: 'ignore' });
        const wtEntries = ENTRY_POINTS_REL.map((rel) => join(wt, rel));
        const wtTsconfig = TSCONFIG_REL ? join(wt, TSCONFIG_REL) : null;
        buildOnce({ entryPoints: wtEntries, tsconfig: wtTsconfig, version: null });
      } catch (err) {
        log(`${c.gold}warn${c.reset} default-alias build failed: ${err.message}`);
      }
    }
  }
} finally {
  cleanup();
}

log('');
log(`${c.dim}Sidebar wiring (astro.config.mjs):${c.reset}`);
log(`${c.dim}  { label: 'TS API', autogenerate: { directory: '${cfg.outputDir.replace(/^src\/content\/docs\/?/, '')}' } }${c.reset}`);
if (versions) log(`${c.dim}  → with ${versions.length} version${versions.length === 1 ? '' : 's'}, the sidebar auto-groups by version subdirectory.${c.reset}`);
log('');
