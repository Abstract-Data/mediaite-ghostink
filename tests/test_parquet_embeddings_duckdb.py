"""Parquet embedding batch I/O, manifest edge cases, and DuckDB cross-store queries."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from pydantic import ValidationError

from forensics.models.features import EmbeddingRecord
from forensics.storage.duckdb_queries import (
    get_ai_marker_spike_detection,
    get_monthly_feature_stats,
    get_rolling_feature_comparison,
)
from forensics.storage.parquet import (
    load_feature_frame_sorted,
    read_embeddings_manifest,
    unpack_article_ids_from_embedding_batch,
    write_author_embedding_batch,
    write_embeddings_manifest,
)


def test_get_rolling_feature_comparison_window_invalid(tmp_path: Path) -> None:
    db_path = tmp_path / "articles.db"
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    with pytest.raises(ValueError, match="window"):
        get_rolling_feature_comparison(db_path, features_dir, "ttr", window=0)


def test_get_rolling_feature_comparison_invalid_feature_name(tmp_path: Path) -> None:
    db_path = tmp_path / "articles.db"
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    with pytest.raises(ValueError, match="Invalid feature"):
        get_rolling_feature_comparison(db_path, features_dir, "not-valid")


def test_get_rolling_feature_comparison_attach_rejects_missing_sqlite(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "missing.db"
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        get_rolling_feature_comparison(db_path, features_dir, "ttr")


def test_get_rolling_feature_comparison_attach_rejects_directory_not_file(
    tmp_path: Path,
) -> None:
    db_dir = tmp_path / "not_a_file"
    db_dir.mkdir()
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    with pytest.raises(ValueError, match="must be an existing file"):
        get_rolling_feature_comparison(db_dir, features_dir, "ttr")


def test_get_rolling_and_monthly_stats_with_sqlite_and_parquet(tmp_path: Path) -> None:
    """End-to-end DuckDB: SQLite authors joined to Parquet feature shards."""
    from forensics.models import Author
    from forensics.storage.repository import Repository, init_db

    db_path = tmp_path / "articles.db"
    init_db(db_path)
    author = Author(
        id="auth-duck-1",
        name="Duck Author",
        slug="duck-author",
        outlet="mediaite.com",
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url="https://example.com/a/",
    )
    with Repository(db_path) as repo:
        repo.upsert_author(author)

    features_dir = tmp_path / "features"
    features_dir.mkdir()
    ts = [
        datetime(2024, 1, 5, tzinfo=UTC),
        datetime(2024, 1, 20, tzinfo=UTC),
        datetime(2024, 2, 3, tzinfo=UTC),
    ]
    df = pl.DataFrame(
        {
            "article_id": ["p1", "p2", "p3"],
            "author_id": [author.id, author.id, author.id],
            "timestamp": ts,
            "ttr": [0.4, 0.6, 0.5],
        }
    )
    df.write_parquet(features_dir / f"{author.slug}.parquet")

    rolling = get_rolling_feature_comparison(db_path, features_dir, "ttr", window=2)
    assert rolling.height == 3
    assert "rolling_avg" in rolling.columns
    assert rolling["author"][0] == author.name

    monthly = get_monthly_feature_stats(features_dir, "ttr")
    assert monthly.height == 2
    assert "month" in monthly.columns
    assert monthly["n"].sum() == 3
    assert monthly.filter(pl.col("n") == 2).height == 1


def test_load_feature_frame_sorted_requires_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "no_ts.parquet"
    pl.DataFrame({"article_id": ["x"], "ttr": [0.1]}).write_parquet(path)
    with pytest.raises(ValueError, match="timestamp"):
        load_feature_frame_sorted(path)


def test_write_author_embedding_batch_shape_validation(tmp_path: Path) -> None:
    path = tmp_path / "batch.npz"
    with pytest.raises(ValueError, match="2-D"):
        write_author_embedding_batch(path, ["a"], np.zeros(4, dtype=np.float32))
    with pytest.raises(ValueError, match="length"):
        write_author_embedding_batch(path, ["a", "b"], np.zeros((1, 4), dtype=np.float32))


def test_write_author_embedding_batch_npz_roundtrip_no_pickle(tmp_path: Path) -> None:
    path = tmp_path / "batch.npz"
    ids = ["café-1", "naïve-2", "ascii"]
    mat = np.arange(3 * 7, dtype=np.float32).reshape(3, 7)
    write_author_embedding_batch(path, ids, mat)
    z = np.load(path, allow_pickle=False)
    assert set(z.files) == {"article_id_lengths", "article_id_bytes", "vectors"}
    got = unpack_article_ids_from_embedding_batch(
        z["article_id_lengths"],
        z["article_id_bytes"],
    )
    assert got == ids
    assert np.array_equal(z["vectors"], mat)


def test_unpack_article_ids_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="sum"):
        unpack_article_ids_from_embedding_batch(
            np.array([2, 2], dtype=np.int32),
            np.array([1, 2, 3], dtype=np.uint8),
        )


def test_read_embeddings_manifest_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_embeddings_manifest(tmp_path / "no_manifest.jsonl") == []


def test_read_embeddings_manifest_skips_blank_lines(tmp_path: Path) -> None:
    rec = EmbeddingRecord(
        article_id="a1",
        author_id="u1",
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        model_name="m",
        model_version="v",
        embedding_path="data/embeddings/x/batch.npz",
        embedding_dim=4,
    )
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "\n\n" + rec.model_dump_json() + "\n\n",
        encoding="utf-8",
    )
    rows = read_embeddings_manifest(manifest)
    assert len(rows) == 1 and rows[0].article_id == "a1"


def test_get_ai_marker_spike_detection_runs_on_parquet_shard(tmp_path: Path) -> None:
    features_dir = tmp_path / "feat"
    features_dir.mkdir()
    ts = [
        datetime(2024, 1, 10, tzinfo=UTC),
        datetime(2024, 1, 11, tzinfo=UTC),
        datetime(2024, 2, 10, tzinfo=UTC),
        datetime(2024, 2, 11, tzinfo=UTC),
    ]
    pl.DataFrame(
        {
            "article_id": ["a", "b", "c", "d"],
            "author_id": ["u", "u", "u", "u"],
            "timestamp": ts,
            "ai_marker_frequency": [0.01, 0.02, 0.9, 0.95],
        }
    ).write_parquet(features_dir / "shard.parquet")
    out = get_ai_marker_spike_detection(features_dir)
    assert out.height >= 2
    assert "spike" in out.columns


def test_read_embeddings_manifest_rejects_invalid_jsonl(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("not-json-at-all\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        read_embeddings_manifest(manifest)


def test_load_article_embeddings_legacy_npy_and_batch_npz(
    tmp_path: Path,
    sample_author,
) -> None:
    from forensics.analysis.drift import load_article_embeddings
    from forensics.storage.repository import Repository, init_db

    root = tmp_path
    db_path = root / "data" / "articles.db"
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)

    # --- legacy .npy per article ---
    emb_root = root / "data" / "embeddings"
    slug_dir = emb_root / sample_author.slug
    slug_dir.mkdir(parents=True)
    v1 = np.arange(5, dtype=np.float32)
    np.save(slug_dir / "art-npy.npy", v1)
    rec_npy = EmbeddingRecord(
        article_id="art-npy",
        author_id=sample_author.id,
        timestamp=datetime(2024, 4, 1, tzinfo=UTC),
        model_name="m",
        model_version="v",
        embedding_path=f"data/embeddings/{sample_author.slug}/art-npy.npy",
        embedding_dim=5,
    )
    write_embeddings_manifest([rec_npy], emb_root / "manifest.jsonl")
    pairs = load_article_embeddings(
        sample_author.slug,
        emb_root,
        db_path,
        project_root=root,
    )
    assert len(pairs) == 1
    assert np.allclose(pairs[0].embedding, v1)

    # --- batched .npz (multiple rows, shared file) ---
    v2 = np.ones(5, dtype=np.float32) * 2
    v3 = np.ones(5, dtype=np.float32) * 3
    batch_path = slug_dir / "batch.npz"
    write_author_embedding_batch(
        batch_path,
        ["art-a", "art-b"],
        np.stack([v2, v3], axis=0),
    )
    rec_batch = [
        EmbeddingRecord(
            article_id="art-a",
            author_id=sample_author.id,
            timestamp=datetime(2024, 5, 1, tzinfo=UTC),
            model_name="m",
            model_version="v",
            embedding_path=f"data/embeddings/{sample_author.slug}/batch.npz",
            embedding_dim=5,
        ),
        EmbeddingRecord(
            article_id="art-b",
            author_id=sample_author.id,
            timestamp=datetime(2024, 5, 2, tzinfo=UTC),
            model_name="m",
            model_version="v",
            embedding_path=f"data/embeddings/{sample_author.slug}/batch.npz",
            embedding_dim=5,
        ),
    ]
    # Second author article rows in DB are not required for load_article_embeddings
    write_embeddings_manifest(rec_batch, emb_root / "manifest.jsonl")
    pairs_b = load_article_embeddings(
        sample_author.slug,
        emb_root,
        db_path,
        project_root=root,
    )
    assert len(pairs_b) == 2
    pairs_b.sort(key=lambda x: x.published_at)
    assert np.allclose(pairs_b[0].embedding, v2)
    assert np.allclose(pairs_b[1].embedding, v3)


def test_load_article_embeddings_rejects_legacy_object_npz_batch(
    tmp_path: Path,
    sample_author,
) -> None:
    """Pre-P1-SEC-001 batches used object-dtyped article_ids (pickle on load)."""
    from forensics.analysis.drift import load_article_embeddings
    from forensics.storage.repository import Repository, init_db

    root = tmp_path
    db_path = root / "data" / "articles.db"
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)

    emb_root = root / "data" / "embeddings"
    slug_dir = emb_root / sample_author.slug
    slug_dir.mkdir(parents=True)
    legacy = slug_dir / "legacy.npz"
    np.savez_compressed(
        legacy,
        article_ids=np.asarray(["leg-a", "leg-b"], dtype=object),
        vectors=np.ones((2, 4), dtype=np.float32),
    )
    rec_batch = [
        EmbeddingRecord(
            article_id="leg-a",
            author_id=sample_author.id,
            timestamp=datetime(2024, 6, 1, tzinfo=UTC),
            model_name="m",
            model_version="v",
            embedding_path=f"data/embeddings/{sample_author.slug}/legacy.npz",
            embedding_dim=4,
        ),
    ]
    write_embeddings_manifest(rec_batch, emb_root / "manifest.jsonl")
    pairs = load_article_embeddings(
        sample_author.slug,
        emb_root,
        db_path,
        project_root=root,
    )
    assert pairs == []


def test_load_article_embeddings_skips_batch_missing_required_keys(
    tmp_path: Path,
    sample_author,
) -> None:
    """Malformed archive without UTF-8 packing keys is ignored (P1-TEST-001)."""
    from forensics.analysis.drift import load_article_embeddings
    from forensics.storage.repository import Repository, init_db

    root = tmp_path
    db_path = root / "data" / "articles.db"
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)

    emb_root = root / "data" / "embeddings"
    slug_dir = emb_root / sample_author.slug
    slug_dir.mkdir(parents=True)
    bad = slug_dir / "only_vectors.npz"
    np.savez_compressed(bad, vectors=np.ones((1, 3), dtype=np.float32))
    rec = EmbeddingRecord(
        article_id="x1",
        author_id=sample_author.id,
        timestamp=datetime(2024, 7, 1, tzinfo=UTC),
        model_name="m",
        model_version="v",
        embedding_path=f"data/embeddings/{sample_author.slug}/only_vectors.npz",
        embedding_dim=3,
    )
    write_embeddings_manifest([rec], emb_root / "manifest.jsonl")
    pairs = load_article_embeddings(
        sample_author.slug,
        emb_root,
        db_path,
        project_root=root,
    )
    assert pairs == []


def test_load_article_embeddings_skips_batch_vector_row_mismatch(
    tmp_path: Path,
    sample_author,
) -> None:
    """When packed id count does not match matrix rows, batch is rejected (P1-TEST-001)."""
    from forensics.analysis.drift import load_article_embeddings
    from forensics.storage.repository import Repository, init_db

    root = tmp_path
    db_path = root / "data" / "articles.db"
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)

    emb_root = root / "data" / "embeddings"
    slug_dir = emb_root / sample_author.slug
    slug_dir.mkdir(parents=True)
    mismatch = slug_dir / "mismatch.npz"
    np.savez_compressed(
        mismatch,
        article_id_lengths=np.array([2, 2], dtype=np.int32),
        article_id_bytes=np.frombuffer(b"aaaabbbb", dtype=np.uint8),
        vectors=np.ones((3, 4), dtype=np.float32),
    )
    rec = EmbeddingRecord(
        article_id="aaaa",
        author_id=sample_author.id,
        timestamp=datetime(2024, 7, 2, tzinfo=UTC),
        model_name="m",
        model_version="v",
        embedding_path=f"data/embeddings/{sample_author.slug}/mismatch.npz",
        embedding_dim=4,
    )
    write_embeddings_manifest([rec], emb_root / "manifest.jsonl")
    pairs = load_article_embeddings(
        sample_author.slug,
        emb_root,
        db_path,
        project_root=root,
    )
    assert pairs == []


def test_load_article_embeddings_skips_article_missing_from_batch(
    tmp_path: Path,
    sample_author,
) -> None:
    """Manifest row pointing at batch file but unknown article_id yields no row (P1-TEST-001)."""
    from forensics.analysis.drift import load_article_embeddings
    from forensics.storage.repository import Repository, init_db

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
        ["in-batch"],
        np.ones((1, 5), dtype=np.float32),
    )
    rec = EmbeddingRecord(
        article_id="not-in-batch",
        author_id=sample_author.id,
        timestamp=datetime(2024, 7, 3, tzinfo=UTC),
        model_name="m",
        model_version="v",
        embedding_path=f"data/embeddings/{sample_author.slug}/batch.npz",
        embedding_dim=5,
    )
    write_embeddings_manifest([rec], emb_root / "manifest.jsonl")
    pairs = load_article_embeddings(
        sample_author.slug,
        emb_root,
        db_path,
        project_root=root,
    )
    assert pairs == []


def test_load_article_embeddings_skips_corrupt_npy_file(
    tmp_path: Path,
    sample_author,
) -> None:
    """Non-numeric bytes behind a ``.npy`` path are skipped without raising (P1-TEST-001)."""
    from forensics.analysis.drift import load_article_embeddings
    from forensics.storage.repository import Repository, init_db

    root = tmp_path
    db_path = root / "data" / "articles.db"
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.upsert_author(sample_author)

    emb_root = root / "data" / "embeddings"
    slug_dir = emb_root / sample_author.slug
    slug_dir.mkdir(parents=True)
    corrupt = slug_dir / "bad.npy"
    corrupt.write_text("not a numpy array", encoding="utf-8")
    rec = EmbeddingRecord(
        article_id="c1",
        author_id=sample_author.id,
        timestamp=datetime(2024, 7, 4, tzinfo=UTC),
        model_name="m",
        model_version="v",
        embedding_path=f"data/embeddings/{sample_author.slug}/bad.npy",
        embedding_dim=99,
    )
    write_embeddings_manifest([rec], emb_root / "manifest.jsonl")
    pairs = load_article_embeddings(
        sample_author.slug,
        emb_root,
        db_path,
        project_root=root,
    )
    assert pairs == []
