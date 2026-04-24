"""Plot helpers for the per-author HTML report (Phase 15 K4).

Currently exposes :func:`render_cp_twin_panel`, the adjusted-vs-unadjusted
change-point twin-panel visualisation. The function is deliberately
side-effect-free — it returns an HTML fragment string so the calling
``html_report`` module can splice it into the page without having to know
how plotly is invoked.

When the J5 section-residualization toggle has not produced any
``pelt_section_adjusted`` / ``bocpd_section_adjusted`` change-points for
an author, the helper returns a short HTML notice rather than a chart.
This keeps the report renderable even before J5 ships (the spec calls
this out as the "single most important forensic-defensibility visual"
which therefore must always render *something*).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from plotly.graph_objects import Figure, Scatter
from plotly.subplots import make_subplots

# Method labels (string-typed because ``ChangePoint.method`` Literal does not
# yet enumerate the section-adjusted variants — the J5 writer will add them
# alongside this consumer).
RAW_METHODS: frozenset[str] = frozenset({"pelt", "bocpd"})
SECTION_ADJUSTED_METHODS: frozenset[str] = frozenset(
    {"pelt_section_adjusted", "bocpd_section_adjusted"}
)

# Stable visual constants (reviewed in tests so future restyles surface as diffs).
RAW_CP_COLOR = "red"
ADJUSTED_CP_COLOR = "blue"
RAW_CP_DASH = "dash"
ADJUSTED_CP_DASH = "solid"

# Notice rendered when J5 outputs are absent. Tests pin the exact prefix so
# downstream readers (and reviewers grepping the report) can detect the
# placeholder at a glance.
J5_PLACEHOLDER_PREFIX = "Section-adjusted CPs not computed"
J5_PLACEHOLDER_HTML = (
    f'<div class="cp-twin-panel-placeholder">'
    f"<p><strong>{J5_PLACEHOLDER_PREFIX} (J5 disabled).</strong> "
    "Enable <code>analysis.section_residualize_features</code> and rerun "
    "the analyze stage to populate the adjusted-vs-unadjusted change-point "
    "comparison.</p></div>"
)


@dataclass(frozen=True, slots=True)
class _ChangePointMark:
    """Minimal CP descriptor used by the renderer (decoupled from pydantic models).

    Decoupling lets tests build inputs without importing the analysis-layer
    model and lets the renderer accept either the model objects or plain
    dicts (e.g. when reading ``result.json`` for partial replay).
    """

    timestamp: datetime
    method: str


def _coerce_change_points(items: Iterable[object]) -> list[_ChangePointMark]:
    """Accept ChangePoint pydantic instances or dicts; return a uniform list.

    Robust to extra keys and method labels not in the current Literal — that
    is precisely the J5-forward-compat path the spec requires.
    """
    marks: list[_ChangePointMark] = []
    for item in items:
        if isinstance(item, _ChangePointMark):
            marks.append(item)
            continue
        ts = getattr(item, "timestamp", None)
        method = getattr(item, "method", None)
        if ts is None and isinstance(item, dict):
            ts = item.get("timestamp")
            method = item.get("method")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if not isinstance(ts, datetime) or not isinstance(method, str):
            continue
        marks.append(_ChangePointMark(timestamp=ts, method=method))
    return marks


def _split_by_source(
    marks: Sequence[_ChangePointMark],
) -> tuple[list[_ChangePointMark], list[_ChangePointMark]]:
    raw = [m for m in marks if m.method in RAW_METHODS]
    adjusted = [m for m in marks if m.method in SECTION_ADJUSTED_METHODS]
    return raw, adjusted


def _add_series(fig: Figure, x: Sequence[datetime], y: Sequence[float], row: int) -> None:
    fig.add_trace(
        Scatter(x=list(x), y=list(y), mode="lines", name="feature", showlegend=row == 1),
        row=row,
        col=1,
    )


def _add_cp_lines(
    fig: Figure,
    marks: Sequence[_ChangePointMark],
    *,
    row: int,
    color: str,
    dash: str,
) -> None:
    """Overlay vertical lines at each change-point on the given subplot row.

    Using ``add_shape`` with ``yref=f"y{row} domain"`` keeps the line spanning
    the full plot height without us having to compute y-axis bounds.
    """
    yref = "y domain" if row == 1 else f"y{row} domain"
    for mark in marks:
        fig.add_shape(
            type="line",
            x0=mark.timestamp,
            x1=mark.timestamp,
            xref=f"x{row}" if row > 1 else "x",
            yref=yref,
            y0=0,
            y1=1,
            line={"color": color, "dash": dash, "width": 1.5},
        )


def render_cp_twin_panel(
    *,
    author_slug: str,
    timestamps: Sequence[datetime],
    feature_series: Sequence[float],
    change_points: Iterable[object],
    feature_name: str = "stylometric feature",
) -> str:
    """Render an HTML fragment with the K4 twin-panel CP visualisation.

    Returns the J5 placeholder when no section-adjusted CPs are present.

    Top panel: ``feature_series`` with raw PELT/BOCPD CPs overlaid (dashed,
    red). Bottom panel: same series with section-adjusted CPs overlaid
    (solid, blue). Both panels share an x-axis so reviewers can read across
    them at a glance.
    """
    marks = _coerce_change_points(change_points)
    raw, adjusted = _split_by_source(marks)

    if not adjusted:
        # Spec K4: render the placeholder rather than crashing or omitting the
        # section. The reviewer should always see *something* about CP source.
        return J5_PLACEHOLDER_HTML

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=(
            f"Raw change-points ({feature_name})",
            f"Section-adjusted change-points ({feature_name})",
        ),
        vertical_spacing=0.12,
    )
    _add_series(fig, timestamps, feature_series, row=1)
    _add_series(fig, timestamps, feature_series, row=2)
    _add_cp_lines(fig, raw, row=1, color=RAW_CP_COLOR, dash=RAW_CP_DASH)
    _add_cp_lines(fig, adjusted, row=2, color=ADJUSTED_CP_COLOR, dash=ADJUSTED_CP_DASH)

    fig.update_layout(
        title=f"Change-points before vs after section residualization — {author_slug}",
        height=520,
        margin={"l": 40, "r": 20, "t": 80, "b": 40},
        showlegend=False,
    )

    return fig.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        div_id=f"cp-twin-panel-{author_slug}",
    )


__all__ = [
    "ADJUSTED_CP_COLOR",
    "ADJUSTED_CP_DASH",
    "J5_PLACEHOLDER_HTML",
    "J5_PLACEHOLDER_PREFIX",
    "RAW_CP_COLOR",
    "RAW_CP_DASH",
    "SECTION_ADJUSTED_METHODS",
    "render_cp_twin_panel",
]
