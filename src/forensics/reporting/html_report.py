"""HTML report assembly for the per-author and aggregate report (Phase 15 K-series).

This module is intentionally tiny: each helper renders one named HTML
fragment and is owned by a single K-series step:

- K2 — section-mix stacked-area chart (``render_section_mix_chart``)
- K3 — section-contrast table (``render_section_contrast_table``)
- K4 — adjusted-vs-unadjusted CP twin panel (``_render_cp_twin_panel_section``)
- K5 — outlet-level section profile embed (``render_section_profile_embed``)

The aggregator :func:`render_author_section` stitches them together in a
fixed order so sibling agents can land helpers without coordinating prose
changes. Every helper here is a free function with no shared state.

Soft-failure semantics: a missing artifact yields a short placeholder
fragment so the surrounding report renders cleanly even when its sibling
wave hasn't shipped yet (e.g. J5 residualization). The chart helpers use
:mod:`plotly.graph_objects` directly (rather than ``plotly.express``) so
the report stage stays pandas-free — this project is Polars-native.
"""

from __future__ import annotations

import html
import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from html import escape
from pathlib import Path

import plotly.graph_objects as go

from forensics.reporting.plots import render_cp_twin_panel

__all__ = [
    "K5_FALLBACK_HTML",
    "SECTION_MIX_CAPTION",
    "SECTION_PROFILE_REPORT_RELPATH",
    "render_author_section",
    "render_section_contrast_table",
    "render_section_mix_chart",
    "render_section_profile_embed",
]

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

# K2 — verbatim caption from the prompt spec (Phase 15). Tests pin this string.
SECTION_MIX_CAPTION = (
    "Section mix. Use this to distinguish stylistic drift from editorial mix shifts."
)

_MISSING_SECTION_MIX_FRAGMENT = (
    '<div class="section-mix-missing"><p><em>No section-mix data available.</em></p></div>'
)
_MISSING_SECTION_CONTRAST_FRAGMENT = (
    '<div class="section-contrast-missing"><p><em>No section-contrast data.</em></p></div>'
)
_INSUFFICIENT_VOLUME_FRAGMENT = (
    '<div class="section-contrast-insufficient">'
    "<p><em>Insufficient section volume for per-author section-contrast tests.</em></p>"
    "</div>"
)


