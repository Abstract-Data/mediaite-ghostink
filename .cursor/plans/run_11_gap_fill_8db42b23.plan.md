---
name: Run 11 gap fill
overview: Refactoring Run 11 is effectively complete in production code and tests; one script still violates the RF-DRY-001 pattern. This plan closes that gap with a minimal change and optional test hardening.
todos:
  - id: g1-migrate-script-db
    content: Replace hand-built data/articles.db default in scripts/migrate_feature_parquets.py with get_project_root() / DEFAULT_DB_RELATIVE from forensics.config
    status: completed
  - id: g2-optional-fixture-hash
    content: "(Optional) Add test: e2e fixture config.toml empty [analysis] yields same analysis config hash as default AnalysisConfig golden"
    status: completed
isProject: false
---

# Run 11 plan audit — gap fill

## Audit conclusion

| Plan task | Status |
|-----------|--------|
| TASK-1 (report docstring, no redundant `mkdir`, `_clean_feature_series`, `utc_archive_stamp`) | Done — e.g. [`src/forensics/models/report.py`](src/forensics/models/report.py), [`per_author.py`](src/forensics/analysis/orchestrator/per_author.py) line 168, [`src/forensics/utils/datetime.py`](src/forensics/utils/datetime.py) |
| TASK-2 (`settings.db_path` / `DEFAULT_DB_RELATIVE` DRY in `src/`) | Done — `src/` uses [`DEFAULT_DB_RELATIVE`](src/forensics/config/settings.py) + `get_project_root()`; `db_path` property matches `get_project_root() / DEFAULT_DB_RELATIVE` |
| TASK-3 (`AnalyzeRequest`, `run_analyze(request)`, [`analyze_options.py`](src/forensics/cli/analyze_options.py)) | Done |
| TASK-4 (nested `AnalysisConfig`, flat TOML, stable hash) | Done — [`src/forensics/config/analysis_settings.py`](src/forensics/config/analysis_settings.py), [`docs/adr/016-analysis-config-nesting.md`](docs/adr/016-analysis-config-nesting.md), golden in [`tests/unit/test_config_hash.py`](tests/unit/test_config_hash.py) (`test_default_analysis_config_model_hash_golden`) |
| TASK-5 (`from forensics.paths import AnalysisArtifactPaths`) | Done in `src/`, `tests/`, `scripts/bench_phase15.py`; shim remains at [`src/forensics/analysis/artifact_paths.py`](src/forensics/analysis/artifact_paths.py) |
| TASK-6 (verify, HANDOFF) | Documented in [`HANDOFF.md`](HANDOFF.md) per prior session |

**Single concrete gap:** [`scripts/migrate_feature_parquets.py`](scripts/migrate_feature_parquets.py) line 62 still uses `project_root / "data" / "articles.db"` instead of the shared constant, which the Run 11 inventory implied for “scripts similarly” hygiene and matches AGENTS guidance to avoid hand-built `data/` paths outside the canonical pattern.

**Optional (not required to “close” Run 11):** A test that loads [`tests/integration/fixtures/e2e/config.toml`](tests/integration/fixtures/e2e/config.toml) (empty `[analysis]`) and asserts `compute_analysis_config_hash(settings)` equals `compute_model_config_hash(AnalysisConfig(), ...)` would further lock “flat TOML → same digest as defaults.” The existing golden already pins default `AnalysisConfig` serialization.

---

## Implementation (after you approve Agent mode)

**TASK-G1 — DRY default DB in migration script (LOW risk, correctness / maintainability)**

- In [`scripts/migrate_feature_parquets.py`](scripts/migrate_feature_parquets.py): import `DEFAULT_DB_RELATIVE` from `forensics.config` (alongside existing `get_project_root`).
- Replace `db = args.articles_db or (project_root / "data" / "articles.db")` with `db = args.articles_db or (project_root / DEFAULT_DB_RELATIVE)`.
- Update the `--articles-db` help string to say default follows project layout (same wording family as CLI modules) if you want doc parity; optional one-line change.

**Validation**

- `uv run ruff check scripts/migrate_feature_parquets.py`
- No new tests strictly required; script is operational glue. If you add **TASK-G2** below, run full `uv run pytest tests/ -v`.

**TASK-G2 — Optional fixture hash regression (LOW)**

- Add a small test in [`tests/unit/test_config_hash.py`](tests/unit/test_config_hash.py) (or next to existing config-loading tests): `FORENSICS_CONFIG_FILE` → e2e fixture, `get_settings().cache_clear` pattern like other tests, assert analysis hash equals `compute_model_config_hash(AnalysisConfig(), length=16, round_trip=True)` and/or equals golden `81d550a7032fbe95`.

**GitNexus (before edit, after stage per repo rules)**

- `gitnexus_impact` on any **symbol** you touch if editing `src/`; for script-only G1, impact is trivial (script entrypoint only). Before commit: `gitnexus_detect_changes` on staged scope.

**HANDOFF**

- One short completion block if you treat this as a discrete session (per AGENTS.md).
