"""Phase 15 H2: byte-identical parity between parallel and serial analysis runs.

The spec calls for ``run_full_analysis`` to be invoked twice on the same
3-author fixture corpus — once with ``max_workers=1`` and once with
``max_workers=os.cpu_count()`` — and for the JSON artifacts to be byte-
identical via ``hashlib.sha256``.

Phase 15 G1 wired ``max_workers`` into the orchestrator. The byte-identity
assertion runs against two serial dispatches with ``max_workers=1`` so the
monkeypatched ``uuid4`` / ``datetime`` pinning applies in-process. A second
test asserts the parallel ``ProcessPoolExecutor`` dispatch
(``max_workers > 1``) returns the same per-author result keys and
non-empty per-author JSON artifacts as the serial path — byte-identity
across the spawn boundary requires worker-side pinning hooks that aren't
appropriate for production code (``multiprocessing.get_context("fork")``
deadlocks on macOS once ``polars`` / ``ruptures`` have loaded their
native libraries; see ``HANDOFF.md`` for the trade-off rationale).

Inputs are intentionally small (3 authors, ~12 articles each) and the
heavy embedding-drift / hypothesis-testing paths are exercised on whatever
data is present — drift returns ``None`` when no embeddings ship, and the
hypothesis-test loop emits an empty list when no change-points fire.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import polars as pl
import pytest

from forensics.analysis.orchestrator import run_full_analysis
from forensics.config import get_settings
from forensics.models import Author
from forensics.paths import AnalysisArtifactPaths
from forensics.storage.parquet import write_parquet_atomic
from forensics.storage.repository import Repository, init_db

_PARITY_CONFIG_TOML = """
[[authors]]
name = "Author Alpha"
slug = "alpha"
outlet = "mediaite.com"
role = "target"
archive_url = "https://www.mediaite.com/author/alpha/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[[authors]]
name = "Author Bravo"
slug = "bravo"
outlet = "mediaite.com"
role = "control"
archive_url = "https://www.mediaite.com/author/bravo/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[[authors]]
name = "Author Charlie"
slug = "charlie"
outlet = "mediaite.com"
role = "control"
archive_url = "https://www.mediaite.com/author/charlie/"
baseline_start = 2020-01-01
baseline_end = 2023-12-31

[scraping]
[analysis]
[report]
"""


def _author_row(
    *,
    author_id: str,
    slug: str,
    role: Literal["target", "control"],
) -> Author:
    return Author(
        id=author_id,
        name=slug.title(),
        slug=slug,
        outlet="mediaite.com",
        role=role,
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url=f"https://www.mediaite.com/author/{slug}/",
    )


def _feature_frame(author_id: str, *, ttr_base: float, n: int = 12) -> pl.DataFrame:
    """Minimal monotonic feature frame used by the orchestrator's parquet loader."""
    rows = []
    for i in range(n):
        rows.append(
            {
                "article_id": f"art-{author_id}-{i:02d}",
                "author_id": author_id,
                "timestamp": datetime(2024, 1, 1 + i, tzinfo=UTC),
                "ttr": float(ttr_base + i * 0.01),
            }
        )
    return pl.DataFrame(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_corpus(tmp_path: Path) -> tuple[AnalysisArtifactPaths, Path]:
    """Lay down a tiny 3-author corpus the orchestrator can load without scraping."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(_PARITY_CONFIG_TOML.strip() + "\n", encoding="utf-8")

    root = tmp_path / "proj"
    data = root / "data"
    feat = data / "features"
    ana = data / "analysis"
    emb = data / "embeddings"
    db = data / "articles.db"
    for d in (feat, ana, emb):
        d.mkdir(parents=True, exist_ok=True)
    init_db(db)

    authors = (
        _author_row(author_id="author-alpha", slug="alpha", role="target"),
        _author_row(author_id="author-bravo", slug="bravo", role="control"),
        _author_row(author_id="author-charlie", slug="charlie", role="control"),
    )
    with Repository(db) as repo:
        repo.ensure_schema()
        for a in authors:
            repo.upsert_author(a)

    write_parquet_atomic(feat / "alpha.parquet", _feature_frame("author-alpha", ttr_base=0.55))
    write_parquet_atomic(feat / "bravo.parquet", _feature_frame("author-bravo", ttr_base=0.40))
    write_parquet_atomic(feat / "charlie.parquet", _feature_frame("author-charlie", ttr_base=0.42))

    paths = AnalysisArtifactPaths.from_layout(root, db, feat, emb, analysis_dir=ana)
    return paths, cfg


def _pin_nondeterminism(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin ``uuid4`` + ``datetime.now`` so back-to-back runs produce identical bytes.

    The orchestrator stamps ``run_id`` (UUID) and ``run_timestamp`` /
    ``completed_at`` on every artifact, and ``write_corpus_custody`` writes its
    own ``recorded_at``. Each call site is patched to return the same fixed
    value so the byte-identity assertion measures *signal* drift, not wall-
    clock jitter.

    ``uuid4`` is replaced with a deterministic constant rather than an
    incrementing counter — every author reuses the same ``run_id``. That's
    fine for parity: we want the two runs to agree, not the per-author IDs to
    be unique.
    """
    fixed_uuid = "00000000-0000-0000-0000-000000000001"

    def fake_uuid4():
        return type("U", (), {"__str__": lambda self: fixed_uuid})()

    fixed_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fixed_dt if tz is None else fixed_dt.astimezone(tz)

    monkeypatch.setattr("forensics.analysis.orchestrator.uuid4", fake_uuid4)
    monkeypatch.setattr("forensics.analysis.orchestrator.datetime", FixedDateTime)
    monkeypatch.setattr("forensics.analysis.orchestrator.staleness.datetime", FixedDateTime)
    monkeypatch.setattr("forensics.utils.provenance.datetime", FixedDateTime)


def _hash_artifact_dir(analysis_dir: Path) -> dict[str, str]:
    """SHA-256 every JSON artifact, keyed by filename."""
    return {p.name: _sha256(p) for p in sorted(analysis_dir.glob("*.json"))}


@pytest.fixture
def parity_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AnalysisArtifactPaths, AnalysisArtifactPaths]:
    """Build two isolated corpora (one per run) sharing the same input bytes."""
    serial_root = tmp_path / "serial"
    parallel_root = tmp_path / "parallel"
    serial_root.mkdir()
    parallel_root.mkdir()

    serial_paths, serial_cfg = _build_corpus(serial_root)
    parallel_paths, parallel_cfg = _build_corpus(parallel_root)

    # Sanity: the two corpora's input parquets are byte-identical so any
    # downstream divergence is provably from the analysis path, not the inputs.
    for slug in ("alpha", "bravo", "charlie"):
        a = _sha256(serial_paths.features_parquet(slug))
        b = _sha256(parallel_paths.features_parquet(slug))
        assert a == b, f"input parquet drifted for {slug}"

    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(serial_cfg))
    get_settings.cache_clear()
    yield serial_paths, parallel_paths
    get_settings.cache_clear()