# ---------------------------------------------------------------------------
# Loading helpers — defensive: a missing/malformed file is a soft failure.
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict | None:
    """Return the parsed JSON dict, or ``None`` when missing/invalid."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# K2 — section-mix stacked-area chart
# ---------------------------------------------------------------------------


def _section_mix_payload(data: dict) -> tuple[list[str], list[str], list[list[float]]]:
    """Extract the three axes from a section-mix JSON payload."""
    months = [str(m) for m in data.get("months", [])]
    sections = [str(s) for s in data.get("sections", [])]
    raw_shares = data.get("shares", [])
    shares: list[list[float]] = []
    for row in raw_shares:
        shares.append([float(v) for v in row])
    return months, sections, shares


def _series_per_section(sections: list[str], shares: list[list[float]]) -> dict[str, list[float]]:
    """Pivot row-major shares into ``{section: [share per month, ...]}``."""
    series: dict[str, list[float]] = {section: [] for section in sections}
    for row in shares:
        for col_idx, section in enumerate(sections):
            value = row[col_idx] if col_idx < len(row) else 0.0
            series[section].append(value)
    return series


def render_section_mix_chart(
    section_mix_path: Path,
    *,
    author_slug: str,
    div_id: str | None = None,
) -> str:
    """Render the section-mix stacked-area chart as a self-contained HTML fragment."""
    payload = _load_json(section_mix_path)
    if payload is None:
        return _MISSING_SECTION_MIX_FRAGMENT

    months, sections, shares = _section_mix_payload(payload)
    if not months or not sections or not shares:
        return _MISSING_SECTION_MIX_FRAGMENT

    series_by_section = _series_per_section(sections, shares)
    figure = go.Figure()
    for section in sections:
        values = series_by_section[section]
        share_pct = [v * 100.0 for v in values]
        figure.add_trace(
            go.Scatter(
                name=section,
                x=months,
                y=values,
                mode="lines",
                stackgroup="section_mix",
                groupnorm="fraction",
                hovertemplate=(
                    "Section: %{fullData.name}<br>"
                    "Month: %{x}<br>"
                    "Share: %{customdata:.1f}%<extra></extra>"
                ),
                customdata=share_pct,
            )
        )
    figure.update_layout(
        title=f"Section mix — {author_slug}",
        yaxis_title="Share of articles",
        xaxis_title="Month",
        legend_title="Section",
    )
    plot_div_id = div_id or f"section-mix-{author_slug}"
    chart_html = figure.to_html(
        include_plotlyjs="cdn",
        full_html=False,
        div_id=plot_div_id,
    )
    return (
        '<div class="section-mix-chart">'
        f"{chart_html}"
        f'<p class="section-mix-caption"><em>{html.escape(SECTION_MIX_CAPTION)}</em></p>'
        "</div>"
    )


# ---------------------------------------------------------------------------
# K3 — section-contrast table
# ---------------------------------------------------------------------------


def _pair_label(pair: dict) -> str | None:
    """Return ``"section_a vs section_b"`` or ``None`` when either is empty."""
    sec_a = str(pair.get("section_a", "")).strip()
    sec_b = str(pair.get("section_b", "")).strip()
    if not sec_a or not sec_b:
        return None
    return f"{sec_a} vs {sec_b}"


def _significant_feature_map(pair: dict) -> dict[str, list[str]]:
    """Coerce ``significant_features_by_family`` into ``{family: [features]}``."""
    raw = pair.get("significant_features_by_family", {}) or {}
    if not isinstance(raw, dict):
        return {}
    return {str(family): [str(f) for f in feats] for family, feats in raw.items() if feats}


def _collect_contrast_axes(
    pairs: list[dict],
) -> tuple[list[str], list[str], dict[tuple[str, str], set[str]]]:
    """Walk ``pairs`` once to collect rows (sections), columns (families), cells."""
    pair_labels: set[str] = set()
    families: set[str] = set()
    cells: dict[tuple[str, str], set[str]] = {}
    for pair in pairs:
        label = _pair_label(pair)
        if label is None:
            continue
        pair_labels.add(label)
        for family, feats in _significant_feature_map(pair).items():
            families.add(family)
            cell = cells.setdefault((label, family), set())
            cell.update(feats)
    return sorted(pair_labels), sorted(families), cells


def _render_contrast_table_html(
    pair_labels: list[str],
    families: list[str],
    cells: dict[tuple[str, str], set[str]],
) -> str:
    """Render the (rows × columns) HTML table fragment for K3."""
    header_cells = "".join(f"<th>{html.escape(f)}</th>" for f in families)
    rows_html: list[str] = []
    for label in pair_labels:
        body_cells: list[str] = []
        for family in families:
            features = cells.get((label, family), set())
            if features:
                joined = ", ".join(html.escape(f) for f in sorted(features))
                body_cells.append(f"<td>{joined}</td>")
            else:
                body_cells.append('<td class="empty">&mdash;</td>')
        row_header = f'<th scope="row">{html.escape(label)}</th>'
        rows_html.append(f"<tr>{row_header}{''.join(body_cells)}</tr>")
    body = "".join(rows_html)
    return (
        '<table class="section-contrast-table">'
        f"<thead><tr><th>Section pair</th>{header_cells}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
    )


def render_section_contrast_table(
    section_contrast_path: Path,
    *,
    author_slug: str,
) -> str:
    """Render the per-author section-contrast table as an HTML fragment."""
    payload = _load_json(section_contrast_path)
    if payload is None:
        return _MISSING_SECTION_CONTRAST_FRAGMENT

    if payload.get("disposition") == "insufficient_section_volume":
        return _INSUFFICIENT_VOLUME_FRAGMENT

    pairs_raw = payload.get("pairs", [])
    if not isinstance(pairs_raw, list) or not pairs_raw:
        return _MISSING_SECTION_CONTRAST_FRAGMENT

    pair_labels, families, cells = _collect_contrast_axes(pairs_raw)
    if not pair_labels or not families:
        return _MISSING_SECTION_CONTRAST_FRAGMENT

    table_html = _render_contrast_table_html(pair_labels, families, cells)
    return (
        '<div class="section-contrast">'
        f"<h4>Section contrast — {html.escape(author_slug)}</h4>"
        f"{table_html}"
        "</div>"
    )


# ---------------------------------------------------------------------------
# K4 — adjusted-vs-unadjusted CP twin panel
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# K5 — outlet-level section profile embed
# ---------------------------------------------------------------------------


def render_section_profile_embed(project_root: Path) -> str:
    """K5: embed the outlet-level section profile report when present."""
    report_path = project_root / SECTION_PROFILE_REPORT_RELPATH
    if not report_path.is_file():
        return K5_FALLBACK_HTML
    body = report_path.read_text(encoding="utf-8")
    return (
        '<section class="outlet-section-profile">'
        "<h2>Outlet-Level Section Profile</h2>"
        '<pre class="section-profile-md">'
        f"{escape(body)}"
        "</pre>"
        "</section>"
    )


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def render_author_section(
    *,
    author_slug: str,
    timestamps: Sequence[datetime],
    feature_series: Sequence[float],
    change_points: Iterable[object],
    feature_name: str = "stylometric feature",
    pipeline_b_diagnostic_html: str = "",
    section_mix_path: Path | None = None,
    section_contrast_path: Path | None = None,
) -> str:
    """Assemble the per-author HTML section.

    Stitches K2 (section mix), K3 (section contrast), K4 (CP twin panel),
    and K6's optional Pipeline B diagnostic block in a fixed order.
    Per spec, the section-mix chart is placed *above* the CP visual so the
    reader sees editorial-mix context before stylometric drift.
    """
    parts: list[str] = [f'<section class="author" data-author="{escape(author_slug)}">']
    parts.append(f"<h2>Author: {escape(author_slug)}</h2>")
    if pipeline_b_diagnostic_html:
        parts.append(pipeline_b_diagnostic_html)
    if section_mix_path is not None:
        parts.append(render_section_mix_chart(section_mix_path, author_slug=author_slug))
    parts.append(
        _render_cp_twin_panel_section(
            author_slug=author_slug,
            timestamps=timestamps,
            feature_series=feature_series,
            change_points=change_points,
            feature_name=feature_name,
        )
    )
    if section_contrast_path is not None:
        parts.append(render_section_contrast_table(section_contrast_path, author_slug=author_slug))
    parts.append("</section>")
    return "".join(parts)
