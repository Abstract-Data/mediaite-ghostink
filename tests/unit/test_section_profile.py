"""Unit tests for the Phase 15 J3 section descriptive report.

Coverage targets (per H1 spec):

* happy path — two clearly distinct synthetic sections produce a high
  cosine distance + Kruskal p < 0.01 → gate verdict ``PASS``.
* edge: a single retained section returns the ``DEGENERATE`` verdict
  without crashing (no inter-section contrast is possible).
* edge: a section with fewer than ``section_min_articles`` is dropped
  from the retained set.
* regression-pin: deterministic fixed-seed fixture locks the gate
  verdict so the J5 toggle decision is reproducible run-to-run.
* artifact write-out — JSON / CSV / Markdown all land on disk and
  contain the verdict.
* side-artifact happy path — the four J3 side artifacts (centroids,
  distance matrix JSON, distance matrix CSV, feature ranking JSON)
  all land beside the markdown report.
* side-artifact regression-pin — JSON shape (sort_keys, stable section
  order) is locked so two equivalent runs serialise to byte-identical
  bytes.
* side-artifact degenerate input — a single retained section writes
  the markdown report but skips the matrix files (with a documented
  note in the report).
* CSV/JSON header parity — CSV header section order matches the JSON
  ``sections`` key order so spreadsheet inspection lines up with
  programmatic readers.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from forensics.analysis.changepoint import PELT_FEATURE_COLUMNS
from forensics.analysis.section_profile import (
    GATE_MIN_MAX_OFF_DIAGONAL_DISTANCE,
    GATE_MIN_SIGNIFICANT_FAMILIES,
    compute_gate_verdict,
    compute_section_profile,
    write_section_profile,
)


def _make_frame(
    *,
    sections: dict[str, dict[str, object]],
    seed: int = 1234,
) -> pl.DataFrame:
    """Build a Polars frame matching the feature-parquet schema this stage reads.

    ``sections`` maps section name → ``{n: int, authors: list[str], shifts:
    dict[feature, mean]}``. Each feature is sampled from
    ``Normal(mean, 0.05)`` so the within-section variance is small relative
    to between-section shifts — this keeps the Kruskal test discriminative
    on small fixtures without forcing every test to repeat boilerplate.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for section, spec in sections.items():
        n = int(spec["n"])  # type: ignore[arg-type]
        authors: list[str] = list(spec["authors"])  # type: ignore[assignment]
        shifts: dict[str, float] = dict(spec.get("shifts", {}))  # type: ignore[arg-type]
        for i in range(n):
            row: dict[str, object] = {
                "author_id": authors[i % len(authors)],
                "section": section,
                "url": f"https://www.mediaite.com/{section}/article-{i}/",
            }
            for feature in PELT_FEATURE_COLUMNS:
                base = shifts.get(feature, 0.0)
                row[feature] = float(base + rng.normal(0.0, 0.05))
            rows.append(row)
    return pl.DataFrame(rows)


def test_happy_path_two_distinct_sections_pass_gate() -> None:
    """Two sections with large shifts on multiple families → PASS verdict."""
    df = _make_frame(
        sections={
            "opinion": {
                "n": 60,
                "authors": ["a1", "a2", "a3"],
                "shifts": {
                    "first_person_ratio": 1.5,
                    "hedging_frequency": 1.5,
                    "flesch_kincaid": 1.5,
                    "ttr": 1.5,
                    "sent_length_mean": 1.5,
                },
            },
            "politics": {
                "n": 60,
                "authors": ["b1", "b2", "b3"],
                "shifts": {
                    "first_person_ratio": -1.5,
                    "hedging_frequency": -1.5,
                    "flesch_kincaid": -1.5,
                    "ttr": -1.5,
                    "sent_length_mean": -1.5,
                },
            },
        },
        seed=42,
    )
    result = compute_section_profile(df, section_min_articles=50)

    assert set(result.sections) == {"opinion", "politics"}
    assert result.max_off_diagonal_distance > GATE_MIN_MAX_OFF_DIAGONAL_DISTANCE
    assert len(result.significant_families) >= GATE_MIN_SIGNIFICANT_FAMILIES
    assert result.gate_verdict == "PASS"
    # Centroid keys span every PELT feature (no silent drops on a clean fixture).
    for section in result.sections:
        assert set(result.centroids[section]) == set(PELT_FEATURE_COLUMNS)


