# Changelog

## [0.3.0] - 2026-04-20
**Model:** gpt-5-3-codex · **Eval impact:** not measured (prompt-only release)

### Added
- docs: codebase alignment (Repository, Article, ForensicsSettings, CLI wiring), article inclusion table, Pydantic extensions for POS features and embedding model_version, Parquet dict guidance, optional Repository query hook

### Changed
- chore: Status header uses `draft` per prompt-library contract; pipeline signature uses `ForensicsSettings`; embedding default references `AnalysisConfig` strings

## [0.2.0] - 2026-04-20
### Added
- feat: add POS bigram & phrase-pattern features (pos_patterns.py) — POS bigram frequency vectors, clause-initial entropy, dependency tree depth distribution

## [0.1.0] - 2026-04-20
### Added
- Initial spec: lexical, structural, content, productivity features, readability scores, sentence-transformer embeddings, Parquet storage.
