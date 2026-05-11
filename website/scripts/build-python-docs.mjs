#!/usr/bin/env node
/**
 * build-python-docs.mjs
 *
 * Orchestrates Python autodoc generation for this Starlight site.
 *
 * Reads `scripts/python-autodoc.json` for configuration:
 *   - searchPath: relative path to your Python source root (parent of the package directory)
 *   - modules:    list of fully-qualified module names to document
 *   - outputDir:  where the generated .md files land (relative to project root)
 *   - repoUrl:    (optional) base URL for "View source on GitHub" links
 *   - repoBranch: (optional) default 'main'
 *   - versions:   (optional) array of { tag, label, default } for versioned API docs
 *                 — when present, the script does one build per tag via git worktrees,
 *                   emitting into <outputDir>/<safeTag>/. The default version's pages
 *                   ALSO emit at <outputDir>/<page>.md (the un-versioned URL) so existing
 *                   links keep working.
 *
 * For each module, in each version:
 *   1. Invokes `pydoc-markdown -I <searchPath> -m <module>` to capture markdown.
 *   2. Lifts the first H1 into Starlight `title:` frontmatter, synthesizes a
 *      `description:` from the first paragraph, injects `version: <tag>` if versioned.
 *   3. Post-processes thin pages (auto-generates Submodules section on package landings,
 *      injects a `:::note` banner on truly-empty pages).
 *
 * Run via:
 *   bun run docs:python
 *
 * Requires Python ≥ 3.9 and pydoc-markdown:
 *   pipx install pydoc-markdown
 */
import { execSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync, rmSync, mkdtempSync } from 'node:fs';
import { join, resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(__dirname, '..');
const CONFIG_PATH = resolve(__dirname, 'python-autodoc.json');

const c = {
  reset: '\x1b[0m', dim: '\x1b[2m', cyan: '\x1b[36m', gold: '\x1b[33m',
  red: '\x1b[31m', green: '\x1b[32m',
};
const log = (...a) => console.log(...a);
const die = (msg) => { console.error(`${c.red}error${c.reset} ${msg}`); process.exit(1); };

// ─── Load config ──────────────────────────────────────────────────────
if (!existsSync(CONFIG_PATH)) die(`Missing config: ${CONFIG_PATH}`);
const cfg = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));
if (!cfg.searchPath) die('python-autodoc.json: `searchPath` is required.');
if (!Array.isArray(cfg.modules) || cfg.modules.length === 0) {
  die('python-autodoc.json: `modules` must be a non-empty array.');
}

const ORIGINAL_SEARCH_PATH = resolve(PROJECT_ROOT, cfg.searchPath);
const outputDir = resolve(PROJECT_ROOT, cfg.outputDir ?? 'src/content/docs/api');

if (!existsSync(ORIGINAL_SEARCH_PATH)) {
  die(`searchPath does not exist: ${ORIGINAL_SEARCH_PATH}\n  Resolved from cfg.searchPath = "${cfg.searchPath}"`);
}

// ─── Verify pydoc-markdown is available ───────────────────────────────
log(`${c.dim}→ checking pydoc-markdown${c.reset}`);
try {
  execSync('pydoc-markdown --version', { stdio: 'ignore' });
} catch {
  die(`pydoc-markdown not found on PATH. Install it:
    pipx install pydoc-markdown
    # or
    pip install --user pydoc-markdown
  Then re-run this script.`);
}

// ─── Versioning setup ────────────────────────────────────────────────
//
// If `versions` is configured, each entry triggers an independent build
// from a `git worktree` checkout of the source repo at that tag. We need
// to know:
//   - the source repo root (where `.git` lives) so we can `git -C` it
//   - the relative path from source-repo-root to the original searchPath,
//     so we can map it to the equivalent path inside each worktree
//
// We walk up from ORIGINAL_SEARCH_PATH looking for `.git`; bail out if we
// hit the filesystem root without finding it.
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
let SEARCH_PATH_REL = null;
if (versions) {
  if (versions.length === 0) die('`versions` is an empty array — set it to null/omit, or list at least one version.');
  if (!versions.some((v) => v.tag)) die('`versions[].tag` is required on every entry.');
  if (versions.filter((v) => v.default).length > 1) die('Only one `versions[].default: true` allowed.');
  if (!versions.some((v) => v.default)) {
    log(`${c.gold}warn${c.reset} no version marked default; treating the first one (${versions[0].tag}) as default`);
    versions[0].default = true;
  }

  SOURCE_REPO_ROOT = findGitRoot(ORIGINAL_SEARCH_PATH);
  if (!SOURCE_REPO_ROOT) {
    die(`versions[] is configured but no .git directory was found above ${ORIGINAL_SEARCH_PATH}.\n  Versioned builds require the source to be a git checkout.`);
  }
  SEARCH_PATH_REL = relative(SOURCE_REPO_ROOT, ORIGINAL_SEARCH_PATH);
  log(`${c.dim}→ source repo: ${SOURCE_REPO_ROOT}${c.reset}`);
  log(`${c.dim}→ relative searchPath: ${SEARCH_PATH_REL || '(repo root)'}${c.reset}`);
}

