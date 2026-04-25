"""Phase 16 B — embedding manifest revision gate on the drift load path."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from forensics.analysis.artifact_paths import AnalysisArtifactPaths
from forensics.analysis.drift import load_article_embeddings, validate_embedding_record
from forensics.models.features import EmbeddingRecord
from forensics.storage.parquet import write_author_embedding_batch, write_embeddings_manifest
from forensics.storage.repository import Repository, init_db


@pytest.fixture()
def revision_gate_layout(tmp_path, sample_author):
    root = tmp_path
    db_path = root / "data" / "articles.db"
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)
    emb_root = root / "data" / "embeddings"
    slug_dir = emb_root / sample_author.slug
    slug_dir.mkdir(parents=True)
    batch_path = slug_dir / "batch.npz"
    write_author_embedding_batch(
        batch_path,
        ["art-1"],
        np.ones((1, 8), dtype=np.float32),
    )
    paths = AnalysisArtifactPaths.from_layout(root, db_path, root / "data" / "features", emb_root)
    rel = f"data/embeddings/{sample_author.slug}/batch.npz"
    return sample_author, paths, rel


def test_load_article_embeddings_revision_mismatch_raises_confirmatory(
    revision_gate_layout,
) -> None:
    sample_author, paths, rel = revision_gate_layout
    rec = EmbeddingRecord(
        article_id="art-1",
        author_id=sample_author.id,
        timestamp=datetime(2024, 8, 1, tzinfo=UTC),
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_version="v2.0",
        model_revision="wrong-sha",
        embedding_path=rel,
        embedding_dim=8,
    )
    write_embeddings_manifest([rec], paths.embeddings_dir / "manifest.jsonl")
    with pytest.raises(ValueError, match="revision mismatch"):
        load_article_embeddings(
            sample_author.slug,
            paths,
            expected_revision="good-sha",
            exploratory=False,
            allow_pre_phase16_embeddings=False,
        )


def test_load_article_embeddings_revision_mismatch_exploratory_raises_without_flag(
    revision_gate_layout,
) -> None:
    sample_author, paths, rel = revision_gate_layout
    rec = EmbeddingRecord(
        article_id="art-1",
        author_id=sample_author.id,
        timestamp=datetime(2024, 8, 1, tzinfo=UTC),
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_version="v2.0",
        model_revision="wrong-sha",
        embedding_path=rel,
        embedding_dim=8,
    )
    write_embeddings_manifest([rec], paths.embeddings_dir / "manifest.jsonl")
    with pytest.raises(ValueError, match="revision mismatch"):
        load_article_embeddings(
            sample_author.slug,
            paths,
            expected_revision="good-sha",
            exploratory=True,
            allow_pre_phase16_embeddings=False,
        )


def test_load_article_embeddings_revision_mismatch_exploratory_warns_with_flag(
    revision_gate_layout,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sample_author, paths, rel = revision_gate_layout
    rec = EmbeddingRecord(
        article_id="art-1",
        author_id=sample_author.id,
        timestamp=datetime(2024, 8, 1, tzinfo=UTC),
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_version="v2.0",
        model_revision="wrong-sha",
        embedding_path=rel,
        embedding_dim=8,
    )
    write_embeddings_manifest([rec], paths.embeddings_dir / "manifest.jsonl")
    caplog.set_level("WARNING")
    pairs = load_article_embeddings(
        sample_author.slug,
        paths,
        expected_revision="good-sha",
        exploratory=True,
        allow_pre_phase16_embeddings=True,
    )
    assert len(pairs) == 1
    assert "revision mismatch" in caplog.text


def test_validate_embedding_record_dim_mismatch_always_raises() -> None:
    rec = EmbeddingRecord(
        article_id="a1",
        author_id="u",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        model_name="m",
        model_version="v",
        model_revision="r",
        embedding_path="p",
        embedding_dim=384,
    )
    vec = np.zeros(10, dtype=np.float32)
    with pytest.raises(ValueError, match="dimension mismatch"):
        validate_embedding_record(
            rec,
            vec,
            "r",
            exploratory=True,
            allow_pre_phase16_embeddings=True,
        )
