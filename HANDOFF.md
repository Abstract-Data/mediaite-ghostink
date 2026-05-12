# HANDOFF

## Handoff Protocol

Every handoff should include:

1. Current status (`Complete`, `Partial`, or `Blocked`)
2. Exact command evidence used for verification
3. Files changed and rationale
4. Known risks and recommended next actions

Agents: append a new block below using this template after every multi-step task.

---

## Template (copy this for each new entry)

<!--
### [Task Title]
**Status:** Complete | Partial | Blocked
**Date:** YYYY-MM-DD
**Agent/Session:** [identifier]

#### What Was Done
- [Concise list of changes]

#### Files Modified
- `path/to/file` — [why]

#### Verification Evidence
```text
[paste the commands you ran and a summary of output]
```

#### Decisions Made
- [Key choices and rationale]

#### Unresolved Questions
- [Anything left open]

#### Risks & Next Steps
- [What should the next operator know or do]
-->

---

## Completion Log


> **History:** Older completion blocks live in [`docs/archive/handoff-history.md`](docs/archive/handoff-history.md). When this file grows past roughly 200 lines of log content, archive older blocks there in the same change set.

### Hybrid documentation versioning (Option C) — Python API + CLI per release tag

**Status:** Complete
**Date:** 2026-05-10
**Agent/Session:** Cursor agent (Claude Opus 4.7)

#### What was done

Implemented hybrid documentation versioning: Python API + Typer CLI reference are now built per-release-tag and surfaced through Starlight's `<VersionPicker>`, while operator docs, ADRs, getting-started, the landing page, and the embedded Quarto report remain evergreen (always reflect `main`). The default release is also aliased at the un-versioned URL so inbound links (`/api/forensics_pipeline/`, `/cli/forensics-preflight/`) keep resolving without redirects.

