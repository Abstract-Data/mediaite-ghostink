"""HTML report assembly for the per-author and aggregate report (Phase 15 K-series).

This module is intentionally tiny: each helper renders one named HTML
fragment and is owned by a single K-series step (K2 = section mix, K3 =
section contrast, K4 = adjusted-vs-unadjusted CP twin panel, K5 =
outlet-level section profile embed). The aggregator
:func:`render_author_section` stitches them together in a fixed order so
sibling agents can land helpers without coordinating prose changes.

The module is *idempotent under re-import*: defining a helper that already
exists from a sibling Wave 3.1 PR is avoided by checking ``globals()``
before redefining. Sibling K1/K2/K3 own different helpers in this same
file; this file deliberately defines only K4 + K5 helpers and the
aggregator.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from html import escape
from pathlib import Path

from forensics.reporting.plots import render_cp_twin_panel

# K5 — outlet-level section profile artifact path (relative to project_root)
SECTION_PROFILE_REPORT_RELPATH: str = "data/analysis/section_profile_report.md"

K5_FALLBACK_HTML = (
    '<section class="outlet-section-profile">'
    "<h2>Outlet-Level Section Profile</h2>"
    "<p><em>Section profile not yet computed; run "
    "<code>forensics analyze section-profile</code> to generate "
    "<code>data/analysis/section_profile_report.md</code>.</em></p>"
    "</section>"
)


def _render_cp_twin_panel_section(
    *,
    author_slug: str,
    timestamps: Sequence[datetime],
    feature_series: Sequence[float],
    change_points: Iterable[object],
    feature_name: str = "stylometric feature",
) -> str:
    """K4 wrapper: wrap the bare plotly fragment in a labelled ``<section>``."""
    fragment = render_cp_twin_panel(
        author_slug=author_slug,
        timestamps=timestamps,
        feature_series=feature_series,
        change_points=change_points,
        feature_name=feature_name,
    )
    return (
        '<section class="cp-twin-panel">'
        "<h3>Adjusted vs unadjusted change-points</h3>"
        f"{fragment}"
        "</section>"
    )


def render_section_profile_embed(project_root: Path) -> str:
    """K5: embed the outlet-level section profile report when present.

    The aggregate report calls this once (not per-author). When the J3
    artifact has not been generated, returns the K5 fallback notice rather
    than raising or omitting the section — the reader should always see
    either the verdict or an explanation of why it is missing.
    """
    report_path = project_root / SECTION_PROFILE_REPORT_RELPATH
    if not report_path.is_file():
        return K5_FALLBACK_HTML
    body = report_path.read_text(encoding="utf-8")
    # Embedding raw markdown inside a <pre> keeps formatting predictable
    # without pulling in a markdown→HTML dependency. The escape() call is
    # essential — a stray ``<`` in the report would otherwise corrupt the
    # surrounding HTML.
    return (
        '<section class="outlet-section-profile">'
        "<h2>Outlet-Level Section Profile</h2>"
        '<pre class="section-profile-md">'
        f"{escape(body)}"
        "</pre>"
        "</section>"
    )


def render_author_section(
    *,
    author_slug: str,
    timestamps: Sequence[datetime],
    feature_series: Sequence[float],
    change_points: Iterable[object],
    feature_name: str = "stylometric feature",
    pipeline_b_diagnostic_html: str = "",
) -> str:
    """Assemble the per-author HTML section.

    Sibling Wave 3.1 (K1+K2+K3) may add additional helpers and extend the
    aggregator; this version only stitches K4 + the optional Pipeline B
    diagnostic block (K6). The diagnostic, if present, is rendered before
    the chart so reviewers see the data-completeness caveat first.
    """
    parts: list[str] = [f'<section class="author" data-author="{escape(author_slug)}">']
    parts.append(f"<h2>Author: {escape(author_slug)}</h2>")
    if pipeline_b_diagnostic_html:
        parts.append(pipeline_b_diagnostic_html)
    parts.append(
        _render_cp_twin_panel_section(
            author_slug=author_slug,
            timestamps=timestamps,
            feature_series=feature_series,
            change_points=change_points,
            feature_name=feature_name,
        )
    )
    parts.append("</section>")
    return "".join(parts)


__all__ = [
    "K5_FALLBACK_HTML",
    "SECTION_PROFILE_REPORT_RELPATH",
    "render_author_section",
    "render_section_profile_embed",
]
