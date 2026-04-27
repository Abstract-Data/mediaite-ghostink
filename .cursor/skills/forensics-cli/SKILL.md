# Forensics CLI Skill

## Capabilities

The `forensics` CLI runs a 4-stage pipeline: scrape → extract → analyze → report.

- Scrape: WordPress discovery, metadata, HTML fetch, dedup, archive
- Extract: lexical/content/probability features → parquet
- Analyze: change-point, time-series, drift, convergence, comparison
- Report: rendered analysis artifacts (Quarto + JSON)

Discoverability:

- `forensics --help` — top-level groups
- `forensics --output json commands` — full machine-readable catalog
- `docs/EXIT_CODES.md` — exit-code contract

## Workflows

### Fresh end-to-end run (no prior state)

1. `forensics preflight --strict` — exit 0 required
2. `forensics lock-preregistration --yes`
3. `forensics all`
4. Output: `data/reports/`

### Single-author refresh after corpus update

1. `forensics scrape --metadata --author SLUG`
2. `forensics extract --author SLUG`
3. `forensics analyze --author SLUG`

### Compare two authors without changing config

`forensics analyze --compare-pair TARGET,CONTROL`

### Migrating simhash fingerprints after D-01 (NFKC v2)

`forensics --output json dedup recompute-fingerprints`

Reads JSON: `.data.recomputed`, `.data.skipped`, `.data.errors`.

### Headless / agent invocation

Always pass `--output json --non-interactive`. Inspect exit code first:

- 0: success — parse `.data`
- 4: transient — retry with exponential backoff (start 5s)
- 5: conflict — read `.error.suggestion`, decide to skip or override
- 2/3: do not retry; surface to user

## Guardrails

- `forensics dashboard` and `forensics setup` are TUI-only. With `--non-interactive` they exit code 2 immediately. Never invoke from an agent.
- `forensics analyze` without `--exploratory` requires a locked preregistration. Lock first via `lock-preregistration --yes`.
- Shared-byline accounts (`mediaite`, `mediaite-staff`) are blocked unless `--include-shared-bylines`.
- All writes go under `data/`. Never write outside.

## Trigger conditions

| Symptom | Workflow |
|---|---|
| Fresh checkout, empty `data/` | Fresh end-to-end run |
| One author's articles changed | Single-author refresh |
| Need ad-hoc target↔control comparison | Compare two authors |
| Old simhashes (pre-D-01) in DB | Migrate simhash fingerprints |
| CI / scheduled job | Headless agent invocation |