// Make a tag filesystem-safe for use as a directory name. We have to be
// strict here: Astro's slug normalizer strips dots from URL segments
// (`0.1.0` → `010`), so if our directory names contain dots the URL the
// VersionPicker constructs won't match the rendered URL. Convert dots
// to dashes (and any other non-alphanumeric to dashes) so the directory
// name AND the URL slug Astro generates from it stay byte-identical.
//   v0.3.0 → 0-3-0
//   v1.0.0-rc.1 → 1-0-0-rc-1
function safeTag(tag) {
  return tag.replace(/^v/, '').replace(/[^a-zA-Z0-9_-]/g, '-');
}

// ─── Per-build pipeline (one invocation per version, or one total) ─────
function buildOnce({ searchPath, version }) {
  // version may be null (single-version mode) or { tag, label, default }
  const versionDir = version ? join(outputDir, safeTag(version.tag)) : outputDir;
  mkdirSync(versionDir, { recursive: true });

  const tagPrefix = version
    ? `${c.cyan}[${version.label ?? version.tag}]${c.reset} `
    : '';
  log(`${c.dim}→ ${tagPrefix}generating ${cfg.modules.length} module page${cfg.modules.length === 1 ? '' : 's'}${c.reset}`);

  // Two-pass build: first collect every page in memory so the thin-page
  // post-processor can cross-reference siblings (for "Submodules" sections
  // on package landing pages), then write everything to disk.
  const pages = [];

  for (const mod of cfg.modules) {
    const safeName = mod.replace(/\./g, '_');
    const outPath = join(versionDir, `${safeName}.md`);

    let markdown;
    try {
      markdown = execSync(
        `pydoc-markdown -I "${searchPath}" -m ${mod}`,
        { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] },
      );
    } catch {
      log(`${c.red}  ✗ ${tagPrefix}${mod}${c.reset}`);
      continue;
    }

    // ─── Frontmatter post-process ────────────────────────────────
    const h1 = markdown.match(/^# (.+?)$/m);
    const title = (h1?.[1] ?? mod).trim().replace(/\\_/g, '_');
    let body = h1 ? markdown.replace(h1[0] + '\n', '') : markdown;
    body = body.replace(/<a id="[^"]*"><\/a>\n?/g, '');
    body = body.replace(
      /:(?:mod|class|func|obj|attr|meth|exc|any|data|const)(?::)?\s*`([^`]+)`/g,
      '`$1`',
    );
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
    const description = (desc ?? `API reference for \`${mod}\`.`)
      .trim().replace(/`/g, '').replace(/"/g, "'").slice(0, 160);

    const fmLines = ['---', `title: ${title}`, `description: "${description}"`];
    if (version) {
      // Emit version metadata. `versionDefault: true` lets the bundled
      // <VersionPicker> auto-discover which version to pre-select without
      // duplicating the canonical list outside the autodoc JSON config.
      fmLines.push(`version: "${version.tag}"`);
      if (version.label) fmLines.push(`versionLabel: "${version.label}"`);
      if (version.default) fmLines.push(`versionDefault: true`);
      // Hide versioned-subdir pages from the sidebar — the default version
      // is *also* aliased at the un-versioned URL (sidebar-visible there),
      // and historic versions are reachable only via the VersionPicker.
      // Without this every module would appear N+1 times in the sidebar.
      fmLines.push('sidebar:', '  hidden: true');
    }
    fmLines.push('---', '');
    const frontmatter = fmLines.join('\n');

    pages.push({ mod, safeName, outPath, title, description, body, frontmatter });
    log(`${c.green}  ✓${c.reset} ${tagPrefix}${mod} ${c.dim}→ ${relative(PROJECT_ROOT, outPath)}${c.reset}`);
  }

  if (pages.length === 0) {
    log(`${c.red}  no pages generated for ${version ? version.tag : 'single build'} — skipping.${c.reset}`);
    return { pages: [] };
  }

  // ─── Thin-page post-processor ──────────────────────────────────────
  const childrenOf = (mod) => pages.filter((p) => p.mod !== mod && p.mod.startsWith(mod + '.'));
  let enriched = 0;
  let bannered = 0;

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

    const kids = childrenOf(page.mod);
    const isPackageLanding = kids.length > 0;

    let newBody = page.body;
    let touched = false;

    // Stale-version banner: non-default versions get a "Latest is X →"
    // pointer at the top of every page. Lives above the thin/package
    // banners since version drift is the higher-priority signal.
    //
    // The link target is the *un-versioned* (default-aliased) URL, not
    // the per-version subdir, because the default version is emitted at
    // both `/api/<page>/` and `/api/<safeTag>/<page>/` — the bare URL is
    // the canonical, sidebar-visible one. The site prefix from
    // `cfg.urlBasePrefix` must be included or starlight-links-validator
    // rejects the link (base prefix is required at validation time).
    if (version && !version.default) {
      const defaultVersion = (cfg.versions ?? []).find((v) => v.default);
      const latestLabel = defaultVersion ? (defaultVersion.label ?? defaultVersion.tag) : 'latest';
      const stalePrefix = (cfg.urlBasePrefix ?? '/').replace(/\/$/, '');
      const staleBaseDir = cfg.outputDir
        .replace(/^src\/content\/docs\/?/, '')
        .replace(/\/$/, '');
      const latestPath = defaultVersion
        ? `${stalePrefix}/${staleBaseDir}/${page.safeName}/`
        : null;
      const link = latestPath ? `[${latestLabel} →](${latestPath})` : latestLabel;
      const stale = [
        '',
        `:::caution[Older version]`,
        `You're viewing **${version.label ?? version.tag}**. Latest is ${link}.`,
        ':::',
        '',
      ].join('\n');
      newBody = stale + newBody;
      touched = true;
    }

    if (isThin && !isPackageLanding) {
      const noteBlock = [
        '',
        ':::note[This page is sparse]',
        `The auto-generated reference for \`${page.mod}\` is short. Expanding the source docstring at the top of \`${page.mod.replace(/\./g, '/')}.py\` (a sentence about purpose, when to use it, and a tiny example) would populate this page with real context.`,
        ':::',
        '',
      ].join('\n');
      newBody = noteBlock + newBody;
      bannered += 1;
      touched = true;
      log(`${c.gold}  ⚠${c.reset} ${tagPrefix}thin-page banner on ${page.mod}`);
    }

    if (isPackageLanding) {
      // Build absolute, base-prefixed Starlight URLs (`/<base>/api/<slug>/`)
      // for each child page. `cfg.outputDir` is `src/content/docs/api`, which
      // maps to URL path `/api/`. Astro's `base` setting (`/mediaite-ghostink`)
      // must be prepended so starlight-links-validator can resolve them
      // against the generated page list (it joins base+slug at validate time).
      // Relative `./*.md` links would be rejected by the validator's default
      // `errorOnRelativeLinks: true`.
      const urlBaseDir = cfg.outputDir
        .replace(/^src\/content\/docs\/?/, '')
        .replace(/\/$/, '');
      const sitePrefix = (cfg.urlBasePrefix ?? '/mediaite-ghostink').replace(/\/$/, '');
      const versionSeg = version ? `${safeTag(version.tag)}/` : '';
      const lines = ['', '## Submodules', ''];
      for (const kid of kids) {
        const summary = kid.description && !kid.description.startsWith('API reference for')
          ? ` — ${kid.description}`
          : '';
        const kidUrl = `${sitePrefix}/${urlBaseDir}/${versionSeg}${kid.safeName}/`;
        lines.push(`- [\`${kid.mod}\`](${kidUrl})${summary}`);
      }
      lines.push('');
      const submodulesSection = lines.join('\n');

      if (isThin) {
        // Replace stub body with brief intro + submodules. If we already
        // prepended a stale-version banner, preserve it at the very top.
        const stalePrefix = newBody.startsWith('\n:::caution[Older version]')
          ? newBody.slice(0, newBody.indexOf(':::\n', 1) + 4) + '\n'
          : '';
        newBody = stalePrefix +
          `\nTop-level package — see submodules below for the documented API surface.\n${submodulesSection}`;
      } else {
        newBody = newBody.replace(/\s+$/, '') + '\n' + submodulesSection;
      }
      enriched += 1;
      touched = true;
      log(`${c.green}  ✓${c.reset} added Submodules section to ${page.mod} (${kids.length} child${kids.length === 1 ? '' : 'ren'})`);
    }

    if (touched && cfg.repoUrl) {
      const branch = version ? version.tag : (cfg.repoBranch ?? 'main');
      const repo = cfg.repoUrl.replace(/\/$/, '');
      const sourcePath = page.mod.replace(/\./g, '/');
      const target = isPackageLanding
        ? `${sourcePath}/__init__.py`
        : `${sourcePath}.py`;
      newBody = newBody.replace(/\s+$/, '') +
        `\n\n## See also\n\n- [View source on GitHub](${repo}/blob/${branch}/${target})\n`;
    }

    writeFileSync(page.outPath, page.frontmatter + newBody);
  }

  log('');
  log(`${c.green}✓${c.reset} ${tagPrefix}Generated ${c.gold}${pages.length}${c.reset} page${pages.length === 1 ? '' : 's'} in ${c.cyan}${relative(PROJECT_ROOT, versionDir)}${c.reset}/`);
  if (enriched || bannered) {
    log(`${c.dim}  ${enriched} package landing${enriched === 1 ? '' : 's'} enriched, ${bannered} thin page${bannered === 1 ? '' : 's'} flagged${c.reset}`);
  }

  return { pages };
}

