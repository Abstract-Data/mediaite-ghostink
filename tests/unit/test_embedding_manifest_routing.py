"""Unit tests for embedding manifest path routing in ``extract_all_features``.

Verifies the critical behavior introduced to fix the multi-author parallel-extract
workflow: when ``author_slug`` is supplied, the manifest is written to a per-author
shard (later merged by ``scripts/merge_embedding_manifest_shards.py``); when no slug
is given, the canonical ``manifest.jsonl`` is updated directly.

Also covers ``merge_embedding_manifest_shards.main()`` dry-run semantics: a true
dry-run must not write *or* delete any files.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from forensics.config.settings import AnalysisConfig, ForensicsSettings, ReportConfig, ScrapingConfig
from forensics.models.features import EmbeddingRecord
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.parquet import read_embeddings_manifest, write_embeddings_manifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).parents[2] / "scripts"


def _load_merge_script():
    """Import ``scripts/merge_embedding_manifest_shards.py`` as a module."""
    spec = importlib.util.spec_from_file_location(
        "merge_embedding_manifest_shards",
        _SCRIPTS_DIR / "merge_embedding_manifest_shards.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("merge_embedding_manifest_shards", mod)
    spec.loader.exec_module(mod)
    return mod


def _settings() -> ForensicsSettings:
    return ForensicsSettings(
        authors=[],
        scraping=ScrapingConfig(),
        analysis=AnalysisConfig(),
        report=ReportConfig(output_format="html"),
    )


def _mock_repo_ctx() -> MagicMock:
    """Context-manager mock that returns itself on ``__enter__``."""
    repo = MagicMock()
    repo.__enter__ = MagicMock(return_value=repo)
    repo.__exit__ = MagicMock(return_value=False)
    repo.list_articles_for_extraction.return_value = [MagicMock()]
    return repo


def _mock_author(slug: str = "john-doe", author_id: str = "a1") -> MagicMock:
    au = MagicMock()
    au.id = author_id
    au.slug = slug
    return au


# ---------------------------------------------------------------------------
# extract_all_features — manifest path routing
# ---------------------------------------------------------------------------


def test_scoped_extract_writes_manifest_shard(tmp_path: Path) -> None:
    """``author_slug`` set → ``write_embeddings_manifest`` targets the shard path."""
    from forensics.features import pipeline as pl

    db_path = tmp_path / "a.db"
    slug = "john-doe"
    expected_paths = AnalysisArtifactPaths.from_project(tmp_path, db_path)
    expected_shard = expected_paths.embedding_manifest_shard(slug)

    with (
        patch("forensics.features.pipeline._archive_embeddings_if_mismatch"),
        patch("forensics.features.pipeline.Repository", return_value=_mock_repo_ctx()),
        patch(
            "forensics.features.pipeline.resolve_author_rows",
            return_value=[_mock_author(slug, "a1")],
        ),
        patch(
            "forensics.features.pipeline._filter_excluded_sections",
            side_effect=lambda articles, _: articles,
        ),
        patch(
            "forensics.features.pipeline._group_articles_by_author",
            return_value={"a1": [MagicMock()]},
        ),
        patch("forensics.features.pipeline._load_spacy_model", return_value=None),
        patch(
            "forensics.features.pipeline._run_author_batches",
            return_value=(1, 0, []),
        ),
        patch("forensics.features.pipeline.write_embeddings_manifest") as mock_write,
    ):
        pl.extract_all_features(
            db_path,
            _settings(),
            author_slug=slug,
            project_root=tmp_path,
            show_rich_progress=False,
        )

    mock_write.assert_called_once_with([], expected_shard)


def test_unscoped_extract_writes_canonical_manifest(tmp_path: Path) -> None:
    """``author_slug`` None → ``write_embeddings_manifest`` targets the canonical path."""
    from forensics.features import pipeline as pl

    db_path = tmp_path / "a.db"
    expected_paths = AnalysisArtifactPaths.from_project(tmp_path, db_path)
    expected_canonical = expected_paths.embedding_manifest()

    with (
        patch("forensics.features.pipeline._archive_embeddings_if_mismatch"),
        patch("forensics.features.pipeline.Repository", return_value=_mock_repo_ctx()),
        patch(
            "forensics.features.pipeline.resolve_author_rows",
            return_value=[_mock_author()],
        ),
        patch(
            "forensics.features.pipeline._filter_excluded_sections",
            side_effect=lambda articles, _: articles,
        ),
        patch(
            "forensics.features.pipeline._group_articles_by_author",
            return_value={"a1": [MagicMock()]},
        ),
        patch("forensics.features.pipeline._load_spacy_model", return_value=None),
        patch(
            "forensics.features.pipeline._run_author_batches",
            return_value=(1, 0, []),
        ),
        patch("forensics.features.pipeline.write_embeddings_manifest") as mock_write,
    ):
        pl.extract_all_features(
            db_path,
            _settings(),
            author_slug=None,
            project_root=tmp_path,
            show_rich_progress=False,
        )

    mock_write.assert_called_once_with([], expected_canonical)


def test_skip_embeddings_does_not_write_manifest(tmp_path: Path) -> None:
    """``skip_embeddings=True`` must never call ``write_embeddings_manifest``."""
    from forensics.features import pipeline as pl

    db_path = tmp_path / "a.db"

    with (
        patch("forensics.features.pipeline.Repository", return_value=_mock_repo_ctx()),
        patch(
            "forensics.features.pipeline.resolve_author_rows",
            return_value=[_mock_author()],
        ),
        patch(
            "forensics.features.pipeline._filter_excluded_sections",
            side_effect=lambda articles, _: articles,
        ),
        patch(
            "forensics.features.pipeline._group_articles_by_author",
            return_value={"a1": [MagicMock()]},
        ),
        patch("forensics.features.pipeline._load_spacy_model", return_value=None),
        patch(
            "forensics.features.pipeline._run_author_batches",
            return_value=(1, 0, []),
        ),
        patch("forensics.features.pipeline.write_embeddings_manifest") as mock_write,
    ):
        pl.extract_all_features(
            db_path,
            _settings(),
            author_slug="any-slug",
            skip_embeddings=True,
            project_root=tmp_path,
            show_rich_progress=False,
        )

    mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# merge_embedding_manifest_shards.main() — dry-run semantics
# ---------------------------------------------------------------------------


def _make_shard(emb_dir: Path, slug: str) -> None:
    """Write a minimal shard file into ``emb_dir``."""
    rec = _make_embedding_record(f"art-{slug}", slug, f"{slug}/batch.npz")
    shard = emb_dir / f"{slug}_manifest.jsonl"
    write_embeddings_manifest([rec], shard)


def _make_embedding_record(article_id: str, author_id: str, embedding_path: str) -> EmbeddingRecord:
    """Construct a minimal ``EmbeddingRecord`` for use in tests."""
    return EmbeddingRecord(
        article_id=article_id,
        author_id=author_id,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        model_name="all-MiniLM-L6-v2",
        model_version="1.0",
        embedding_path=embedding_path,
        embedding_dim=384,
    )


def test_merge_dry_run_does_not_write_canonical(tmp_path: Path) -> None:
    """``main(dry_run=True)`` must not create or modify the canonical manifest."""
    merge = _load_merge_script()

    emb_dir = tmp_path / "data" / "embeddings"
    emb_dir.mkdir(parents=True)
    _make_shard(emb_dir, "alice")

    canonical = emb_dir / "manifest.jsonl"
    assert not canonical.exists(), "canonical must not exist before dry-run"

    with patch.object(merge, "get_project_root", return_value=tmp_path):
        rc = merge.main(dry_run=True)

    assert rc == 0
    assert not canonical.exists(), "dry-run must not write the canonical manifest"
    # Shard must still be present
    assert (emb_dir / "alice_manifest.jsonl").exists(), "dry-run must not delete shards"


def test_merge_wet_run_writes_canonical_and_removes_shards(tmp_path: Path) -> None:
    """Normal (non-dry-run) merge writes the canonical manifest and removes shards."""
    merge = _load_merge_script()

    emb_dir = tmp_path / "data" / "embeddings"
    emb_dir.mkdir(parents=True)
    _make_shard(emb_dir, "bob")

    canonical = emb_dir / "manifest.jsonl"

    with patch.object(merge, "get_project_root", return_value=tmp_path):
        rc = merge.main(dry_run=False)

    assert rc == 0
    assert canonical.exists(), "wet run must write the canonical manifest"
    records = read_embeddings_manifest(canonical)
    assert any(r.article_id == "art-bob" for r in records)
    assert not (emb_dir / "bob_manifest.jsonl").exists(), "wet run must delete shards"


def test_merge_dry_run_preserves_existing_canonical(tmp_path: Path) -> None:
    """Existing canonical is not mutated by a dry-run even when shards are present."""
    merge = _load_merge_script()

    emb_dir = tmp_path / "data" / "embeddings"
    emb_dir.mkdir(parents=True)

    # Write an existing canonical with one record
    existing_rec = _make_embedding_record("art-existing", "existing", "existing/batch.npz")
    canonical = emb_dir / "manifest.jsonl"
    write_embeddings_manifest([existing_rec], canonical)
    original_bytes = canonical.read_bytes()

    _make_shard(emb_dir, "charlie")

    with patch.object(merge, "get_project_root", return_value=tmp_path):
        rc = merge.main(dry_run=True)

    assert rc == 0
    assert canonical.read_bytes() == original_bytes, "dry-run must not modify existing canonical"
    assert (emb_dir / "charlie_manifest.jsonl").exists(), "dry-run must not delete shards"