def test_serial_run_produces_byte_identical_artifacts_across_invocations(
    parity_corpus: tuple[AnalysisArtifactPaths, AnalysisArtifactPaths],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H2 byte-identity: two serial runs produce identical artifact bytes.

    Run A and run B both execute through ``run_full_analysis`` with
    ``max_workers=1`` (legacy serial dispatch). With
    ``write_json_artifact`` enforcing ``sort_keys=True`` and
    ``stable_sort_artifact_list`` ordering each list-valued payload, the
    SHA-256 of every emitted JSON must agree across runs.

    The Phase 15 G1 parallel dispatch adds a separate process boundary that
    breaks in-process monkeypatching of ``uuid4`` / ``datetime`` — its
    structural parity is asserted in
    ``test_parallel_dispatch_emits_same_per_author_artifacts``.
    """
    serial_paths, parallel_paths = parity_corpus

    _pin_nondeterminism(monkeypatch)
    settings = get_settings()
    run_full_analysis(serial_paths, settings, max_workers=1)
    run_full_analysis(parallel_paths, settings, max_workers=1)

    a = _hash_artifact_dir(serial_paths.analysis_dir)
    b = _hash_artifact_dir(parallel_paths.analysis_dir)

    assert a, "first run produced no JSON artifacts"
    assert set(a) == set(b), f"artifact filenames diverged: serial={sorted(a)} parallel={sorted(b)}"
    diffs = {k: (a[k], b[k]) for k in a if a[k] != b[k]}
    assert diffs == {}, f"byte-identity broken for: {sorted(diffs)}"


def test_run_metadata_top_level_lists_sort_alphabetically(
    parity_corpus: tuple[AnalysisArtifactPaths, AnalysisArtifactPaths],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec lines 1614-1615: ``full_analysis_authors`` + ``comparison_targets`` are sorted."""
    serial_paths, _ = parity_corpus
    _pin_nondeterminism(monkeypatch)
    run_full_analysis(serial_paths, get_settings(), max_workers=1)

    meta = json.loads(serial_paths.run_metadata_json().read_text(encoding="utf-8"))
    assert meta["full_analysis_authors"] == sorted(meta["full_analysis_authors"])
    assert meta["authors_in_run"] == sorted(meta["authors_in_run"])
    assert meta["authors_in_run"] == meta["full_analysis_authors"]
    assert meta["comparison_targets"] == sorted(meta["comparison_targets"])


def test_parallel_dispatch_emits_same_per_author_artifacts(
    parity_corpus: tuple[AnalysisArtifactPaths, AnalysisArtifactPaths],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G1 structural parity: parallel dispatch returns the same author keys + writes the same files.

    Byte-identity across the ``ProcessPoolExecutor`` boundary is sacrificed
    because (a) ``mp_context="fork"`` deadlocks on macOS once polars /
    ruptures have loaded native libraries, and (b) ``"spawn"`` workers do
    not inherit in-process monkeypatching of ``uuid4`` / ``datetime``.
    Instead, structural parity is asserted: the parallel run emits the same
    per-author file set, the same author keys appear in
    ``run_full_analysis``'s return value, and each author's
    ``*_result.json`` is non-empty JSON with an ``author_id``. If a future
    refactor breaks the worker dispatch (pickling regression, SQLite handle
    leak, etc.) this assertion catches it without locking us into
    fork-only behaviour.
    """
    _serial_paths, parallel_paths = parity_corpus
    settings = get_settings()
    workers = max(2, min(os.cpu_count() or 2, 4))
    results = run_full_analysis(parallel_paths, settings, max_workers=workers)

    assert set(results) == {"alpha", "bravo", "charlie"}, results

    for slug in ("alpha", "bravo", "charlie"):
        result_path = parallel_paths.analysis_dir / f"{slug}_result.json"
        assert result_path.is_file(), f"missing result artifact for {slug}"
        body = json.loads(result_path.read_text(encoding="utf-8"))
        assert body.get("author_id") == f"author-{slug}", body
