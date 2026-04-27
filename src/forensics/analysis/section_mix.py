"""Per-author monthly section-share matrix → ``data/analysis/<slug>_section_mix.json``.

Rows sum to 1 per month (0 when empty). JSON key ordering is stable; see
``tests/unit/test_section_mix.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from forensics.storage.json_io import write_text_atomic
from forensics.utils.url import section_from_url

__all__ = [
    "SectionMixSeries",
    "compute_and_write_section_mix",
    "compute_section_mix",
    "section_mix_artifact_path",
    "write_section_mix_artifact",
]

# Column names this module expects (or derives) on the input frame.
_AUTHOR_ID_COL = "author_id"
_TIMESTAMP_COL = "timestamp"
_SECTION_COL = "section"
_URL_COL = "url"


@dataclass(frozen=True, slots=True)
class SectionMixSeries:
    """Per-author monthly section-share matrix.

    Attributes:
        author_id: Stable identifier for the author (matches the value in the
            input frame, not necessarily the slug).
        months: ``YYYY-MM`` keys in chronological order.
        sections: Section names in alphabetical order.
        shares: Dense matrix where ``shares[i][j]`` is the share of
            ``sections[j]`` in ``months[i]``. Each row sums to 1.0 unless the
            month has no articles, in which case the row is all zeros.
    """

    author_id: str
    months: list[str]
    sections: list[str]
    shares: list[list[float]]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready dict in the canonical key order."""
        return {
            "author_id": self.author_id,
            "months": list(self.months),
            "sections": list(self.sections),
            "shares": [list(row) for row in self.shares],
        }


def _ensure_section_column(frame: pl.LazyFrame, schema_names: set[str]) -> pl.LazyFrame:
    """Return ``frame`` with a ``section`` column, deriving from ``url`` if absent.

    J1 (Wave 2.1) is wiring ``section`` into the feature parquet. Until every
    upstream caller has migrated, this falls back to deriving on read via
    :func:`forensics.utils.url.section_from_url`. If ``url`` is also missing,
    every row gets ``"unknown"``.
    """
    if _SECTION_COL in schema_names:
        return frame
    if _URL_COL in schema_names:
        return frame.with_columns(
            pl.col(_URL_COL)
            .map_elements(section_from_url, return_dtype=pl.Utf8)
            .alias(_SECTION_COL)
        )
    return frame.with_columns(pl.lit("unknown").alias(_SECTION_COL))


def compute_section_mix(
    author_id: str,
    articles_df: pl.DataFrame | pl.LazyFrame,
) -> SectionMixSeries:
    """Compute the per-author monthly section-share matrix for ``author_id``.

    The input frame must carry ``author_id`` and ``timestamp`` columns and
    either ``section`` or ``url`` (the latter is derived on read via
    :func:`section_from_url`). Rows with a missing ``timestamp`` are dropped.

    Returns an empty :class:`SectionMixSeries` if the author has no articles.
    """
    lazy = articles_df.lazy() if isinstance(articles_df, pl.DataFrame) else articles_df
    schema_names = set(lazy.collect_schema().names())
    for required in (_AUTHOR_ID_COL, _TIMESTAMP_COL):
        if required not in schema_names:
            msg = f"section_mix input frame missing required column: {required}"
            raise ValueError(msg)

    lazy = _ensure_section_column(lazy, schema_names)

    # Filter to this author, drop null timestamps, and bucket into YYYY-MM.
    counts_df = (
        lazy.filter(pl.col(_AUTHOR_ID_COL) == author_id)
        .filter(pl.col(_TIMESTAMP_COL).is_not_null())
        .with_columns(pl.col(_TIMESTAMP_COL).dt.strftime("%Y-%m").alias("_month"))
        .group_by(["_month", _SECTION_COL])
        .agg(pl.len().alias("_count"))
        .collect()
    )

    if counts_df.is_empty():
        return SectionMixSeries(
            author_id=author_id,
            months=[],
            sections=[],
            shares=[],
        )

    # Single pass: collect axes and bucket counts simultaneously.
    months_set: set[str] = set()
    sections_set: set[str] = set()
    raw_counts: dict[tuple[str, str], float] = {}
    for row in counts_df.iter_rows(named=True):
        month, section, count = row["_month"], row[_SECTION_COL], float(row["_count"])
        months_set.add(month)
        sections_set.add(section)
        raw_counts[(month, section)] = count

    months = sorted(months_set)
    sections = sorted(sections_set)

    shares: list[list[float]] = []
    for month in months:
        row_counts = [raw_counts.get((month, section), 0.0) for section in sections]
        total = sum(row_counts)
        if total <= 0.0:
            shares.append([0.0] * len(sections))
        else:
            shares.append([count / total for count in row_counts])

    return SectionMixSeries(
        author_id=author_id,
        months=months,
        sections=sections,
        shares=shares,
    )


def _serialise_canonical(series: SectionMixSeries, *, indent: int = 2) -> str:
    """Render ``series`` as canonical JSON: sorted keys, deterministic ordering."""
    return json.dumps(series.to_dict(), indent=indent, sort_keys=True)


def write_section_mix_artifact(
    series: SectionMixSeries,
    artifact_path: Path,
    *,
    indent: int = 2,
) -> None:
    """Atomically write ``series`` to ``artifact_path`` with a canonical encoding.

    The encoding uses ``sort_keys=True`` so the resulting bytes are stable
    for a fixed fixture (Phase H2 byte-parity contract). Parent directories
    are created if absent.
    """
    text = _serialise_canonical(series, indent=indent) + "\n"
    write_text_atomic(artifact_path, text)


def section_mix_artifact_path(analysis_dir: Path, author_slug: str) -> Path:
    """Return the canonical artifact path for a per-author section-mix file."""
    return analysis_dir / f"{author_slug}_section_mix.json"


def compute_and_write_section_mix(
    author_id: str,
    author_slug: str,
    articles_df: pl.DataFrame | pl.LazyFrame,
    analysis_dir: Path,
) -> tuple[SectionMixSeries, Path]:
    """Convenience wrapper: compute, persist, and return both the series and path."""
    series = compute_section_mix(author_id, articles_df)
    path = section_mix_artifact_path(analysis_dir, author_slug)
    write_section_mix_artifact(series, path)
    return series, path
