"""Plotly theme and annotation helpers for forensic notebooks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

import plotly.graph_objects as go
import plotly.io as pio

FORENSICS_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        template="plotly_white",
        font=dict(family="Inter, system-ui, sans-serif", size=12),
        title=dict(font=dict(size=16)),
        colorway=[
            "#1f77b4",
            "#ff7f0e",
            "#2ca02c",
            "#d62728",
            "#9467bd",
            "#8c564b",
            "#e377c2",
            "#7f7f7f",
            "#bcbd22",
            "#17becf",
        ],
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    ),
)

pio.templates["forensics"] = FORENSICS_TEMPLATE
pio.templates.default = "forensics"


def _coerce_date(value: datetime | date | str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def apply_change_point_annotations(
    fig: go.Figure,
    change_points: Sequence[datetime | date | str | Mapping[str, Any]],
    *,
    line_color: str = "#d62728",
    line_width: float = 1.5,
    line_dash: str = "dash",
) -> go.Figure:
    """Add vertical lines (and optional labels) for detected change points."""
    for cp in change_points:
        if isinstance(cp, Mapping):
            ts = cp.get("timestamp") or cp.get("date") or cp.get("time")
            label = str(cp.get("feature_name", cp.get("label", "")))
        else:
            ts = cp
            label = ""
        if ts is None:
            continue
        x0 = _coerce_date(ts)
        x_str = x0.isoformat()
        ann = label[:40] if label else None
        # ``add_vline`` fails when the figure axis is categorical/strings; shapes are robust.
        fig.add_shape(
            type="line",
            x0=x_str,
            x1=x_str,
            y0=0,
            y1=1,
            xref="x",
            yref="paper",
            line=dict(color=line_color, width=line_width, dash=line_dash),
            layer="above",
        )
        if ann:
            fig.add_annotation(
                x=x_str,
                y=1,
                xref="x",
                yref="paper",
                text=ann,
                showarrow=False,
                yanchor="bottom",
            )
    return fig


def apply_baseline_shading(
    fig: go.Figure,
    start: datetime | date | str,
    end: datetime | date | str,
    *,
    fillcolor: str = "rgba(99,110,250,0.12)",
    layer: str = "below",
) -> go.Figure:
    """Add a shaded rectangle for the baseline period."""
    s = _coerce_date(start)
    e = _coerce_date(end)
    fig.add_vrect(
        x0=s.isoformat(),
        x1=e.isoformat(),
        fillcolor=fillcolor,
        layer=layer,
        line_width=0,
    )
    return fig


def register_forensics_template(*, set_default: bool = True) -> None:
    """Register the forensic Plotly template (idempotent)."""
    pio.templates["forensics"] = FORENSICS_TEMPLATE
    if set_default:
        pio.templates.default = "forensics"
