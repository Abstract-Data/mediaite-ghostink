# Article labels (optional, M-17)

Human auditors may append rows to `article_labels.jsonl` using the
`ArticleLabel` schema in `src/forensics/models/labels.py`.

- **Format:** one JSON object per line (JSONL), UTF-8.
- **Empty corpus:** an empty file or only comments is valid; the forensic
  report should state that precision/recall of stylometric gates are unknown
  without labeled articles.
- **Loader contract:** downstream tooling may read this directory in a future
  phase; the main pipeline currently does not gate analysis on labels.

See `article_labels.seed.jsonl` for an empty starter file.