def test_single_retained_section_returns_degenerate_without_crash() -> None:
    """Only one section meets retention → DEGENERATE verdict, no exception."""
    df = _make_frame(
        sections={
            "opinion": {
                "n": 60,
                "authors": ["a1", "a2"],
                "shifts": {"first_person_ratio": 1.0},
            },
            "tinysection": {
                "n": 5,
                "authors": ["b1"],
                "shifts": {"first_person_ratio": -1.0},
            },
        },
        seed=7,
    )
    result = compute_section_profile(df, section_min_articles=50)
    assert result.sections == ["opinion"]
    assert "tinysection" in result.skipped_sections
    assert result.gate_verdict == "DEGENERATE"
    # Distance matrix is 1×1, max off-diagonal must be 0 (no off-diagonal exists).
    assert result.max_off_diagonal_distance == 0.0


def test_section_below_min_articles_is_skipped() -> None:
    """Section below the threshold lands in ``skipped_sections`` with a reason."""
    df = _make_frame(
        sections={
            "politics": {
                "n": 80,
                "authors": ["a1", "a2"],
                "shifts": {"ttr": 0.5},
            },
            "podcasts": {
                "n": 10,  # below min_articles=50
                "authors": ["b1", "b2"],
                "shifts": {"ttr": -0.5},
            },
        },
        seed=11,
    )
    result = compute_section_profile(df, section_min_articles=50)
    assert "politics" in result.sections
    assert "podcasts" not in result.sections
    assert "podcasts" in result.skipped_sections
    # The reason references the threshold so a future operator can debug.
    assert "section_min_articles=50" in result.skipped_sections["podcasts"]


def test_gate_verdict_pinned_for_fixed_seed() -> None:
    """Regression-pin: this exact synthetic input must yield PASS forever.

    Locking the verdict (not the floating-point distance) keeps the gate
    decision reproducible across numpy / scipy patch upgrades while still
    catching regressions in :func:`compute_gate_verdict`'s threshold logic.
    """
    df = _make_frame(
        sections={
            "opinion": {
                "n": 55,
                "authors": ["a1", "a2"],
                "shifts": {
                    "first_person_ratio": 1.0,
                    "hedging_frequency": 1.0,
                    "flesch_kincaid": 1.0,
                    "ttr": 1.0,
                },
            },
            "politics": {
                "n": 55,
                "authors": ["b1", "b2"],
                "shifts": {
                    "first_person_ratio": -1.0,
                    "hedging_frequency": -1.0,
                    "flesch_kincaid": -1.0,
                    "ttr": -1.0,
                },
            },
            "sponsored": {
                "n": 55,
                "authors": ["c1", "c2"],
                "shifts": {
                    "ai_marker_frequency": 1.5,
                    "formula_opening_score": 1.5,
                    "self_similarity_30d": 1.0,
                },
            },
        },
        seed=20240501,
    )
    result = compute_section_profile(df, section_min_articles=50)
    assert sorted(result.sections) == ["opinion", "politics", "sponsored"]
    assert result.gate_verdict == "PASS", (
        f"verdict={result.gate_verdict}, families={result.significant_families}, "
        f"max_off_diag={result.max_off_diagonal_distance}"
    )


def test_artifacts_persist_to_disk(tmp_path: Path) -> None:
    """``write_section_profile`` lands all 5 artifacts and the verdict echoes through."""
    df = _make_frame(
        sections={
            "opinion": {
                "n": 60,
                "authors": ["a1", "a2"],
                "shifts": {"first_person_ratio": 1.5, "hedging_frequency": 1.5, "ttr": 1.5},
            },
            "politics": {
                "n": 60,
                "authors": ["b1", "b2"],
                "shifts": {"first_person_ratio": -1.5, "hedging_frequency": -1.5, "ttr": -1.5},
            },
        },
        seed=99,
    )
    result = compute_section_profile(df, section_min_articles=50)
    artifacts = write_section_profile(result, tmp_path)
    for path in (
        artifacts.centroids_json,
        artifacts.distance_matrix_json,
        artifacts.distance_matrix_csv,
        artifacts.feature_ranking_json,
        artifacts.report_md,
    ):
        assert path.is_file(), f"expected artifact at {path}"
    distance_payload = json.loads(artifacts.distance_matrix_json.read_text())
    assert distance_payload["sections"] == result.sections
    assert distance_payload["max_off_diagonal_distance"] == pytest.approx(
        result.max_off_diagonal_distance
    )
    ranking_payload = json.loads(artifacts.feature_ranking_json.read_text())
    assert ranking_payload["gate_verdict"] == result.gate_verdict
    report_text = artifacts.report_md.read_text()
    assert result.gate_verdict in report_text
    assert "Inter-section Cosine Distance Matrix" in report_text