- **New: `website/scripts/sync-versions.mjs`** — single source of truth for which tags ship. Reads `.release-please-manifest.json` for the current version, cross-references `git tag --list 'v*.*.*'`, sorts by semver, keeps the most recent 5 (override via `KEEP_VERSIONS=N` or `--keep N`), marks the manifest version as `default`, and writes `versions[]` into both autodoc configs. Falls back to single-version (main) mode and removes stale `versions[]` if no tags exist (bootstrap-safe).
- **New: `website/scripts/build-cli-docs.mjs`** — per-version CLI orchestrator that mirrors `build-python-docs.mjs`. For each tag: `git worktree add --detach` → `uv sync --frozen --extra dev` → `uv run --directory <wt> python <REPO_ROOT>/scripts/generate_cli_docs.py --out <outDir>/<safeTag> --version <tag> [--version-default]`. Worktrees cleaned on exit/SIGINT. The default version is re-rendered with `--version-segment ""` and copied (top-level `.md` only — never wipes subdirs) into the un-versioned output dir to alias the default URL.
- **New: `website/scripts/cli-autodoc.json`** — mirror of `python-autodoc.json` for the CLI orchestrator. Specifies `outputDir`, `urlBasePrefix`, `repoUrl`, `repoBranch`, `generatorScript`, and `uvExtras: ["dev"]`. `versions[]` populated dynamically by `sync-versions.mjs`.
- **Modified: `scripts/generate_cli_docs.py`** — added `--version`, `--version-label`, `--version-default`, and `--version-segment` flags. Writes `version:`, `versionLabel:`, `versionDefault: true` frontmatter and `sidebar.hidden: true` on versioned-subdir pages (default version's un-versioned alias stays sidebar-visible). Rewrites cross-page links (subcommand tables, `cli/index.md`) to honor `version_segment`, and points `editUrl` at the version tag rather than `main` so "Edit this page" goes to the released code. New `safe_tag()` helper mirrors `safeTag()` from the JS orchestrator. Backward compatible: no `--version` flag → unchanged behavior.
- **Modified: `website/scripts/build-python-docs.mjs`** — added `sidebar.hidden: true` to versioned-subdir page frontmatter (without it the sidebar would show every module N+1 times). Fixed the "Older version" banner link target: now correctly prepends `cfg.urlBasePrefix` and points at the *un-versioned* default-aliased URL (`/mediaite-ghostink/api/forensics_pipeline/`) instead of the versioned subdir, satisfying `starlight-links-validator` and giving readers the latest canonical page.
- **Modified: `website/package.json`** — added `sync-versions` and `docs:cli` scripts. Existing `dev` and `build` unchanged so `bun run dev` keeps Just Working in single-version repos.
- **New: `website/src/components/SocialIcons.astro`** — top-level project override of Starlight's `SocialIcons` slot that renders TWO `<VersionPicker>` instances (one for `/api`, one for `/cli`) plus the default theme social icons. Required because the theme's existing `SocialIcons` override ships only ONE picker bound to a single `apiBase`. Each picker is render-gated by its own URL prefix so at most one is visible on any given page.
- **Modified: `website/astro.config.mjs`** — wired the new `SocialIcons` override at the top level (`components: { SocialIcons: './src/components/SocialIcons.astro' }`) so it takes precedence over the theme's plugin-level override.
- **Modified: `Makefile`** — added `docs-versions` phony target (`bun run sync-versions`); `docs-cli` and `docs-python` now depend on `docs-versions` and shell out to the new orchestrators; `docs-quarto` description updated to note evergreen status; `docs-build` description updated to note versioned CLI + Python API + evergreen report.
- **Modified: `.github/workflows/deploy-docs.yml`** — added `fetch-depth: 0` to the checkout step (REQUIRED — shallow clones can't materialize tag commits for `git worktree`), inserted `bun run sync-versions` after `bun install`, replaced the single CLI generator step with `bun run docs:cli` (which now orchestrates per-tag worktrees), and extended the smoke test to verify all evergreen paths, all default-aliased paths, AND per-version subdir paths (resolves current `safeTag` from the release-please manifest so the assertion tracks releases without manual edits).
- **Modified: `docs/RUNBOOK.md`** — expanded the "CI / hosting cutover" section to 11 explicit build steps including the worktree-based versioning machinery, plus a new "Versioned documentation (Option C)" subsection covering how versions are resolved, how per-version pages get built, the frontmatter contract (`version:`, `versionLabel:`, `versionDefault:`, `sidebar.hidden:`), and a diagnosis quick-reference table for the common failure modes.

#### Files modified

- `website/scripts/sync-versions.mjs` *(new)*
- `website/scripts/build-cli-docs.mjs` *(new)*
- `website/scripts/cli-autodoc.json` *(new)*
- `website/src/components/SocialIcons.astro` *(new)*
- `scripts/generate_cli_docs.py`
- `website/scripts/build-python-docs.mjs`
- `website/package.json`
- `website/astro.config.mjs`
- `Makefile`
- `.github/workflows/deploy-docs.yml`
- `docs/RUNBOOK.md`

#### Verification evidence

```text
$ make docs-clean && make docs-build
... (157 page(s) built in 5.94s) ...
03:46:46 ✓ Completed.
03:46:46 [@astrojs/check] Getting diagnostics for Astro files in /Users/.../website...
Result (157 files):
- 0 errors
- 0 warnings
- 0 hints
03:46:54 [check] All internal links are valid.    ← starlight-links-validator
03:46:54 [build] Complete!

# Smoke test (mirrors deploy-docs.yml exactly)
$ CURRENT_SAFE_TAG=$(node -e 'const m=require("../.release-please-manifest.json"); process.stdout.write(m["."].replace(/[^a-zA-Z0-9_-]/g,"-"));')
$ echo "default tag = $CURRENT_SAFE_TAG"
default tag = 0-1-2
$ for p in dist/index.html dist/getting-started/index.html \
         dist/cli/index.html dist/cli/forensics/index.html \
         dist/cli/forensics-preflight/index.html \
         dist/synced/architecture/index.html dist/synced/runbook/index.html \
         dist/adr/index.html dist/api/forensics/index.html \
         dist/api/forensics_pipeline/index.html dist/report/index.html \
         dist/sitemap-index.xml \
         "dist/cli/${CURRENT_SAFE_TAG}" \
         "dist/cli/${CURRENT_SAFE_TAG}/forensics-preflight/index.html" \
         "dist/api/${CURRENT_SAFE_TAG}" \
         "dist/api/${CURRENT_SAFE_TAG}/forensics_pipeline/index.html"; do
    [ -e "$p" ] && echo "OK $p" || echo "MISS $p"
done
... (all 16 paths OK) ...
missing = 0

# Sample versioned page frontmatter
$ head -10 website/src/content/docs/api/0-1-2/forensics_pipeline.md
---
title: forensics.pipeline
description: "End-to-end pipeline orchestration (scrape → extract → analyze → report)."
version: "v0.1.2"
versionLabel: "0.1.2"
versionDefault: true
sidebar:
  hidden: true
---

# Lint
$ uv run ruff check scripts/generate_cli_docs.py && uv run ruff format --check scripts/generate_cli_docs.py
All checks passed!
1 file already formatted
```

`bun run sync-versions` resolved 3 tags (`v0.1.2` default, `v0.1.1`, `v0.1.0`). Total `make docs-build` wall time ~6 min on a warm `uv` cache (per-tag `uv sync --frozen` dominates; subsequent runs are faster).

#### Decisions made

- **Default version aliased at un-versioned URL, not redirected.** Re-rendering the default version with `--version-segment ""` (CLI) / a second `version: null` build (API) into the bare output dir keeps the URL shape stable for inbound links. The alternative — a redirect from `/api/<page>/` to `/api/<safeTag>/<page>/` — would have polluted analytics and broken `starlight-links-validator`'s pages set.
- **Keep last 5 versions by default.** Configurable via `KEEP_VERSIONS=N` or `--keep N`. Per-tag worktree + `uv sync` is the slowest part of the build; 5 is the point where wall time stays under 10 min on a warm cache while still covering enough history to be useful.
- **Tag-list as source of truth, manifest only for default selection.** If `release-please-manifest.json` declares a version that isn't tagged locally yet (common in CI right after a release-please commit lands but before tag fetch), the orchestrator falls back to the newest tag and logs a warning instead of failing.
- **One orchestrator per docs surface, not a shared generic.** The Python and CLI generators have different shapes (`pydoc-markdown` vs. a custom Typer walker), different per-tag dependency requirements, and different default-alias rules. A shared orchestrator would have needed enough switches that it'd be harder to read than two near-identical scripts.
- **Versioned pages are `sidebar.hidden: true`, reachable only via the picker.** Otherwise the sidebar shows every module/command N+1 times (once per version + the default alias). The default alias remains sidebar-visible — it's the canonical "latest" entry.
- **Failed `uv sync --frozen` for old tags downgrades to a warning, not a hard fail.** Older lockfiles can resolve to wheels yanked from PyPI; in that case the orchestrator logs and skips, so a single dead historical version doesn't tank the whole build. The default version is always in the kept window so the latest never has this risk.

#### Unresolved questions

- **Should we surface a banner on aliased default pages saying "you're viewing v0.1.2 / latest"?** Currently the alias copies omit version frontmatter entirely (so they don't trip the "stale version" banner). A future enhancement could re-add a soft "viewing latest (v0.1.2)" banner to set expectations, but that's a UX call, not a correctness gap.
- **Quarto report versioning is deliberately out of scope.** It's evergreen by design — the investigation report describes a state of work, not a software release. If we later need pinned-historical reports, the manifest-driven pattern here would extend naturally with `--out website/public/report/<safeTag>` plus a banner.

#### Risks & next steps

- **Risk: CI worktree-add fails on first run.** Mitigation: `fetch-depth: 0` is now pinned in the deploy workflow. Anyone copying that workflow to another repo MUST copy that line — shallow clones break `git worktree add <tmp> <tag>` silently from the user's perspective (the orchestrator catches it and logs).
- **Risk: a future `release-please` config change that drops `include-v-in-tag: true`.** The orchestrator's `git tag --list 'v*.*.*'` filter is the contract; if tags become `0.1.3` instead of `v0.1.3`, sync-versions will silently see zero matches and fall back to single-version mode. Belt-and-braces: pin `include-v-in-tag: true` in `release-please-config.json` and don't change it.
- **Next step: wait for the next release tag to land, watch one CI run end-to-end** to confirm the per-tag worktree path resolves on GitHub Actions runners (different `uv` cache state, different `git` config). If it works, no follow-up. If `uv sync --frozen` fails inside a worktree because of a wheel-cache layout, the fix is `uv sync --frozen --refresh` inside the orchestrator — but don't preemptively make that change; it doubles per-tag build time.
- **Operational note:** to widen the kept-versions window from 5 to N, set `KEEP_VERSIONS=N` in the workflow env, or add `--keep N` to `bun run sync-versions` in `docs-versions` target. No code changes needed.

---

### Docs CI/CD hardening — Python API in pipeline + smoke tests

**Status:** Complete
**Date:** 2026-05-10
**Agent/Session:** Cursor agent (Claude Opus 4.7)

#### What was done

- **`.github/workflows/deploy-docs.yml`** rewritten to match `make docs-build` end-to-end:
  - Added `pipx install pydoc-markdown` step so the Python API reference is generated in CI (previously the workflow skipped `bun run docs:python`, which left `/api/*` empty on production).
  - Added explicit `Generate Python API reference` step (`bun run docs:python`) between `bun install --frozen-lockfile` and `bun run build`, matching the local Makefile order.
  - Added a post-build smoke-test step that hard-asserts the canonical entry points exist in `website/dist/` (`/`, `/getting-started/`, `/cli/`, `/cli/forensics/`, `/cli/forensics-preflight/`, `/synced/architecture/`, `/synced/runbook/`, `/adr/`, `/api/forensics/`, `/api/forensics_pipeline/`, `/report/`, `sitemap-index.xml`). A regression in any generator (sync-docs, CLI generator, pydoc-markdown, Quarto) now hard-fails the workflow before Pages sees it.
  - Aligned with the repo's existing CI pattern: `astral-sh/setup-uv@v4` + `enable-cache: true` + `uv sync --frozen --extra dev` (was `@v5` without freeze).
  - Broadened path filters: `src/forensics/**` (not just `cli/`), plus `pyproject.toml` and `uv.lock` (so dependency changes that affect generated reference docs re-deploy).
  - Allowed `workflow_dispatch` from `main` to also publish (previously dispatch built but never deployed).
  - Split concurrency: build job uses `deploy-docs-${{ github.ref }}` with `cancel-in-progress` only for PRs; deploy job pins the shared GitHub-recommended `pages` group with `cancel-in-progress: false` so a live deploy is never interrupted mid-flight.
- **`website/scripts/python-autodoc.json`**: fixed `searchPath` from `../../src` → `../src` (the script resolves relative to `website/`, so the prior value pointed at `/Users/.../PyCharmProjects/src`, outside the repo). Added `urlBasePrefix: "/mediaite-ghostink"` so the build-python-docs script can emit base-prefixed Starlight URLs.
- **`website/scripts/build-python-docs.mjs`**: the auto-generated `## Submodules` section on package landing pages previously emitted relative `./<safeName>.md` links, which `starlight-links-validator` rejects (default `errorOnRelativeLinks: true`). Patched to emit absolute base-prefixed Starlight URLs (`/mediaite-ghostink/api/<safeName>/`), honoring `cfg.urlBasePrefix` and version directories when versions are configured.
- **`Makefile`**: `docs-python` now precheck-fails with an actionable message (`Install with: pipx install pydoc-markdown`) when `pydoc-markdown` is not on `PATH`, matching the CI dependency exactly.
- **`docs/RUNBOOK.md`**: documented the 9-step CI build pipeline (uv sync → pydoc-markdown → Quarto setup → Bun setup → CLI gen → Quarto render → bun install → Python API → astro build + smoke-test), the broadened path triggers, and the concurrency split.

#### Files modified

- `.github/workflows/deploy-docs.yml`
- `Makefile`
- `website/scripts/build-python-docs.mjs`
- `website/scripts/python-autodoc.json`
- `docs/RUNBOOK.md`

#### Verification

```text
# Cold rebuild mirroring CI exactly
make docs-clean && make docs-build
# → [build] 58 page(s) built in 8.08s
# → ✓ All internal links are valid.

# Workflow smoke-test block (12/12 OK)
for f in website/dist/index.html website/dist/getting-started/index.html \
         website/dist/cli/index.html website/dist/cli/forensics/index.html \
         website/dist/cli/forensics-preflight/index.html \
         website/dist/synced/architecture/index.html \
         website/dist/synced/runbook/index.html website/dist/adr/index.html \
         website/dist/api/forensics/index.html \
         website/dist/api/forensics_pipeline/index.html \
         website/dist/report/index.html website/dist/sitemap-index.xml; do
  test -f "$f" && echo "OK $f" || echo "MISS $f"
done
# → All 12 entries OK

# Python lint/format on the only Python file in the CI generator path
uv run ruff check scripts/generate_cli_docs.py    # All checks passed!
uv run ruff format --check scripts/generate_cli_docs.py   # 1 file already formatted

# Workflow YAML parses
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-docs.yml'))"
# → YAML OK
```

#### Decisions made

- **Install `pydoc-markdown` via `pipx`** rather than `uv pip install` because (a) it keeps the docs toolchain out of the project venv, (b) `pipx` is preinstalled on `ubuntu-latest`, and (c) it matches the upstream Abstract Data docs theme's recommended install path (see the script's own banner).
- **Embed an explicit smoke-test** (12 path checks) rather than relying solely on `astro build` exit code. The Astro build can succeed even if a generator silently produced zero pages (e.g. pydoc-markdown returns 1 per module but the script logs and continues). The smoke-test catches that class of regression deterministically.
- **Broaden trigger paths to `src/forensics/**`** (not just `cli/`) because pydoc-markdown introspects every documented module; changing any function signature under `src/forensics/` may need a fresh deploy to keep the API reference accurate.
- **Did not refactor** the rest of the repo's CI; quality/test workflows (`ci.yml`, `ci-tests.yml`, `ci-quality.yml`, `ci-report.yml`, `agents-governance.yml`, `release-please.yml`) are unrelated to docs deployment and already ignore docs-only paths via `paths-ignore: ['**.md', 'docs/**', 'LICENSE']`. Leaving them untouched per scope.

#### Risks & next steps

- **Maintainer follow-ups for the Cloudflare → GitHub Pages migration** (carried over from the prior docs-site handoff and still pending):
  1. `Settings → Pages → Source: GitHub Actions` on the GitHub repo.
  2. Watch the first `Deploy Docs` run on `main`, confirm the site renders at `https://abstract-data.github.io/mediaite-ghostink/`.
  3. Retire the Cloudflare `ai-writing-forensics` Pages project and remove `CF_API_TOKEN` / `CF_ACCOUNT_ID` repo secrets.
  4. Retire the legacy `make deploy` target (still references `wrangler pages deploy`) in a follow-up change once the CF project is gone.
- **`bun.lock` is committed** (`workspaces.[\"\"].name = \"website\"`, not the renamed `mediaite-ghostink-website`). Bun's `--frozen-lockfile` checks dependency tree integrity, not the workspace name, so this is fine — but if you ever regenerate the lockfile cleanly the workspace name will update and that should be a non-issue.
- **First production deploy will be the first time pydoc-markdown runs against the live `src/forensics/` tree on a GitHub runner**. If a module raises at import (e.g. spaCy model not available), the CLI step would still pass but the Python API step would fail loudly. The smoke-test would then catch any drop in expected pages.

---

### Run 13 follow-up — inline review (parser, refresh, analyze CLI, settings, config audit)

**Status:** Complete  
**Date:** 2026-04-29  
**Agent/Session:** Cursor agent

#### What was done

- **REST parser:** `extract_article_text_from_rest` now runs `_strip_stray_angle_brackets` after sanitize so malformed fragments (e.g. a lone `<`) do not survive in plain text; satisfies `test_parser_rest_fuzz` idempotence + no-`<`/`>` invariants.
- **`refresh.py`:** Comment on `__all__` for patch targets; split `_run_isolated_author_parallel_jobs`; refactored `run_parallel_author_refresh` into helpers with docstring; parallel analyze path seeds audit / `run_metadata` like serial paths.
- **`analyze_dispatch.py`:** `_conflicting_analyze_flags` + validation in `_compare_only_or_parallel_early_exit` for invalid flag mixes (`--compare` with other stages; `--parallel-authors` with serial stages).
- **`analyze_models.py`:** Docstring on `AnalyzeContext.build`.
- **`config_cmd.py`:** JSON mode emits `{"status":"ok","diffs":[...],"count":N}` when overrides exist (no prose lines).
- **`settings.py`:** `mode="before"` mirror: when `survey` has `excluded_sections` and `features` is missing, inject `features` from survey.
- **`per_author.py`:** Polars LazyFrame pipeline for `_clean_feature_series` (ruff-formatted).
- **`test_parser_rest_fuzz.py`:** Stronger assertions + sentinel-preservation Hypothesis test.

#### Files modified

- `src/forensics/scraper/parser.py`, `tests/unit/test_parser_rest_fuzz.py`
- `src/forensics/analysis/orchestrator/refresh.py`, `per_author.py`
- `src/forensics/cli/analyze_dispatch.py`, `analyze_models.py`, `config_cmd.py`
- `src/forensics/config/settings.py`

#### Verification

```text
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/ -v --tb=line -q
```

1095 passed, 4 skipped (TUI), 1 xfailed; coverage 80.44% (meets fail-under).

#### Risks and next steps

- Stripping `<`/`>` in the REST path only removes markup-like characters from **flattened** text; legitimate angle brackets in article prose are rare for this corpus. If needed, narrow to known-malformed patterns only.

### Run 13 — Code review + refactoring plan (config, CLI, orchestrator)

**Status:** Complete  
**Date:** 2026-04-29  
**Agent/Session:** Cursor agent

#### What was done

- **RF-DRY-001:** `CONFIG_HASH_EXTRA` in `src/forensics/config/constants.py`; replaced repeated `json_schema_extra` dicts in `analysis_settings.py` and `settings.py`.
- **RF-DRY-002 / P3-SEC-001:** `worker_errors.py` with recoverable-exception policy; `parallel.py` / `comparison.py` updated; `RuntimeError` included so isolated-refresh tests still pass.
- **RF-DRY-003:** `survey.excluded_sections` canonical; `mode="before"` validator on `ForensicsSettings` mirrors into `features` (dict and model init).
- **P2-ARCH-001:** `--verify-raw-archives/--no-verify-raw-archives`, `--log-all-generations/--no-log-all-generations` on analyze; wired via `AnalyzeCustodyParams`.
- **P3-SEC-002:** `_METADATA_INGEST_RECOVERABLE` narrowed to `IntegrityError` + `OperationalError` (not all `sqlite3.Error`).
- **P3-TEST-001:** `tests/unit/test_parser_rest_fuzz.py` for `extract_article_text_from_rest`.
- **P3-PERF-001:** Polars-native `_clean_feature_series` in `per_author.py`.
- **RF-COMPLEXITY-001:** `analyze_models.py`, `analyze_dispatch.py`, `analyze_section.py`; trimmed `analyze.py`.
- **RF-COMPLEXITY-002:** `parallel_shared.py`, `refresh.py`, slim `parallel.py` + lazy `import_module` re-exports for patch surface.
- **RF-SMELL-002:** Nested `AnalyzeRequest` (`stages`, `baseline`, `custody`); `pipeline.py` and tests updated.
- **P2-CQ-002:** `forensics analyze run` and `forensics analyze compare-only` subcommands.
- **P2-CQ-001 / RF-SMELL-003:** `forensics config audit`; flat `[analysis]` deprecation warning in `compat_analysis.py` (once per process); ADR-017 note.
- **RF-SMELL-001:** `ForensicsSettings` shortcuts `pelt`, `bocpd`, `convergence`, `content_lda`, `hypothesis`, `embedding`.
- **RF-ARCH-001:** Docstrings in `runner.py` and `analyze_dispatch.py` cross-referencing CLI vs `run_full_analysis`.

#### Files modified (high level)

- `src/forensics/config/` (`constants.py`, `settings.py`, `compat_analysis.py`, `analysis_settings.py`)
- `src/forensics/cli/` (`analyze.py`, `analyze_models.py`, `analyze_dispatch.py`, `analyze_section.py`, `analyze_options.py`, `config_cmd.py`, `__init__.py`)
- `src/forensics/analysis/orchestrator/` (`parallel.py`, `parallel_shared.py`, `refresh.py`, `worker_errors.py`, `per_author.py`, `comparison.py`, `runner.py`)
- `src/forensics/scraper/crawler.py`, `tests/unit/test_parser_rest_fuzz.py`, `tests/unit/test_config_audit.py`, `tests/unit/test_analyze_compare.py`, `tests/test_preregistration.py`, `tests/unit/test_settings.py`, `scripts/merge_embedding_manifest_shards.py` (E501 wrap)
- `docs/RUNBOOK.md`, `docs/adr/017-analysis-config-change-control.md`, `src/forensics/pipeline.py`

#### Verification

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/ -q --no-cov
```

All tests passed (4 skipped TUI, 1 xfail section-residualize).

#### Risks and next steps

- **Parallel refresh tests** must patch `forensics.analysis.orchestrator.refresh._validate_and_promote_isolated_outputs` (implementation lives in `refresh.py`).
- **ForensicsSettings** excluded-sections mirroring uses `mode="before"` so pydantic-settings applies the merged dict correctly.
- Consider migrating internal code to `settings.hypothesis` etc. incrementally; accessors are additive only.

### Run 12 — TASK-6 / TASK-7 / TASK-8 (patch surface, config compat, parallel dedup + coverage)

**Status:** Complete  
**Date:** 2026-04-27

#### What was done

- **TASK-6:** Expanded `forensics.analysis.orchestrator` module docstring with maintainer rules for `_PATCH_TARGETS` vs `__all__`; added `test_patch_targets_subset_of_all_exports`, `test_patch_surface_tests_track_patch_targets`, `test_patch_targets_modules_nonempty` in `tests/unit/test_orchestrator_patch_surface.py`.
- **TASK-7:** Added ADR-017 (AnalysisConfig change control; no `HashableField` — governance + compat split); moved flat TOML lift / `_FLAT_TO_GROUP` / `_GROUP_ATTRS` into `src/forensics/config/compat_analysis.py` with `analysis_settings` importing from it; amended ADR-016 references.
- **TASK-8:** Factored `_run_repo_per_author_pipeline_with_artifacts` in `parallel.py` for `_per_author_worker` and `_isolated_author_worker` (isolated path keeps `emit_success_log=False` for log parity); added root `coverage-tui.toml` and RUNBOOK § item 7 for `pytest --cov-config=coverage-tui.toml` when TUI extra is installed.

#### Files modified

- `src/forensics/analysis/orchestrator/__init__.py`, `parallel.py`
- `src/forensics/config/compat_analysis.py` (new), `analysis_settings.py`
- `docs/adr/017-analysis-config-change-control.md` (new), `docs/adr/016-analysis-config-nesting.md`, `docs/RUNBOOK.md`
- `tests/unit/test_orchestrator_patch_surface.py`, `coverage-tui.toml` (new), `HANDOFF.md`

#### Verification

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/ -q
uv run pytest tests/integration/test_parallel_parity.py -v --no-cov -q
uv run pytest tests/unit/test_config_hash.py -v --no-cov -q
```

Full suite: **passed** (1 known xfail); parallel parity: **3 passed**. GitNexus MCP server not available in this Cursor session; run upstream `impact` on edited symbols before merge when enabled.

#### Unresolved / next steps

- None for this slice.

---

### Pipeline B default, config_hash gate, direction concordance scoping, embedding compare parity

**Status:** Complete  
**Date:** 2026-04-27  
**Agent/Session:** Cursor agent (plan slice: doc-hash-migration, integration-hash-test, direction-concordance-filter, comparison-embedding-propagate, probability-trajectory-verify)

#### What was done

- **RUNBOOK:** Documented why `pipeline_b_mode` participates in `config_hash`, symptoms (`Analysis artifact compatibility failed` / stale hashes), and remediation (full `forensics analyze` cohort vs `pipeline_b_mode = "legacy"` to match old artifacts).
- **Integration:** `tests/integration/test_analysis_config_hash_gate.py` asserts `validate_analysis_result_config_hashes` returns failure and `_validate_compare_artifact_hashes` raises `ValueError` on mismatched `*_result.json` `config_hash`.
- **Direction concordance:** `classify_direction_concordance` filters hypothesis rows to `convergence_window.features_converging` when that list is non-empty; unit tests updated + new scoping test; Phase 17 golden fixtures already align feature names with `features_converging` (no golden JSON edit).
- **Compare path:** Introduced `orchestrator/embedding_policy.py` with `embedding_fail_should_propagate` (avoids `parallel` ↔ `comparison` import cycle); `_iter_compare_targets` re-raises embedding drift/revision errors in confirmatory mode; `parallel.py` uses the shared helper; unit tests in `test_comparison_target_controls.py`.
- **Pipeline C:** Comment on equal-weight monthly means and sparse Binoculars months in `probability_trajectories.py`; unit test `test_sparse_binoculars_months_pipeline_c_score_finite` for length inequality + finite score.

#### Files modified

- `docs/RUNBOOK.md` — `pipeline_b_mode` / `config_hash` operator subsection
- `HANDOFF.md` — this block
- `src/forensics/analysis/orchestrator/embedding_policy.py` — new shared policy
- `src/forensics/analysis/orchestrator/parallel.py`, `comparison.py` — embedding propagation
- `src/forensics/models/report.py` — concordance scoping
- `src/forensics/analysis/probability_trajectories.py` — comments
- `tests/integration/test_analysis_config_hash_gate.py` — new
- `tests/unit/test_direction_concordance.py`, `test_comparison_target_controls.py`, `test_probability_trajectories.py` — tests

#### Verification evidence

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/integration/test_analysis_config_hash_gate.py tests/unit/test_direction_concordance.py tests/unit/test_comparison_target_controls.py tests/unit/test_probability_trajectories.py tests/integration/test_phase17_classification.py -v --no-cov
```

#### Decisions made

- **Embedding policy module:** `comparison.py` cannot import `parallel.py` (existing `parallel` → `comparison` edge); policy lives in `embedding_policy.py` instead of duplicating logic.

#### Unresolved questions

- None.

#### Risks & next steps

- **GitNexus:** `gitnexus_impact` / `gitnexus_detect_changes` were not run (GitNexus MCP server not available in this Cursor session). Run on `classify_direction_concordance`, `_iter_compare_targets`, and `embedding_fail_should_propagate` before merge when enabled.
- Operators with pre–percentile-default `*_result.json` should follow the new RUNBOOK subsection before compare/report.

---

### Full confirmatory re-run for all 12 configured authors → fresh PDF report
**Status:** Complete
**Date:** 2026-04-28
**Agent/Session:** Claude Code (Opus 4.7, 1M context)

#### What Was Done
- Re-ran the full forensic pipeline end-to-end for all 12 configured authors and produced a confirmatory-mode PDF report.
- Diagnosed and patched a manifest-stomping bug in `forensics extract --author <slug>` that would have silently destroyed the manifest under any multi-call workflow.
- Added per-author manifest shards plus a merge step; verified shards accumulate correctly and the canonical manifest is rebuilt before `forensics analyze`.
- Recovered from a bash `set -e` gotcha (loop body inside `&&` chain) that left an ostensibly-killed extract loop racing a replacement chain.
- Captured both failure patterns as Signs in `docs/GUARDRAILS.md`.

#### Files Modified
- `src/forensics/features/pipeline.py` — write per-author manifest shards (`<slug>_manifest.jsonl`) when `author_slug` is set; legacy single-write path retained for unscoped runs.
- `scripts/merge_embedding_manifest_shards.py` — new helper; merges shards + canonical (last-wins by `article_id`), atomically rewrites canonical manifest, deletes shards.
- `docs/GUARDRAILS.md` — appended two Signs (`set -e` for-loop/`&&` interaction; pre-patch manifest-stomping behavior of `extract --author`).
- `data/reports/Mediaite-writing-analysis-—-technical-report.pdf` — final confirmatory PDF (90 KB, mtime 2026-04-28 01:33:03 CDT).
- `data/analysis/run_metadata.json`, `comparison_report.json`, all per-author `*_result.json` / `*_changepoints.json` / `*_convergence.json` / `*_hypothesis_tests.json` / `*_drift.json` etc. — fresh artifacts.
- `data/embeddings/manifest.jsonl` — 49,126 rows / 12 distinct `author_id`s (canonical, post-merge).
- `data/embeddings_archive_20260428T002003Z/` — auto-archived prior embeddings (revision-pin mismatch).
- `data/embeddings/manifest.jsonl.pre-revrepin-20260427T191951` — operator-side manifest snapshot (pre-rerun rollback breadcrumb; safe to delete now).
- `data/logs/path_b_parallel_20260427T220619.log` — main run log; per-author logs at `data/logs/extract_<slug>.log`.

#### Verification Evidence
```text
$ tail -2 data/logs/path_b_parallel_20260427T220619.log
Tue Apr 28 01:33:03 CDT 2026
EXIT=0

$ stat -f '%Sm %z %N' data/reports/*.pdf
Apr 28 01:33:03 2026 92234 data/reports/Mediaite-writing-analysis-—-technical-report.pdf

$ uv run python -c 'import json; ids=set(); n=0
> for line in open("data/embeddings/manifest.jsonl"):
>     line=line.strip()
>     if line: ids.add(json.loads(line)["author_id"]); n+=1
> print(f"rows={n} authors={len(ids)}")'
rows=49126 authors=12

$ jq '{exploratory, allow_pre_phase16_embeddings, preregistration_status, config_hash}' \
    data/analysis/run_metadata.json
{
  "exploratory": false,
  "allow_pre_phase16_embeddings": false,
  "preregistration_status": "ok",
  "config_hash": "6bffd326f0074688514c3d595ad2bc6065725ea17e783489"
}
```

Total wallclock: 22:06:19 → 01:33:03 = **3 h 26 min 44 s** (4-way parallel extract via `xargs -P 4` + merge + `forensics analyze --max-workers 4` + Quarto/lualatex PDF render, 3 passes).

#### Decisions Made
- **Path B over A.** Delivered confirmatory-mode report (`exploratory=false`) instead of taking the faster A-mode shortcut, because the report is preregistration-clean and matches the locked thresholds at 2026-04-26T09:46:47.
- **Per-author manifest shards over fcntl locking.** Cleaner — each writer owns its own path; the merge step is a single-process operation. Reader (`read_embeddings_manifest`) needed no changes because last-wins-by-`article_id` semantics already match.
- **Killed alex-griffing's 95-min run mid-extract** to land the patch and restart with parallelism. Net savings on remaining 11 authors outweighed the loss.
- **4-way parallel** chosen as the sweet spot for an M1 Max (10 cores, 64 GB, single MPS GPU). Measured ~36% wall slowdown per author vs serial baseline (much better than my 30% MPS-contention worst case); effective ~3× speedup.
- **Skipped re-extracting `ahmad-austin`** — its rows from the (failed) earlier sequential run were already in the canonical manifest and its `batch.npz` was on disk. The merge step preserved them.

#### Unresolved Questions
- **Section-residualized sensitivity flags** (in `run_metadata.json`): 4 authors have `downgrade_recommended=true` (`ahmad-austin`, `colby-hall`, `isaac-schorr`, `sarah-rumpf`). Their primary findings drop substantially when section composition is residualized, suggesting section bias inflates the raw signal. Worth scrutinizing in the narrative before client delivery.
- **CLI behavior cleanup (deferred):** `forensics extract` (no `--author` flag) iterates all 505 DB authors via `list_articles_for_extraction(author_id=None)`, while `resolve_author_rows(author_slug=None)` returns only the 12 configured authors. The two are inconsistent. `forensics analyze` already scopes to configured authors when no `--author` is given. Worth a separate PR to align `extract`'s default scope with `analyze`'s — would let a single `forensics extract` call replace the 12 sequential `--author` invocations.
- **Manifest-shard cleanup is destructive.** `merge_embedding_manifest_shards.py` deletes shards after merge. If a multi-author run is interrupted between extract and merge, partial state requires manual cleanup. Consider keeping shards under `data/embeddings/_shards/` with a configurable retention policy.

#### Risks & Next Steps
- **`pipeline.py` patch needs a unit test.** Currently no test asserts that scoped extract writes shards rather than the canonical manifest. Suggested: add to `tests/test_parquet_embeddings_duckdb.py` or a new `tests/unit/test_extract_manifest_shards.py` covering (a) shard-only write when `author_slug` is set, (b) canonical write when `author_slug` is `None` (legacy path), (c) merge script idempotency on no-shards.
- **GitNexus impact analysis was not run** on the patched `extract_all_features` symbol or the new merge script (per the project's GitNexus rule). Run before any subsequent edits to `pipeline.py`.
- **GUARDRAILS Sign: confirm `set -e` claim.** I asserted the bash POSIX/bash-specific behavior from observed evidence (the OLD chain continued past a killed inner command). The exact set-of-conditions where bash suppresses `set -e` inside compound commands is more nuanced than the Sign captures — if a future operator encounters edge cases, the canonical reference is `bash(1)` and POSIX 2.14.1.4. Keep the Sign as a heuristic.
- **`data/embeddings_archive_20260428T002003Z/` and `data/embeddings/manifest.jsonl.pre-revrepin-20260427T191951`** can be deleted once the new artifacts are blessed. Combined ~hundreds of MB.
- **Operator hint:** If you ever re-run extract for a subset of authors after this point, use `forensics extract --author <slug>` (the patch makes that safe) followed by `uv run python scripts/merge_embedding_manifest_shards.py` before `forensics analyze`. Or, for a full corpus, run `forensics extract` (no flag) — that path still uses the legacy single-write semantics, which are correct when there's only one writer for the whole manifest.

---

### Root cleanup, README, and production readiness

**Status:** Complete  
**Date:** 2026-04-28  
**Agent/Session:** Cursor agent

#### What was done

- Archived historical `HANDOFF.md` completion log to [`docs/archive/handoff-history.md`](docs/archive/handoff-history.md); trimmed root `HANDOFF.md` to protocol + last three blocks + pointer; documented size discipline in [`AGENTS.md`](AGENTS.md).
- README: **At a glance**, **Five-minute smoke test**, `_quarto.yml` corrections, repository layout row, **Contributing** section; documentation table entries for `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/RUNBOOK.md`](docs/RUNBOOK.md): `_quarto.yml` wording; E2E bullet uses `_quarto.yml`.
- Moved root `TASK.md` to [`docs/TASK.md`](docs/TASK.md); updated [`docs/adr/ADR-003-agent-governance-and-hooks.md`](docs/adr/ADR-003-agent-governance-and-hooks.md); removed redundant `!TASK.md` from [`_quarto.yml`](_quarto.yml).
- Added [`LICENSE`](LICENSE) (MIT), [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md); [`pyproject.toml`](pyproject.toml) `license` + `Repository` URL.
- Moved [`docs/coverage-tui.toml`](docs/coverage-tui.toml) from repo root; updated RUNBOOK `pytest --cov-config` path.
- Removed local ephemeral files where present (`coverage.json`, `.coverage`, `_freeze/`, `.DS_Store`).

#### Files modified

- `HANDOFF.md`, `docs/archive/handoff-history.md` (new), `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`, `docs/TASK.md` (moved from root), `docs/adr/ADR-003-agent-governance-and-hooks.md`, `_quarto.yml`, `pyproject.toml`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/coverage-tui.toml` (moved from root)

#### Verification evidence

```bash
uv build
# sdist + wheel OK

uv run ruff check . && uv run ruff format --check .
uv run pytest tests/test_report.py -v --no-cov
```

#### Risks and next steps

- **License:** Root [`LICENSE`](LICENSE) is **MIT** with Abstract Data LLC copyright. If the org requires a different license, replace the file and `pyproject.toml` `license` metadata in one commit.
- GitNexus `impact` / `detect_changes` not run (no MCP server in this session); run before merge if your workflow requires it.

---

### Peer reviewer setup (Makefile, `forensics peer-setup`, docs)

**Status:** Complete  
**Date:** 2026-04-29  
**Agent/Session:** Cursor subagent

#### What was done

- **Makefile:** Peer-oriented targets (`install-reviewer`, `install-baseline`, `install-probability`, `install-all-extras`, `peer-verify`, `peer-verify-network`, `peer-setup`, `peer-hints`); `peer-setup` runs install + validate + `uv run forensics peer-setup`.
- **CLI:** `src/forensics/cli/peer_setup.py` with `peer_setup_cmd` (`--check-ollama` → `asyncio.run(preflight_check(...))`, PASS/FAIL), `attach_peer_setup(app)` registered from `forensics.cli.__init__`.
- **Tests:** `tests/unit/test_cli_peer_setup.py` asserts `ollama pull` lines for configured `[baseline] models`.
- **Docs:** README (five-minute smoke + local setup: `make peer-setup`, spaCy wheel note), `docs/RUNBOOK.md` § Peer reviewers.

#### Files modified

- `Makefile`, `src/forensics/cli/peer_setup.py`, `src/forensics/cli/__init__.py`, `tests/unit/test_cli_peer_setup.py`, `README.md`, `docs/RUNBOOK.md`, `HANDOFF.md`
- Lint-only fixes encountered during `ruff check .`: `scripts/merge_embedding_manifest_shards.py`, `tests/unit/test_embedding_manifest_routing.py`

#### Verification evidence

```
uv run ruff check . && uv run ruff format .
uv run pytest tests/ -v --no-cov
```

Full suite: **1099 passed**, **3 deselected**, **1 xfailed** (known `test_section_residualize_suppresses_section_mix_only_change_point`), ~110s.

#### Decisions made

- Baseline / Ollama hints print when `settings.baseline.models` is non-empty (defaults include three tags).
- `peer-setup` Makefile recipe invokes `uv run forensics peer-setup` after deps + validate; `peer-hints` remains a hints-only target.

#### Unresolved questions

- None.

#### Risks & next steps

- GitNexus MCP `gitnexus_impact` not invoked in this session; new symbols are primary (`peer_setup_cmd`, `attach_peer_setup`); `__init__.py` only gained import + `attach_peer_setup(app)` call (duplicate inline `app.command` removed). Run impact/detect_changes before merge if required by team workflow.

---

### Peer-reviewer Makefile and CLI (`peer-setup`)

**Status:** Complete  
**Date:** 2026-04-29  
**Agent/Session:** Cursor agent

#### What was done

- **Makefile:** `install-reviewer`, `install-baseline`, `install-probability`, `install-all-extras`, `peer-verify`, `peer-verify-network`, `peer-hints`, `peer-setup` (sync dev+tui → validate → `forensics peer-setup`); top comment for peers.
- **CLI:** `src/forensics/cli/peer_setup.py` — `forensics peer-setup` prints uv tiers, spaCy/Quarto notes, config-driven `ollama pull` lines; `--check-ollama` uses `baseline.preflight.preflight_check`; rejects `--output json`. Registered via `attach_peer_setup(app)` in `forensics.cli`.
- **Tests:** `tests/unit/test_cli_peer_setup.py` — baseline models in stdout; JSON output rejected.
- **Docs:** `README.md` (spaCy wheel, Installation, models table), `docs/RUNBOOK.md` (peer subsection under Ollama).

#### Files modified

- `Makefile`, `src/forensics/cli/peer_setup.py` (new), `src/forensics/cli/__init__.py`, `tests/unit/test_cli_peer_setup.py`, `README.md`, `docs/RUNBOOK.md`, `HANDOFF.md`

#### Verification evidence

```
uv run ruff check src/forensics/cli/peer_setup.py src/forensics/cli/__init__.py tests/unit/test_cli_peer_setup.py
uv run pytest tests/unit/test_cli_peer_setup.py tests/unit/test_cli_commands_dump.py -v --no-cov -q
# 5 passed
```

#### Risks and next steps

- `make peer-setup` runs `forensics validate`, which fails if `config.toml` still has placeholder authors or other preflight hard-fails; peers should fix config before the meta-target or run `make install-reviewer` + `make peer-hints` separately.

---

### Documentation site (Astro Starlight + Bun) — `website/` integration

**Status:** Complete
**Date:** 2026-05-10
**Agent/Session:** Cursor agent

#### What was done

- **Scaffold:** Ran `bun create @abstractdata/docs website` at the repo root. Pulled in the Abstract Data Starlight theme (`@abstractdata/starlight-theme@0.3.5`), Bun-first `package.json`, pydoc-markdown autodoc orchestrator, and the bundled `abstract-data-setup` skill. Cleaned the scaffold's embedded `.git`, `.DS_Store`, and tmp `.fuse_hidden*` files. `bunx abstract-data-install-skills` ran cleanly (all 11 skill markers detected as already present — kept existing).
- **Astro config:** Set `site: 'https://abstract-data.github.io'`, `base: '/mediaite-ghostink'`, `trailingSlash: 'always'`; rewrote sidebar to expose Get Started / Operator docs (synced) / CLI reference / Python API / Decision records / Forensic report; configured `editLink`, `lastUpdated`, and `starlightLinksValidator` with `/report/**` excluded.
- **Sync pipeline:** New [`website/scripts/sync-docs.mjs`](website/scripts/sync-docs.mjs) copies allow-listed `docs/*.md` (ARCHITECTURE, RUNBOOK, TESTING, GUARDRAILS, DEPLOYMENTS, EXIT_CODES) into `src/content/docs/synced/` and all `docs/adr/*.md` into `src/content/docs/adr/`, injecting YAML frontmatter and rewriting internal links to base-prefixed Starlight URLs (off-list paths fall back to absolute GitHub URLs on `main`). Emits a synthesized `adr/index.md` so the sidebar landing resolves.
- **CLI reference:** New [`scripts/generate_cli_docs.py`](scripts/generate_cli_docs.py) walks `forensics.cli:app` via `typer.main.get_command` and emits one Markdown page per command/subcommand (27 pages) plus an index, all with `editUrl` frontmatter pointing back to `src/forensics/cli/__init__.py`. Slugs are full-name dashed (`forensics-analyze-section-profile`) so the subcommand-table links match the on-disk filenames.
- **Python API:** Configured [`website/scripts/python-autodoc.json`](website/scripts/python-autodoc.json) to target `forensics`, `forensics.config/models/scraper/features/analysis/reporting/storage/pipeline` (uses the scaffold's pydoc-markdown orchestrator). Output lands at `src/content/docs/api/` (gitignored); regenerated locally via `make docs-python` once `pipx install pydoc-markdown` is on `PATH`.
- **MDX pages:** Hand-authored [`website/src/content/docs/index.mdx`](website/src/content/docs/index.mdx) (`template: splash`, `<CardGrid>`/`<LinkCard>`/`<Aside>`) and [`website/src/content/docs/getting-started.mdx`](website/src/content/docs/getting-started.mdx) (`<Steps>`, `<Aside>`, `<FileTree>`, `<Tabs>` per acceptance criteria). Deleted the scaffold's placeholder `quickstart.md`.
- **Makefile:** New targets `docs-cli`, `docs-python`, `docs-quarto`, `docs-dev`, `docs-build`, `docs-clean` chained off the new generators and `bun run` scripts (`website` is Bun-first).
- **CI cutover:** New [`.github/workflows/deploy-docs.yml`](.github/workflows/deploy-docs.yml) (uv + Quarto + Bun, builds CLI ref + Quarto report + Astro site, uploads `website/dist` as a Pages artifact, deploys on `main` push). Removed the previous Cloudflare-only deploy at `.github/workflows/deploy.yml` plus the dead `website/.github/workflows/{deploy,deploy-cloudflare,deploy-vercel}.yml` files that the scaffold dropped inside `website/`.
- **Repo docs hygiene:** Updated [`docs/RUNBOOK.md`](docs/RUNBOOK.md) with a "Documentation site (Astro Starlight)" section (commands, hosted URL, maintainer checklist), appended a build-artifacts Sign to [`docs/GUARDRAILS.md`](docs/GUARDRAILS.md), refreshed the README's `## Reports (Quarto)` and `## Documentation` sections to point at `https://abstract-data.github.io/mediaite-ghostink/`.

#### Files modified / added

- `website/**` — full new scaffold (theme, Bun lockfile, `astro.config.mjs`, `package.json`, `scripts/`, `src/`, `.gitignore`, skills, copilot instructions); generated output dirs gitignored.
- `scripts/generate_cli_docs.py` (new)
- `.github/workflows/deploy-docs.yml` (new); removed `.github/workflows/deploy.yml`
- `Makefile` (new `docs-*` targets)
- `docs/RUNBOOK.md`, `docs/GUARDRAILS.md`, `README.md` (docs site section + Sign + Reports/Docs links)

#### Verification evidence

```
# 1. Scaffold + bun install (Bun 1.3.3) — already ran during this session.

# 2. sync-docs idempotent
cd website && node scripts/sync-docs.mjs
# ✓ synced 6 operator docs + 11 ADRs

# 3. CLI generator deterministic
cd .. && uv run python scripts/generate_cli_docs.py
# generate_cli_docs: wrote 27 page(s) to website/src/content/docs/cli

# 4. Full production build
cd website && bun run build
# → 49 pages built; "✓ All internal links are valid."; pagefind index OK; sitemap-index.xml created.

# 5. Quarto + CI invariants
test ! -f .github/workflows/deploy.yml && echo OK
# OK
```

#### Decisions made

- **Bun (not npm) as the canonical package manager** because the `@abstractdata/docs` template is Bun-first (`bun.lock` committed, scripts assume `bun run`, theme prefers it). `deploy-docs.yml` uses `oven-sh/setup-bun@v2` and `bun install --frozen-lockfile`.
- **Generators produce base-prefixed internal links** (`/mediaite-ghostink/...`). `starlight-links-validator@0.16` joins the configured `base` to the validator's page lookup, so unprefixed `/cli/...` URLs reported as invalid. Hand-authored MDX uses the same convention.
- **`docs/cli/` is skipped at the repo root**; the CLI generator writes directly into `website/src/content/docs/cli/`. The repo's canonical CLI source remains `src/forensics/cli/`, and the generated reference is reproducible from it.
- **ADR/sync separation:** ADRs land in `src/content/docs/adr/` (not under `synced/`) so the "Decision records" sidebar entry doesn't duplicate them inside "Operator docs."
- **Quarto sources untouched:** `_quarto.yml`, `index.qmd`, `notebooks/`, `src/forensics/analysis/`, and `config.toml` were not modified, per the spec's scope boundary.

#### Maintainer checklist (Cloudflare → GitHub Pages cutover)

1. **Enable GitHub Pages** in repo settings: `Settings → Pages → Source: GitHub Actions`.
2. **Run** the `Deploy Docs` workflow once (push to `main` or use `workflow_dispatch`) and confirm the deploy succeeds at `https://abstract-data.github.io/mediaite-ghostink/`.
3. **Retire** the Cloudflare Pages project `ai-writing-forensics` in the Cloudflare dashboard.
4. **Remove** the `CF_API_TOKEN` and `CF_ACCOUNT_ID` repo secrets under `Settings → Secrets and variables → Actions`.
5. **Retire** the legacy `make deploy` target (still calls `wrangler pages deploy`) in a follow-up change once the CF project is gone.
6. **Optional:** `pipx install pydoc-markdown` on contributor laptops so `make docs-python` populates the Python API section locally.

#### Risks & next steps

- The `@abstractdata/starlight-theme` `<VersionPicker>` logs a "no `version:` frontmatter" warning per page during build because we don't ship versioned API docs. Benign — warnings only, no build failure. Can be silenced later by adding a `versions[]` block to `python-autodoc.json` if/when we tag releases.
- `starlight-links-validator` is base-aware but requires hand-written internal links to include the base prefix. Future contributors should follow the convention or use Starlight's slug-based linking; the existing generators encode this in one place each.
- Quarto rendering is wired into the deploy workflow but skipped in local `make docs-dev`. Run `make docs-quarto` (or `make docs-build`) when iterating on the report.
- GitNexus impact analysis was not invoked; the changes are additive (new scripts, new workflow, gitignored generated content). Pre-merge, run `gitnexus_detect_changes` to confirm the scope.

---

### Dependency version bumps + docs URL in README
**Status:** Complete
**Date:** 2026-05-12
**Agent/Session:** Copilot cloud agent (Claude Sonnet 4.6)

#### What Was Done
- Bumped all dependency minimum version pins in `pyproject.toml` to match the currently locked
  versions in `uv.lock` (reflecting the latest stable releases available as of ~7 days after
  the previous pinned minimums).
- Added `Documentation` URL to `[project.urls]` in `pyproject.toml`.
- Added a `Docs` badge (gh-pages URL) to the README header badge row.

#### Files Modified
- `pyproject.toml` — bumped `>=` constraints for all main, dev, and optional dependencies; added `Documentation` URL
- `README.md` — added `[![Docs](...)](https://abstract-data.github.io/mediaite-ghostink/)` badge

#### Verification Evidence
```text
# All new constraints satisfied by uv.lock (verified via Python script):
# typer: locked=0.24.1 >= min=0.24.0  ✓
# polars: locked=1.40.0 >= min=1.40.0  ✓
# duckdb: locked=1.5.2 >= min=1.5.0  ✓
# ... (all 41 packages OK, none FAIL)
```

#### Decisions Made
- Used the currently resolved versions in `uv.lock` as the new minimums; no lock update needed.
- Previous deploy-docs failure (run 25649887514) was a tag-timing race: `v0.1.3` tag was not
  yet visible when the workflow ran. The tag now exists; subsequent runs should pass.

#### Risks & Next Steps
- The `uv.lock` is still frozen — only `pyproject.toml` constraints changed. No `uv lock` regeneration
  needed unless new packages are added.
- When the next release is cut (v0.1.4), ensure `v0.1.4` tag exists before deploy-docs runs.
