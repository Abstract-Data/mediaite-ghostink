#!/usr/bin/env node
/**
 * sync-docs.mjs
 *
 * Copies canonical Markdown from the repo-root `docs/` directory into the
 * Starlight content collection at `website/src/content/docs/`.
 *
 *   docs/<NAME>.md          → src/content/docs/synced/<slug>.md
 *   docs/adr/<file>.md      → src/content/docs/adr/<slug>.md
 *
 * For each file:
 *   1. Strip the first H1 (Starlight renders the title from frontmatter).
 *   2. Synthesize YAML frontmatter (`title` from H1, `description` from the
 *      first prose paragraph truncated to 160 chars, `editUrl` pointing back
 *      to the canonical source on GitHub).
 *   3. Rewrite internal Markdown links per the rules below.
 *
 * Outputs are gitignored — they are deterministic and regenerated on every
 * `bun run dev` / `bun run build` via the `sync-docs` npm script.
 *
 * Link rewriting:
 *   docs/<allowed>.md           → /synced/<slug>/
 *   docs/adr/<file>.md          → /adr/<slug>/
 *   ../adr/<file>.md            → /adr/<slug>/
 *   anything else outside the   → absolute GitHub URL on main
 *     allow-list (repo-root
 *     files, off-list docs,
 *     code, _quarto.yml, etc.)
 *
 * Idempotent: re-running on a clean tree produces identical output.
 *
 * Run via:
 *   bun run sync-docs
 */
