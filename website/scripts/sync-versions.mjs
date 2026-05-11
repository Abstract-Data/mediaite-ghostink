#!/usr/bin/env node
/**
 * sync-versions.mjs
 *
 * Resolve the canonical list of release versions for the docs site and
 * write it into the two autodoc configs that orchestrate per-tag builds:
 *
 *   - website/scripts/python-autodoc.json   (Python API reference)
 *   - website/scripts/cli-autodoc.json      (Typer CLI reference)
 *
 * Single source of truth for which tags ship into versioned docs:
 *
 *   1. Read `.release-please-manifest.json` to discover the *current*
 *      package version (the `.` entry).
 *   2. Cross-reference `git tag --list 'v*.*.*'` to discover all published
 *      tags (release-please pins `include-v-in-tag: true`, so all tags
 *      should start with `v`).
 *   3. Sort by semver (numeric-aware), keep the most recent N (default 5),
 *      and mark the manifest version as default.
 *
 * Hybrid versioning contract (Option C):
 *   - Versioned: Python API + Typer CLI reference (per-tag rebuilds).
 *   - Evergreen: operator docs, ADRs, getting-started, landing page,
 *     Quarto report (always `main`).
 *
 * The two consumed autodoc configs share the contract used by
 * `build-python-docs.mjs`: `versions[]` is an array of
 * `{ tag, label, default }` entries. When `versions[]` is absent the
 * orchestrators do a single-version build (current main).
 *
 * Bootstrap: if no `v*.*.*` tags exist, this script logs a warning and
 * removes `versions[]` from both configs so the orchestrators fall back
 * to single-version builds. That keeps pre-release repos working without
 * special-casing.
 *
 * Run via:
 *   node website/scripts/sync-versions.mjs           # default behavior
 *   KEEP_VERSIONS=10 node website/scripts/sync-versions.mjs   # keep last 10
 *
 * CLI flags (any subset):
 *   --keep N            override KEEP_VERSIONS / default 5
 *   --dry-run           print the resolved versions[] to stdout, do not
 *                       touch any config files
 *
 * Exit codes:
 *   0  versions resolved and configs updated (or in dry-run mode)
 *   1  unrecoverable error (no manifest, no git, invalid JSON, etc.)
 */
import { execSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCRIPTS_DIR = __dirname;
const WEBSITE_ROOT = resolve(__dirname, '..');
const REPO_ROOT = resolve(WEBSITE_ROOT, '..');

const MANIFEST = resolve(REPO_ROOT, '.release-please-manifest.json');
const PYTHON_AUTODOC = resolve(SCRIPTS_DIR, 'python-autodoc.json');
const CLI_AUTODOC = resolve(SCRIPTS_DIR, 'cli-autodoc.json');

const args = process.argv.slice(2);
const DRY_RUN = args.includes('--dry-run');
const keepIdx = args.indexOf('--keep');
const KEEP = Number.parseInt(
  keepIdx >= 0 ? args[keepIdx + 1] : process.env.KEEP_VERSIONS || '5',
  10,
);

const c = {
  reset: '\x1b[0m', dim: '\x1b[2m', cyan: '\x1b[36m', gold: '\x1b[33m',
  red: '\x1b[31m', green: '\x1b[32m',
};
const log = (...a) => console.log(...a);
const die = (msg) => { console.error(`${c.red}error${c.reset} ${msg}`); process.exit(1); };

if (!Number.isInteger(KEEP) || KEEP <= 0) {
  die(`--keep must be a positive integer, got ${KEEP}.`);
}

if (!existsSync(MANIFEST)) {
  die(`Missing release-please manifest: ${MANIFEST}.\n  Versioned docs require release-please to be configured (see release-please-config.json + .release-please-manifest.json).`);
}

let currentVersion;
try {
  const manifest = JSON.parse(readFileSync(MANIFEST, 'utf8'));
  currentVersion = manifest['.'];
  if (typeof currentVersion !== 'string') {
    die(`Manifest ${MANIFEST} does not contain a "." key with a string version. Got: ${JSON.stringify(manifest)}`);
  }
} catch (err) {
  die(`Could not parse ${MANIFEST}: ${err.message}`);
}

let rawTags;
try {
  rawTags = execSync('git tag --list "v*.*.*" --sort=-v:refname', {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  })
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
} catch (err) {
  die(`git tag failed: ${err.message}.\n  This script must run inside the repository checkout (REPO_ROOT=${REPO_ROOT}).`);
}

// Tag-list source of truth. Cross-reference the manifest to pick `default`.
const expectedDefault = `v${currentVersion}`;
if (rawTags.length === 0) {
  log(`${c.gold}warn${c.reset} no v*.*.* tags found in ${REPO_ROOT}. Falling back to single-version (main) docs.`);
} else if (!rawTags.includes(expectedDefault)) {
  log(`${c.gold}warn${c.reset} manifest declares ${expectedDefault} but tag is not present locally (in CI, ensure fetch-depth: 0). Using newest tag instead.`);
}

const tagList = rawTags.slice(0, KEEP);
const defaultTag = rawTags.includes(expectedDefault) ? expectedDefault : tagList[0];

const versions = tagList.map((tag) => ({
  tag,
  label: tag.replace(/^v/, ''),
  default: tag === defaultTag,
}));

// ─── Logging ──────────────────────────────────────────────────────────
log(`${c.dim}→ release-please manifest version: ${c.reset}${currentVersion}`);
log(`${c.dim}→ git tags discovered: ${c.reset}${rawTags.length} (keeping last ${tagList.length})`);
if (versions.length > 0) {
  for (const v of versions) {
    const mark = v.default ? `${c.green}default${c.reset}` : `${c.dim}    -  ${c.reset}`;
    log(`   ${mark}  ${v.tag}`);
  }
} else {
  log(`${c.dim}   (no versions resolved — orchestrators will do single-version main build)${c.reset}`);
}

if (DRY_RUN) {
  log(`\n${c.cyan}--dry-run:${c.reset} not writing any files.`);
  process.exit(0);
}

// ─── Patch autodoc configs ────────────────────────────────────────────
function patchConfig(configPath) {
  if (!existsSync(configPath)) {
    log(`${c.dim}skip ${relative(REPO_ROOT, configPath)} (does not exist)${c.reset}`);
    return false;
  }
  let cfg;
  try {
    cfg = JSON.parse(readFileSync(configPath, 'utf8'));
  } catch (err) {
    die(`Failed to parse ${configPath}: ${err.message}`);
  }

  if (versions.length === 0) {
    // Remove `versions` to fall back to single-version mode if no tags exist.
    if ('versions' in cfg) {
      delete cfg.versions;
      writeFileSync(configPath, JSON.stringify(cfg, null, 2) + '\n');
      log(`${c.gold}~${c.reset} ${relative(REPO_ROOT, configPath)} (removed stale versions[])`);
      return true;
    }
    return false;
  }

  cfg.versions = versions;
  writeFileSync(configPath, JSON.stringify(cfg, null, 2) + '\n');
  log(`${c.green}✓${c.reset} ${relative(REPO_ROOT, configPath)} (versions[] = ${versions.length})`);
  return true;
}

patchConfig(PYTHON_AUTODOC);
patchConfig(CLI_AUTODOC);
