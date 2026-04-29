# v0.1.0 — Initial public release

First public release of the Mediaite writing forensics pipeline: a hybrid
scrape → extract → analyze → report system that searches for adoption signals
of AI-assisted writing in published news content. This release covers nine
days of intensive development (97 merged PRs, 2026-04-20 → 2026-04-29) and
ships the analysis dataset for the inaugural twelve-author study.

## Highlights

- End-to-end pipeline: scrape Mediaite via WordPress REST + Internet Archive,
  extract stylometric / readability / entropy / self-similarity / AI-marker
  features, run change-point detection (PELT + BOCPD with MAP-reset), embedding
  drift (sentence-transformers MiniLM-L6-v2 pinned to revision
  `c9745ed1...`), hypothesis testing with per-family Benjamini–Hochberg
  correction, and target/control comparison.
- Confirmatory analysis path with locked pre-registration thresholds
  (Phase-16 schema), corpus chain-of-custody fingerprint, and
  preregistration verification gate.
- Quarto book deliverable rendered to PDF (40 pages, 24 charts) with
  reproducibility dataset (~250 MB) shipped via Git LFS — see
  [docs/DATA.md](docs/DATA.md).

## Pipeline foundation

- feat: initial forensic pipeline scaffold + scraper fetcher (#1)
- Initial repository scaffolding (#8)
- docs: capture cloud dev environment bootstrap steps (#17)
- Add CI badges and quality section to README (#21)
- Add Phase 7–8 analysis, reporting, and notebook artifacts (#12)
- feat: land Phases 9, 10, and 11 — probability features, Ollama AI baseline
  generator, Typer CLI (#16)
- phase11-typer-cli-migration (#7, #20)
- phase11-1-refactor (#24)
- prompt13-refactor (#26)
- Notion code review and refactoring report implementation (#18)
- fix: address PR #18 code review follow-ups (#19)

## Scraping & data acquisition

- scraper: improve concurrency, streaming export, async JSONL (#23)
- feat(scrape): year-scoped WordPress posts (REST `after`/`before`) (#51)
- feat(scraper): WP REST `content.rendered` bulk extractor (#55)
- fix(scraper): restore `extract_article_text_from_rest` helper (#56)

## Feature extraction & analysis core (Phase 12–13)

- Phase 12 §1 — Survey mode: blind newsroom-wide AI-adoption analysis (#30)
- Phase 12 §2 — feat(tui): interactive setup wizard (#33)
- Phase 12 §4 — calibration suite (#31)
- Phase 12 §6 — report overhaul: survey dashboard, calibration notebook,
  evidence narrative (#34)
- Phase 12 §7 — operational QoL: validate + export CLI (#32)
- feat(ws5): pre-registration locking + permutation-based significance (#29)
- Ws3 preflight hardening (#35)
- phase12-refactor-all-phases (#22)
- docs(prompts): publish Phase 12 v0.2.0 alignment audit (#27)
- refactor(storage): migrate `read_features` to lazy scan (#37)
- refactor(cli): introduce `AnalyzeContext` dataclass (#41)
- refactor(analysis): consolidate `timeseries.py` (Phase 13 Unit 2) (#36)
- refactor(analysis): consolidate `changepoint.py` (Phase 13 Unit 1) (#38)
- refactor(features): decompose `extract_all_features` into focused helpers
  (#44)
- refactor(analysis): extract `load_drift_summary` to drift module (#45)
- refactor(scraper): Phase 13 Unit 6 — `ensure_repo`, `_persist_and_log`,
  `_full_pipeline` composition (#43)
- refactor(models): DRY `_accept_legacy_flat_payload` into `FAMILIES` loop
  (#40)
- test(analysis): unit tests for `compute_convergence_scores` (#39)
- test(features): unit tests for `_topic_entropy_lda` with mocked spaCy (#42)
- Invoke preregistration and add permutation config/tests (#47)
- docs(adr): consolidate naming to `ADR-NNN-*` scheme (#46)
- fix: carry forward phase11-1 TOCTOU + nullability fixes (#48)
- Phase 12–13: close gaps, raise coverage, add tests (#49)
- Phase 13 Run 7 remediation (27 steps, 7 phases) (#54, #61)

## Statistical hardening (Phases 14–16)

- Phase 14: review remediation (6th-run Apr 22, 2026 reports) (#50)
- Phase 15 Unit 1 — Foundations (Phase 0 + L) (#63)
- Phase 15 Unit 3 — convergence family scoring + Pipeline B percentile +
  CP-source dispatch (#65)
- Phase 15 Unit 4 — feature families registry (#64)
- Phase 15 Unit 6 — per-family BH (C2) + per-feature series cache (F2) (#66)
- Phase 15 C1 — drop KS test from default hypothesis battery (#68)
- Phase 15 F0 — PELT kernel swap RBF → L2 (#69)
- Phase 15 F1+F3 — bootstrap vectorization + constant-signal early exit (#72)
- Phase 15 G2+G3 — per-feature parallel + embedding audit (within #80)
- Phase 15 Phase A — BOCPD MAP-reset detection rule + Student-t predictive
  (#70)
- Phase 15 Phase D — shared-byline filter (model field + heuristic +
  qualification exclusion) (#71)
- Phase 15 J1 — section column derivation from URL (#73)
- Phase 15 J2 — exclude advertorial / syndicated sections from survey +
  features (#76)
- Phase 15 J3 — section-level descriptive report (newsroom-wide diagnostic)
  (#75)
- Phase 15 J4 — per-author section-mix time series (#74)
- Phase 15 J5 — verdict: BORDERLINE (deferred per gate spec) (#83)
- Phase 15 J6+J7 — section contrast + CLI (within #80)
- Phase 15 H1+H2+H3 — reference fixtures + parallel parity + coverage bump
  (#81)
- Phase 15 K1+K2+K3 — reporting integration: families + section mix +
  section contrast (#78)
- Phase 15 K4+K5+K6 — reporting integration: CP twin-panel + section
  profile + Pipeline B diagnostics (#79)
- Phase 15 fix — migration JOINs `articles.db` for section backfill (#82)
- Phase 15 I1–I4 — docs sweep: ARCHITECTURE + RUNBOOK + GUARDRAILS + HANDOFF
  (#77)
- Phase 15 TUI progress (#57)
- Phase 16 refactor — revision pin + corpus_custody schema v2 (#62)

## Diagnostics, gates & calibration

- Phase 15 E1+E2 — Pipeline B diagnostics: DEBUG component logging +
  missing-artifact WARNING (#67)
- Phase 15 Fix-G — drift-only persistence channel for convergence windows
  (#87)
- Fix-F — lower `PIPELINE_SCORE_PASS_THRESHOLD` 0.5 → 0.3 (#86)
- Fix #5 — convergence-ratio ceiling: regroup single-member families
  (FAMILY_COUNT 8→6) (#84)
- Fix #4 — Pipeline B percentile mode (math-floor confirmed) (#85)
- Phase 17 direction/volume diagnostics + golden-case fixtures (#94)

## Report deliverable (notebooks → Quarto book → PDF)

- Quarto-Plotly — enable interactive chart rendering in book HTML (#93)
- Report-A — fill notebook 05 with real change-point findings (#90)
- Report-B — fill notebook 06 with real Pipeline B / drift findings (#91)
- Report-C — fill notebook 07 with FDR-significance findings (#88)
- Report-D — fill notebook 08 with target/control contrast (#89)
- Report-E — fill notebook 09 with executive summary (#92)

## Final calibration + ship (this release)

- CLI agent-readiness sweep (#95)
- Output deslop pass — drop noisy stdout from text-mode runs (#96)
- Stat-consistency mod — `pipeline_b_mode` default flip (legacy → percentile)
  + `config_hash` gate (#97)
- Add per-author manifest shards and fix notebook/PDF layout for
  confirmatory report (#98)
- Publish reproducibility dataset (~250 MB) via Git LFS — analysis +
  features + embeddings (this commit; see
  [docs/DATA.md](docs/DATA.md))

## Reproducibility

The full source corpus (`articles.db`, ~78 K Mediaite article texts) is
omitted from public redistribution. The deterministic scraper and pinned
embedding-model revision (`c9745ed1d9f207416be6d2e6f8de32d1f16199bf`) make
the corpus reconstructable from scratch:

```bash
uv sync
uv run forensics scrape           # rebuild data/articles.db
uv run forensics extract          # rebuild data/features/, data/embeddings/
uv run forensics analyze --max-workers 4
uv run forensics --yes report --format pdf --verify
```

Article IDs are derived from canonical URL hashes
(`forensics.utils.hashing`), so end-to-end reproduction yields stable IDs
across machines. The `config_hash` recorded in
`data/analysis/run_metadata.json` and the locked thresholds in
`data/preregistration/preregistration_lock.json` define the exact analysis
parameters used to produce the v0.1.0 PDF.

## Citation

Cite the v0.1.0 GitHub release tag together with the `config_hash` from
`data/analysis/run_metadata.json` and the `recorded_at` timestamp in
`data/preregistration/preregistration_lock.json`.

> A Zenodo DOI for archival distribution is **TBD**. Once archived,
> replace the citation block in [docs/DATA.md](docs/DATA.md) with the
> DOI and date of archival.

---

**Full Changelog**: https://github.com/Abstract-Data/mediaite-ghostink/commits/v0.1.0