@pytest.mark.parametrize(
    ("families", "max_off_diag", "n_sections", "expected"),
    [
        (["a", "b", "c"], 0.4, 2, "PASS"),
        (["a", "b", "c"], 0.2, 2, "BORDERLINE"),
        (["a"], 0.4, 2, "BORDERLINE"),
        (["a"], 0.2, 2, "FAIL"),
        ([], 0.0, 1, "DEGENERATE"),
    ],
)
def test_compute_gate_verdict_truth_table(
    families: list[str], max_off_diag: float, n_sections: int, expected: str
) -> None:
    """The verdict logic is a 4-way truth table over the two J5 criteria."""
    assert (
        compute_gate_verdict(
            significant_families=families,
            max_off_diagonal=max_off_diag,
            n_sections=n_sections,
        )
        == expected
    )


def test_empty_frame_does_not_invent_phantom_row() -> None:
    """Polars footgun: ``pl.DataFrame().with_columns(pl.lit(...))`` becomes 1 row.

    ``compute_section_profile`` must short-circuit on an empty input frame
    so the report doesn't claim a phantom ``unknown`` section was skipped.
    Regression-pin for the empty-corpus CLI smoke path.
    """
    result = compute_section_profile(pl.DataFrame(), section_min_articles=50)
    assert result.sections == []
    assert result.skipped_sections == {}
    assert result.gate_verdict == "DEGENERATE"


def _two_section_result(tmp_path: Path):
    """Shared happy-path fixture for the side-artifact tests."""
    df = _make_frame(
        sections={
            "opinion": {
                "n": 60,
                "authors": ["a1", "a2", "a3"],
                "shifts": {
                    "first_person_ratio": 1.5,
                    "hedging_frequency": 1.5,
                    "ttr": 1.5,
                    "flesch_kincaid": 1.5,
                },
            },
            "politics": {
                "n": 60,
                "authors": ["b1", "b2", "b3"],
                "shifts": {
                    "first_person_ratio": -1.5,
                    "hedging_frequency": -1.5,
                    "ttr": -1.5,
                    "flesch_kincaid": -1.5,
                },
            },
        },
        seed=20260424,
    )
    result = compute_section_profile(df, section_min_articles=50)
    artifacts = write_section_profile(result, tmp_path)
    return result, artifacts


def test_side_artifacts_happy_path_writes_all_four_alongside_markdown(tmp_path: Path) -> None:
    """All four J3 side artifacts + the markdown report land on disk together.

    This locks the PR #75 contract: ``compute_section_profile`` persists
    centroids, distance-matrix JSON, distance-matrix CSV, feature ranking
    JSON, and the markdown report in a single call. Regression-pin for the
    spec block (prompts/phase15-optimizations/v0.4.0.md lines 1280-1289).
    """
    result, artifacts = _two_section_result(tmp_path)

    assert artifacts.centroids_json is not None
    assert artifacts.distance_matrix_json is not None
    assert artifacts.distance_matrix_csv is not None
    assert artifacts.feature_ranking_json is not None
    assert artifacts.report_md is not None

    for path in (
        artifacts.centroids_json,
        artifacts.distance_matrix_json,
        artifacts.distance_matrix_csv,
        artifacts.feature_ranking_json,
        artifacts.report_md,
    ):
        assert path.is_file(), f"expected artifact at {path}"
        assert path.stat().st_size > 0, f"artifact at {path} is empty"

    # Centroids JSON must carry one key per retained section.
    centroids_payload = json.loads(artifacts.centroids_json.read_text())
    assert set(centroids_payload) == set(result.sections)

    # Feature ranking must include the per-section means/medians used by the
    # operator when reading the report — not just the aggregate ranking.
    ranking_payload = json.loads(artifacts.feature_ranking_json.read_text())
    assert "ranking" in ranking_payload
    first_row = ranking_payload["ranking"][0]
    assert "section_means" in first_row
    assert "section_medians" in first_row
    assert set(first_row["section_means"]) == set(result.sections)