import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
  statSync,
  rmSync,
  existsSync,
} from 'node:fs';
import { dirname, resolve, join, basename, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEBSITE_ROOT = resolve(__dirname, '..');
const REPO_ROOT = resolve(WEBSITE_ROOT, '..');
const DOCS_DIR = resolve(REPO_ROOT, 'docs');
const SYNCED_DIR = resolve(WEBSITE_ROOT, 'src/content/docs/synced');
const ADR_OUT = resolve(WEBSITE_ROOT, 'src/content/docs/adr');

const GITHUB_REPO = 'https://github.com/Abstract-Data/mediaite-ghostink';
const EDIT_BASE = `${GITHUB_REPO}/edit/main`;
const BLOB_BASE = `${GITHUB_REPO}/blob/main`;

// Astro `base` value from astro.config.mjs. Internal absolute links must be
// prefixed with this so starlight-links-validator's page lookup matches the
// rendered URL (it joins base + slug when building its allow list).
const SITE_BASE = '/mediaite-ghostink';

const TOP_LEVEL_ALLOW = new Set([
  'ARCHITECTURE.md',
  'RUNBOOK.md',
  'TESTING.md',
  'GUARDRAILS.md',
  'DEPLOYMENTS.md',
  'EXIT_CODES.md',
]);

const c = {
  reset: '\x1b[0m',
  dim: '\x1b[2m',
  cyan: '\x1b[36m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  gold: '\x1b[33m',
};
const log = (...a) => console.log(...a);

function slugify(name) {
  return name
    .toLowerCase()
    .replace(/\.md$/i, '')
    .replace(/_/g, '-')
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

function escapeYamlString(s) {
  return s.replace(/"/g, '\\"');
}

function extractTitleAndBody(markdown) {
  const lines = markdown.split('\n');
  let titleLine = null;
  let titleIndex = -1;
  for (let i = 0; i < lines.length; i += 1) {
    const m = lines[i].match(/^#\s+(.+?)\s*$/);
    if (m) {
      titleLine = m[1].trim();
      titleIndex = i;
      break;
    }
  }
  if (titleLine === null) {
    return { title: null, body: markdown };
  }
  const body = [...lines.slice(0, titleIndex), ...lines.slice(titleIndex + 1)].join('\n');
  return { title: titleLine, body };
}

function firstProseParagraph(body) {
  const lines = body.split('\n');
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith('#')) continue;
    if (line.startsWith('```')) continue;
    if (line.startsWith('|')) continue;
    if (line.startsWith('>')) continue;
    if (/^[-*+]\s/.test(line)) continue;
    if (/^<[^>]+>/.test(line)) continue;
    if (/^---+$/.test(line)) continue;
    return line;
  }
  return null;
}

function truncate(s, n) {
  if (s.length <= n) return s;
  const cut = s.slice(0, n);
  const lastSpace = cut.lastIndexOf(' ');
  return lastSpace > n - 30 ? `${cut.slice(0, lastSpace)}…` : `${cut}…`;
}

function rewriteLinks(body, sourceRelPath) {
  // Markdown links: [text](target) and reference-style not handled here
  // because the synced sources do not use ref-style links (verified).
  return body.replace(/\]\(([^)]+)\)/g, (match, target) => {
    const trimmed = target.trim();
    // Leave anchors, mailto, external URLs alone
    if (/^https?:\/\//i.test(trimmed)) return match;
    if (trimmed.startsWith('#')) return match;
    if (/^mailto:/i.test(trimmed)) return match;

    // Split off any inline fragment / title
    const [pathPart, ...rest] = trimmed.split(/(\s+|#)/);
    const fragment = rest.join('');

    // Resolve the link target relative to the source file's repo path
    const sourceDir = dirname(sourceRelPath);
    let resolved;
    try {
      resolved = relative(REPO_ROOT, resolve(REPO_ROOT, sourceDir, pathPart));
    } catch {
      return match;
    }
    // Normalize Windows-style backslashes just in case
    resolved = resolved.replace(/\\/g, '/');

    // Rule: docs/adr/<file>.md → <base>/adr/<slug>/
    const adrMatch = resolved.match(/^docs\/adr\/(.+\.md)$/i);
    if (adrMatch) {
      const slug = slugify(adrMatch[1]);
      return `](${SITE_BASE}/adr/${slug}/${fragment})`;
    }

    // Rule: docs/<TOP_LEVEL_ALLOW>.md → <base>/synced/<slug>/
    const docsTop = resolved.match(/^docs\/([^/]+\.md)$/i);
    if (
      docsTop &&
      (TOP_LEVEL_ALLOW.has(docsTop[1]) || TOP_LEVEL_ALLOW.has(docsTop[1].toUpperCase()))
    ) {
      const slug = slugify(docsTop[1]);
      return `](${SITE_BASE}/synced/${slug}/${fragment})`;
    }

    // Everything else points to canonical source on main
    return `](${BLOB_BASE}/${resolved}${fragment})`;
  });
}

function buildFrontmatter({ title, description, editUrl }) {
  const lines = ['---', `title: "${escapeYamlString(title)}"`];
  if (description) {
    lines.push(`description: "${escapeYamlString(description)}"`);
  }
  if (editUrl) {
    lines.push(`editUrl: "${editUrl}"`);
  }
  lines.push('---', '');
  return lines.join('\n');
}

function processFile(repoRelPath, outAbsPath) {
  const absPath = resolve(REPO_ROOT, repoRelPath);
  if (!existsSync(absPath)) {
    log(`${c.red}  ✗${c.reset} missing: ${repoRelPath}`);
    return false;
  }
  const raw = readFileSync(absPath, 'utf8');
  const { title, body } = extractTitleAndBody(raw);
  if (!title) {
    log(`${c.red}  ✗${c.reset} no H1 found: ${repoRelPath} — skipped`);
    return false;
  }
  const para = firstProseParagraph(body);
  const description = para ? truncate(para.replace(/`/g, ''), 160) : '';
  const rewritten = rewriteLinks(body, repoRelPath).replace(/^\s+/, '');
  const editUrl = `${EDIT_BASE}/${repoRelPath}`;
  const fm = buildFrontmatter({ title, description, editUrl });
  mkdirSync(dirname(outAbsPath), { recursive: true });
  writeFileSync(outAbsPath, fm + rewritten + (rewritten.endsWith('\n') ? '' : '\n'));
  log(`${c.green}  ✓${c.reset} ${repoRelPath} ${c.dim}→ ${relative(WEBSITE_ROOT, outAbsPath)}${c.reset}`);
  return true;
}

function syncTopLevel() {
  log(`${c.dim}→ syncing top-level operator docs${c.reset}`);
  // Clean stale outputs so renames / removals propagate
  if (existsSync(SYNCED_DIR)) {
    rmSync(SYNCED_DIR, { recursive: true, force: true });
  }
  mkdirSync(SYNCED_DIR, { recursive: true });
  let n = 0;
  for (const fname of TOP_LEVEL_ALLOW) {
    const out = join(SYNCED_DIR, `${slugify(fname)}.md`);
    if (processFile(`docs/${fname}`, out)) n += 1;
  }
  return n;
}

function writeAdrIndex(adrSlugs) {
  const indexPath = join(ADR_OUT, 'index.md');
  const lines = [
    '---',
    'title: "Decision records"',
    'description: "Architecture decision records for the mediaite-ghostink forensic pipeline."',
    '---',
    '',
    'Each ADR captures a single architectural decision: the context, the choice',
    'made, the alternatives weighed, and the consequences. Records are immutable',
    'once accepted — superseding decisions land as new ADRs that link back.',
    '',
    '| ADR | Title |',
    '|-----|-------|',
  ];
  for (const { slug, title } of adrSlugs) {
    const cleanTitle = title.replace(/\|/g, '\\|');
    lines.push(`| [${slug}](${SITE_BASE}/adr/${slug}/) | ${cleanTitle} |`);
  }
  lines.push('');
  writeFileSync(indexPath, lines.join('\n'));
}

function syncAdrs() {
  log(`${c.dim}→ syncing ADRs${c.reset}`);
  if (existsSync(ADR_OUT)) {
    rmSync(ADR_OUT, { recursive: true, force: true });
  }
  mkdirSync(ADR_OUT, { recursive: true });
  const adrDir = join(DOCS_DIR, 'adr');
  if (!existsSync(adrDir)) {
    log(`${c.gold}  ⚠${c.reset} no docs/adr/ directory found — skipping`);
    return 0;
  }
  const files = readdirSync(adrDir)
    .filter((f) => f.endsWith('.md'))
    .sort();
  let n = 0;
  const written = [];
  for (const f of files) {
    const slug = slugify(f);
    const out = join(ADR_OUT, `${slug}.md`);
    const ok = processFile(`docs/adr/${f}`, out);
    if (!ok) continue;
    const raw = readFileSync(resolve(REPO_ROOT, `docs/adr/${f}`), 'utf8');
    const { title } = extractTitleAndBody(raw);
    written.push({ slug, title: title ?? slug });
    n += 1;
  }
  writeAdrIndex(written);
  return n;
}

const t0 = Date.now();
log(`${c.cyan}sync-docs${c.reset} ${c.dim}— copying ${relative(REPO_ROOT, DOCS_DIR)}/ into Starlight content${c.reset}`);
const topN = syncTopLevel();
const adrN = syncAdrs();
log('');
log(`${c.green}✓${c.reset} synced ${c.gold}${topN}${c.reset} operator doc${topN === 1 ? '' : 's'} + ${c.gold}${adrN}${c.reset} ADR${adrN === 1 ? '' : 's'} ${c.dim}in ${Date.now() - t0}ms${c.reset}`);
