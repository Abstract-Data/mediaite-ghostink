"""HTML fragments for the per-author report sections (Phase 15 K2 + K3).

Wave 3 wires three new analysis artifacts into the per-author HTML report:

- ``<author_slug>_section_mix.json`` (J4) — a stacked-area plot of monthly
  section composition, placed *above* the stylometric drift plot. K2.
- ``<author_slug>_section_contrast.json`` (J6) — a per-author table of
  pairwise section contrasts, summarised at the feature-family level. K3.

Both helpers in this module return self-contained HTML strings. They never
write to disk and never raise on missing inputs: a missing artifact yields a
short placeholder fragment so the surrounding report renders cleanly even
when its sibling wave hasn't shipped yet (J6 is parallel work in Wave 3.3).

Wave 3.2 (K4–K6) will add adjusted-vs-unadjusted change-point twin panels,
the section-profile embed, and the Pipeline B diagnostics block in this
same file. To keep the conflict surface small, every helper here is a
free function with no shared state.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import plotly.graph_objects as go

__all__ = [
    "SECTION_MIX_CAPTION",
    "render_section_contrast_table",
    "render_section_mix_chart",
]

# Verbatim caption from the prompt spec (Phase 15 K2). Tests pin this string.
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
    """Return the parsed JSON dict, or ``None`` when missing/invalid.

    Soft-failure semantics keep K2/K3 from crashing the report stage when the
    sibling analysis artifact (especially K3's J6) has not yet been produced.
    """
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
    """Render the section-mix stacked-area chart as a self-contained HTML fragment.

    Returns a short placeholder fragment when ``section_mix_path`` is missing
    or empty; the surrounding report still renders. The caption is fixed
    verbatim from the spec so reviewers see the same framing across authors.

    The chart uses :mod:`plotly.graph_objects` directly (rather than
    ``plotly.express.area``) so the report stage stays pandas-free — this
    project's data path is Polars-native and we do not want to drag pandas
    in as a transitive reporting dependency. The visual result (one stacked
    area per section, normalized to 1.0) is identical.
    """
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
    """Coerce ``significant_features_by_family`` into ``{family: [features]}``.

    Drops empty/missing entries so callers can iterate without re-checking.
    """
    raw = pair.get("significant_features_by_family", {}) or {}
    if not isinstance(raw, dict):
        return {}
    return {str(family): [str(f) for f in feats] for family, feats in raw.items() if feats}


def _collect_contrast_axes(
    pairs: list[dict],
) -> tuple[list[str], list[str], dict[tuple[str, str], set[str]]]:
    """Walk ``pairs`` once to collect rows (sections), columns (families), cells.

    The cell set holds the features with significant contrast for each
    (pair, family) cell. Pair labels are sorted alphabetically so the table
    is byte-stable across runs.
    """
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
    """Render the per-author section-contrast table as an HTML fragment.

    Soft-fails (returns a "no data" fragment) when:
    - the artifact file is missing (J6 may not have shipped yet),
    - the JSON is malformed,
    - ``disposition == "insufficient_section_volume"`` (we render a short
      note instead, as the spec requires),
    - or no qualifying pairs are present.
    """
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