def test_side_artifact_json_shape_is_regression_pinned(tmp_path: Path) -> None:
    """JSON shape is sort-key-stable so parallel runs produce byte-identical bytes.

    ``write_json_artifact`` defaults to ``sort_keys=True`` (Phase 15 H2).
    If a future refactor flips that flag the side artifacts lose their
    byte-identity guarantee — this test pins the invariant so the
    regression is caught before a parallel-parity run diverges.
    """
    _, artifacts = _two_section_result(tmp_path)

    # Top-level keys must be alphabetically sorted in the on-disk JSON. We
    # round-trip the bytes through ``json.loads`` + ``json.dumps(sort_keys=True)``
    # and compare — any drift from the sort_keys contract surfaces as a diff.
    for payload_path in (
        artifacts.distance_matrix_json,
        artifacts.feature_ranking_json,
        artifacts.centroids_json,
    ):
        raw_text = payload_path.read_text()
        canonical = json.dumps(json.loads(raw_text), indent=2, sort_keys=True)
        assert raw_text.rstrip("\n") == canonical.rstrip("\n"), (
            f"{payload_path} bytes diverge from sort_keys=True canonical form"
        )

    # Centroid keys inside each section are themselves sorted (important
    # because the centroid vectors feed the distance-matrix computation and
    # a drift in key order would quietly change the projection).
    centroids_raw = artifacts.centroids_json.read_text()
    centroids_payload = json.loads(centroids_raw)
    for section, vector in centroids_payload.items():
        assert list(vector) == sorted(vector), (
            f"centroid keys for {section!r} not sorted — sort_keys contract broken"
        )

    # Distance-matrix JSON section ordering mirrors ``result.sections`` (not
    # alphabetical — the sections key is list-valued and preserves compute
    # order so the matrix rows/cols remain aligned with centroids).
    distance_payload = json.loads(artifacts.distance_matrix_json.read_text())
    assert distance_payload["sections"] == sorted(distance_payload["sections"]), (
        "sections list must be sorted so CSV + JSON header orders align"
    )


def test_side_artifacts_degenerate_input_skips_matrix_files(tmp_path: Path) -> None:
    """Single retained section → markdown lands, matrix files are skipped.

    The 1×1 matrix would be misleading on disk (a single zero distance has
    no contrast signal), so ``write_section_profile`` intentionally skips
    both the JSON and CSV matrix outputs in that case. The markdown report
    documents the skip so an operator reading the analysis dir is not left
    guessing at missing files.
    """
    df = _make_frame(
        sections={
            "opinion": {
                "n": 60,
                "authors": ["a1", "a2", "a3"],
                "shifts": {"first_person_ratio": 1.0},
            },
            "tinysection": {
                "n": 5,
                "authors": ["b1"],
                "shifts": {"first_person_ratio": -1.0},
            },
        },
        seed=11,
    )
    result = compute_section_profile(df, section_min_articles=50)
    assert result.sections == ["opinion"]
    assert result.gate_verdict == "DEGENERATE"

    artifacts = write_section_profile(result, tmp_path)

    # Markdown + centroids + feature ranking still land on disk.
    assert artifacts.report_md.is_file()
    assert artifacts.centroids_json.is_file()
    assert artifacts.feature_ranking_json.is_file()

    # Matrix files were intentionally skipped — the artifact record reflects
    # the skip by holding ``None`` so downstream consumers don't chase a
    # phantom path.
    assert artifacts.distance_matrix_json is None
    assert artifacts.distance_matrix_csv is None
    assert not (tmp_path / "section_distance_matrix.json").exists()
    assert not (tmp_path / "section_distance_matrix.csv").exists()

    # The report documents the skip so a future operator reading the file
    # knows why two expected artifacts are missing.
    report_text = artifacts.report_md.read_text()
    assert "section_distance_matrix.json" in report_text
    assert "section_distance_matrix.csv" in report_text


def test_csv_header_order_matches_json_sections(tmp_path: Path) -> None:
    """CSV header columns match JSON ``sections`` so spreadsheet + JSON align.

    Without this pin the CSV and JSON could drift apart under a future
    refactor (e.g. one writes alphabetical and the other writes insertion
    order), which would produce misaligned rows when an analyst cross-
    references the two files.
    """
    _, artifacts = _two_section_result(tmp_path)
    assert artifacts.distance_matrix_json is not None
    assert artifacts.distance_matrix_csv is not None

    json_sections: list[str] = json.loads(artifacts.distance_matrix_json.read_text())["sections"]

    with artifacts.distance_matrix_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Header is ["section", *sections]; verify the trailing columns are in
        # the same order as the JSON sections key.
        assert header[0] == "section"
        assert header[1:] == json_sections

        # First column of each data row is the same section list, in the same
        # order — this keeps the matrix square from both axes.
        row_sections = [row[0] for row in reader]
        assert row_sections == json_sections
