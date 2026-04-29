# Data Availability

This repository ships the **derived analysis artifacts** for the Mediaite
writing forensic study. The full source corpus (~78,000 Mediaite article
texts) is omitted from public redistribution; reproducibility runs from the
locked feature artifacts forward, or end-to-end from the deterministic scraper.

## Tracked here (~250 MB total via Git LFS)

| Path | Size | Contents |
|---|---|---|
| `data/embeddings/manifest.jsonl` | ~18 MB | sentence-transformer manifest pinned to revision `c9745ed1d9f207416be6d2e6f8de32d1f16199bf`; one row per article (49,126 rows / 12 author_ids in the canonical bundle) |
| `data/embeddings/<slug>/batch.npz` | ~95 MB total | packed embedding batches per author (configured + control) |
| `data/features/<slug>.parquet` | ~99 MB total | stylometric + structural features per article, per author |
| `data/analysis/<slug>_*.json` | small | per-author change-points, drift, hypothesis tests, convergence windows, imputation stats, bursts, UMAP, baseline curves, results |
| `data/analysis/<slug>_centroids.npz` | small | monthly drift centroids per author |
| `data/analysis/<slug>_timeseries.parquet` | small | per-author time series for plots |
| `data/analysis/comparison_report.json` | ~73 KB | target ↔ control comparisons |
| `data/analysis/run_metadata.json` | <1 KB | run id, `config_hash`, preregistration status, authors in run |
| `data/analysis/corpus_custody.json` | <1 KB | corpus chain-of-custody fingerprint (schema v2) |
| `data/analysis/sensitivity/section_residualized/**` | small | section-residualized sensitivity outputs |
| `data/preregistration/preregistration_lock.json` | <1 KB | locked thresholds (Phase-16 schema) |
| `data/preregistration/amendment_*.md` | KB scale | preregistration amendments |
| `data/provenance/`, `data/bench/`, `data/analysis/provenance/` | KB scale | reproducibility metadata + bench baselines |

Routing details live in [`.gitattributes`](../.gitattributes). The relaxation
rules that keep these files out of the blanket `data/*` ignore live in
[`.gitignore`](../.gitignore).

## Omitted from public distribution

| Path | Reason |
|---|---|
| `data/articles.db` (~661 MB) | Source corpus — full text of ~77,947 Mediaite articles. Not redistributed for copyright reasons (Mediaite published news). |
| `data/articles.jsonl` (~250 MB) | JSONL export of the same corpus; same rationale. |
| `data/raw/` | Per-article raw HTML; archived to `data/raw/<year>.tar.gz` on retention rotation. |
| `data/embeddings_archive_*` | Auto-generated archives created when the embedding model revision changes. Transient. |
| `data/logs/`, `data/reports/` | Operational logs and rendered outputs. The PDF rebuilds from `quarto render --execute --to pdf` against the artifacts in this directory. |
| `data/probability/`, `data/ai_baseline/`, `data/calibration/`, `data/survey/`, `data/pipeline/` | Side-pipeline outputs not used by the published report; regenerable from the corpus. |

## Reproducing the corpus

The scraper is deterministic given the configured author list and date range
(see `config.toml`). Article IDs are derived from canonical URL hashes (see
`forensics.utils.hashing`) so end-to-end reproduction yields stable IDs across
machines.

```bash
uv sync
uv run forensics scrape           # rebuilds data/articles.db from Mediaite (network)
uv run forensics extract          # rebuilds data/features/, data/embeddings/
uv run forensics analyze --max-workers 4
uv run forensics --yes report --format pdf --verify
```

Re-running the scraper from scratch is bandwidth-bound (~78K articles via
the Mediaite + Internet Archive paths). The resulting `articles.db` should
match the corpus hash recorded in `data/analysis/corpus_custody.json` modulo
articles that have since been edited or deleted upstream — the chain-of-custody
record captures the canonical fingerprint at time of original analysis.

## Cloning with LFS

Anyone fetching this repository needs `git-lfs` installed:

```bash
brew install git-lfs   # or: apt install git-lfs / port install git-lfs
git lfs install
git clone https://github.com/Abstract-Data/mediaite-ghostink
# LFS objects (~250 MB) download as part of the clone
```

To clone code only (skip LFS payload):

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/Abstract-Data/mediaite-ghostink
```

LFS pointers will then sit in place of the actual `.parquet` / `.npz` /
manifest files; fetch on demand via `git lfs pull` or `git lfs fetch <ref>`.

## Citing this dataset

Cite the GitHub release commit hash along with the `config_hash` recorded
in `data/analysis/run_metadata.json`. The locked preregistration thresholds
in `data/preregistration/preregistration_lock.json` are fixed at the
`recorded_at` timestamp inside that file.

> A Zenodo DOI for archival distribution is **TBD**. Once the dataset is
> archived to a long-term store (Zenodo / OSF / institutional repository),
> replace this paragraph with the DOI and date of archival.
