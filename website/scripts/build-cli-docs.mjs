#!/usr/bin/env node
/**
 * build-cli-docs.mjs
 *
 * Orchestrates per-version Typer CLI documentation generation, mirroring
 * the contract used by `build-python-docs.mjs` so the two stay
 * interchangeable from a user perspective.
 *
 * For each version listed in `scripts/cli-autodoc.json` (populated by
 * `sync-versions.mjs`):
 *
 *   1. `git worktree add --detach <wt> <tag>` into a temp directory.
 *   2. `uv sync --frozen [--extra <e>]…` inside that worktree so
 *      `forensics.cli` is importable against that tag's pinned deps.
 *   3. `uv run --directory <wt> python <REPO_ROOT>/scripts/generate_cli_docs.py
 *         --out <outputDir>/<safeTag>
 *         --version <tag>
 *         [--version-default]`
 *      The script is the *current main* generator (with `--version` support)
 *      pointed at the *tag's* venv — older tags don't necessarily have the
 *      `--version` flag in their copy of the script, so we always shell out
 *      to the current one.
 *   4. After per-version builds, alias the default version at the
 *      un-versioned URL by running the generator one more time with
 *      `--version-segment ""`, into the bare `outputDir`. That keeps
 *      `/cli/forensics-preflight/` etc. resolving to the latest release
 *      without a redirect step.
 *
 * Single-version fallback: when `cli-autodoc.json` has no `versions[]`
 * (e.g. pre-1.0 repo with no tags yet), the orchestrator does one
 * unversioned build from the current checkout — same behavior as calling
 * the Python generator directly.
 *
 * Run via:
 *   bun run docs:cli
 *
 * Requires:
 *   - `uv` on PATH (per-tag dependency sync).
 *   - `git` on PATH (worktree creation).
 *   - In CI: `actions/checkout@v4` with `fetch-depth: 0` (no shallow
 *     clones — worktrees require the tag commits to be present locally).
 */
import { execSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, mkdirSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEBSITE_ROOT = resolve(__dirname, '..');
const REPO_ROOT = resolve(WEBSITE_ROOT, '..');
const CONFIG_PATH = resolve(__dirname, 'cli-autodoc.json');

const c = {
  reset: '\x1b[0m', dim: '\x1b[2m', cyan: '\x1b[36m', gold: '\x1b[33m',
  red: '\x1b[31m', green: '\x1b[32m',
};
const log = (...a) => console.log(...a);
const die = (msg) => { console.error(`${c.red}error${c.reset} ${msg}`); process.exit(1); };

if (!existsSync(CONFIG_PATH)) {
  die(`Missing config: ${CONFIG_PATH}\n  Run \`node website/scripts/sync-versions.mjs\` first.`);
}

let cfg;
try {
  cfg = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'));
} catch (err) {
  die(`Failed to parse ${CONFIG_PATH}: ${err.message}`);
}

const OUTPUT_DIR = resolve(WEBSITE_ROOT, cfg.outputDir ?? 'src/content/docs/cli');
const GENERATOR = resolve(REPO_ROOT, cfg.generatorScript ?? 'scripts/generate_cli_docs.py');
const UV_EXTRAS = Array.isArray(cfg.uvExtras) ? cfg.uvExtras : ['dev'];
const versions = Array.isArray(cfg.versions) ? cfg.versions : null;

if (!existsSync(GENERATOR)) {
  die(`generator script does not exist: ${GENERATOR}`);
}

function safeTag(tag) {
  return tag.replace(/^v/, '').replace(/[^a-zA-Z0-9_-]/g, '-');
}

// `uv sync --frozen` per worktree. Some older lockfiles may resolve to wheels
// that are no longer on PyPI; on failure we log and skip the version rather
// than tanking the entire build (consumers of pinned older docs are rare
// enough that "show the latest two reliably" beats "show none").
function uvSyncInWorktree(wt, label) {
  const extras = UV_EXTRAS.map((e) => `--extra ${e}`).join(' ');
  const cmd = `uv sync --frozen ${extras}`;
  log(`${c.dim}→ ${label}: ${cmd}${c.reset}`);
  try {
    execSync(cmd, { cwd: wt, stdio: 'inherit' });
    return true;
  } catch (err) {
    log(`${c.gold}warn${c.reset} ${label}: uv sync failed (${err.message}). Skipping this version.`);
    return false;
  }
}

function runGenerator({ wt, outDir, versionTag, versionLabel, versionDefault, versionSegment }) {
  mkdirSync(outDir, { recursive: true });
  const args = ['--out', outDir];
  if (versionTag) {
    args.push('--version', versionTag);
    if (versionLabel) args.push('--version-label', versionLabel);
    if (versionDefault) args.push('--version-default');
  }
  if (versionSegment !== undefined) {
    args.push('--version-segment', versionSegment);
  }
  // `uv run --directory <wt>` activates the worktree's .venv (so
  // `from forensics.cli import app` resolves to the tag's code) but uses
  // the absolute path to the *current* generator script. Older tags don't
  // know about --version, so we never use their copy of the script.
  const quoted = args.map((a) => `"${a.replace(/"/g, '\\"')}"`).join(' ');
  const cmd = `uv run --directory "${wt}" python "${GENERATOR}" ${quoted}`;
  log(`${c.dim}→ ${cmd}${c.reset}`);
  execSync(cmd, { stdio: 'inherit' });
}

// Worktree bookkeeping for cleanup on exit / signal.
const createdWorktrees = [];
function cleanup() {
  for (const wt of createdWorktrees) {
    try {
      execSync(`git -C "${REPO_ROOT}" worktree remove --force "${wt}"`, { stdio: 'ignore' });
    } catch {
      try { rmSync(wt, { recursive: true, force: true }); } catch {}
    }
  }
}
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

try {
  if (!versions || versions.length === 0) {
    log(`${c.cyan}cli-autodoc:${c.reset} no versions configured — running single-version (main) build.`);
    runGenerator({ wt: REPO_ROOT, outDir: OUTPUT_DIR });
    log(`${c.green}✓${c.reset} CLI docs written to ${relative(WEBSITE_ROOT, OUTPUT_DIR)}/`);
    process.exit(0);
  }

  log(`${c.cyan}cli-autodoc:${c.reset} ${versions.length} version${versions.length === 1 ? '' : 's'} configured`);
  for (const v of versions) {
    if (!v.tag) die(`versions[] entry is missing \`tag\`: ${JSON.stringify(v)}`);
  }

  for (const v of versions) {
    const safe = safeTag(v.tag);
    const versionDir = join(OUTPUT_DIR, safe);
    const wt = mkdtempSync(join(tmpdir(), `cli-docs-${safe}-`));
    createdWorktrees.push(wt);

    log(`\n${c.cyan}[${v.label ?? v.tag}]${c.reset} git worktree add ${wt} ${v.tag}`);
    try {
      execSync(
        `git -C "${REPO_ROOT}" worktree add --detach "${wt}" "${v.tag}"`,
        { stdio: 'inherit' },
      );
    } catch {
      log(`${c.gold}warn${c.reset} ${v.tag}: worktree add failed (tag not present? run with fetch-depth: 0 in CI). Skipping.`);
      continue;
    }

    if (!uvSyncInWorktree(wt, v.tag)) {
      continue;
    }

    runGenerator({
      wt,
      outDir: versionDir,
      versionTag: v.tag,
      versionLabel: v.label,
      versionDefault: !!v.default,
    });
    log(`${c.green}✓${c.reset} ${v.tag} → ${relative(WEBSITE_ROOT, versionDir)}/`);
  }

  // Alias the default version at the un-versioned URL so existing inbound
  // links (`/cli/forensics-preflight/`) and the "latest" sidebar entry keep
  // working without redirects. We re-run from the default version's
  // worktree (already in createdWorktrees) with `--version-segment ""` so
  // cross-page links inside these aliased pages stay at the bare URL.
  const defaultV = versions.find((v) => v.default);
  if (defaultV) {
    const defaultSafe = safeTag(defaultV.tag);
    log(`\n${c.cyan}default-alias:${c.reset} aliasing ${defaultV.tag} at ${relative(WEBSITE_ROOT, OUTPUT_DIR)}/`);
    const wt = mkdtempSync(join(tmpdir(), `cli-docs-default-`));
    createdWorktrees.push(wt);
    try {
      execSync(
        `git -C "${REPO_ROOT}" worktree add --detach "${wt}" "${defaultV.tag}"`,
        { stdio: 'inherit' },
      );
      if (uvSyncInWorktree(wt, `${defaultV.tag} (alias)`)) {
        // The aliased pages live at `outputDir/` (no subdir). To keep the
        // versioned subdir intact, we generate into a temp dir and then
        // copy *only* the top-level .md files — `--clean` would otherwise
        // wipe the per-version subdirectories we just built.
        const aliasTmp = mkdtempSync(join(tmpdir(), `cli-alias-${defaultSafe}-`));
        runGenerator({
          wt,
          outDir: aliasTmp,
          versionTag: defaultV.tag,
          versionLabel: defaultV.label,
          versionDefault: true,
          versionSegment: '',
        });
        // Copy the alias .md files into OUTPUT_DIR root without touching subdirs.
        const { readdirSync, copyFileSync, statSync } = await import('node:fs');
        for (const entry of readdirSync(aliasTmp)) {
          const src = join(aliasTmp, entry);
          if (!entry.endsWith('.md')) continue;
          if (!statSync(src).isFile()) continue;
          copyFileSync(src, join(OUTPUT_DIR, entry));
        }
        rmSync(aliasTmp, { recursive: true, force: true });
        log(`${c.green}✓${c.reset} default alias landed at ${relative(WEBSITE_ROOT, OUTPUT_DIR)}/`);
      }
    } catch (err) {
      log(`${c.gold}warn${c.reset} default-alias failed: ${err.message}`);
    }
  }
} finally {
  cleanup();
}

log(`\n${c.green}✓${c.reset} CLI docs generation complete.`);