// ─── Run: single-build or per-version with worktrees ──────────────────
const createdWorktrees = [];

function cleanup() {
  for (const wt of createdWorktrees) {
    try {
      execSync(`git -C "${SOURCE_REPO_ROOT}" worktree remove --force "${wt}"`,
        { stdio: 'ignore' });
    } catch {
      // best-effort; if remove failed, rm -rf the directory
      try { rmSync(wt, { recursive: true, force: true }); } catch {}
    }
  }
}

process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

try {
  if (!versions) {
    // Single-version build (existing behavior)
    buildOnce({ searchPath: ORIGINAL_SEARCH_PATH, version: null });
  } else {
    // Per-version builds via git worktrees
    for (const v of versions) {
      const wt = mkdtempSync(join(tmpdir(), `autodoc-${safeTag(v.tag)}-`));
      createdWorktrees.push(wt);
      log(`${c.dim}→ git worktree add ${wt} ${v.tag}${c.reset}`);
      try {
        execSync(`git -C "${SOURCE_REPO_ROOT}" worktree add --detach "${wt}" "${v.tag}"`,
          { stdio: 'inherit' });
      } catch {
        die(`Failed to create git worktree for ${v.tag}.\n  Verify the tag exists in ${SOURCE_REPO_ROOT}: git tag --list "${v.tag}"`);
      }
      const wtSearchPath = SEARCH_PATH_REL ? join(wt, SEARCH_PATH_REL) : wt;
      if (!existsSync(wtSearchPath)) {
        log(`${c.gold}warn${c.reset} ${v.tag}: searchPath ${wtSearchPath} doesn't exist (the directory layout may have changed). Skipping.`);
        continue;
      }
      buildOnce({ searchPath: wtSearchPath, version: v });
    }

    // Also emit the default version at the un-versioned path so existing
    // links to /api/foo/ keep resolving without a redirect step.
    const defaultV = versions.find((v) => v.default);
    if (defaultV) {
      log(`${c.dim}→ aliasing ${defaultV.tag} as the default (un-versioned) build${c.reset}`);
      const wt = mkdtempSync(join(tmpdir(), `autodoc-default-`));
      createdWorktrees.push(wt);
      try {
        execSync(`git -C "${SOURCE_REPO_ROOT}" worktree add --detach "${wt}" "${defaultV.tag}"`,
          { stdio: 'ignore' });
        const wtSearchPath = SEARCH_PATH_REL ? join(wt, SEARCH_PATH_REL) : wt;
        // Stash original outputDir, point at root for un-versioned emit
        buildOnce({ searchPath: wtSearchPath, version: null });
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
log(`${c.dim}  { label: 'API Reference', autogenerate: { directory: '${cfg.outputDir.replace(/^src\/content\/docs\/?/, '')}' } }${c.reset}`);
if (versions) {
  log(`${c.dim}  → with ${versions.length} version${versions.length === 1 ? '' : 's'}, the sidebar will auto-group by version subdirectory.${c.reset}`);
  log(`${c.dim}  → import VersionPicker: import { VersionPicker } from '@abstractdata/starlight-theme/components';${c.reset}`);
}
log('');
