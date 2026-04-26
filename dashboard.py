"""
Tellico River — Interactive Dashboard
======================================
Generates a self-contained HTML file with a zoomable Plotly chart.

Usage:
    python dashboard.py           # predict with saved model
    python dashboard.py retrain   # retrain then show dashboard
"""

import argparse
import subprocess
import numpy as np
import pandas as pd
from datetime import timedelta

import plotly.graph_objects as go

from tellico_predictor import (
    run_prediction,
    PADDABLE_MIN_CFS,
    PADDABLE_MAX_CFS,
    SWEET_SPOT_MIN,
    SWEET_SPOT_MAX,
    USGS_GAUGE_ID,
)

HISTORY_SHOW_DAYS = 7       # days of actual gauge data shown left of "now"
OUTPUT_HTML       = "tellico_dashboard.html"


# ---------------------------------------------------------------------------
# Figure builder
# ---------------------------------------------------------------------------

def build_figure(results: dict) -> go.Figure:
    gauge_hist  = results["gauge_hist"]
    forecast    = results["hourly"]
    precip_hist = results["precip_hist"]

    now_ts     = forecast.index[0]
    hist_start = now_ts - timedelta(days=HISTORY_SHOW_DAYS)
    actual     = gauge_hist[gauge_hist.index >= hist_start]

    # Precip — combined historical + forecast as a single series
    p_hist    = precip_hist[precip_hist.index >= hist_start]
    p_fcast   = forecast[["precip_mm"]]
    all_precip = (
        pd.concat([p_hist, p_fcast])
        .pipe(lambda d: d[~d.index.duplicated(keep="last")])
        .sort_index()
    )

    # Default view: yesterday → 2 days out
    default_start = (now_ts - timedelta(days=1)).isoformat()
    default_end   = (now_ts + timedelta(days=2)).isoformat()

    # -----------------------------------------------------------------------
    # Layout — single panel, mobile-first
    # -----------------------------------------------------------------------
    fig = go.Figure()

    fig.update_layout(
        paper_bgcolor="#0f0f1a",
        plot_bgcolor="#13132a",
        font=dict(color="#c0c0c0", family="system-ui, -apple-system, sans-serif", size=14),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#1a1a2e",
            bordercolor="#42a5f5",
            font_color="#ffffff",
            font_size=14,
            namelength=-1,
        ),
        showlegend=False,
        height=580,
        margin=dict(l=0, r=0, t=48, b=48),
        xaxis=dict(
            range=[default_start, default_end],
            showgrid=True,
            gridcolor="#1e1e38",
            gridwidth=1,
            tickformat="%-I%p\n%b %-d",
            tickfont=dict(size=16, color="#ffffff"),
            tickcolor="#444",
            linecolor="#333",
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#1e1e38",
            gridwidth=1,
            tickformat=",d",
            tickfont=dict(size=16, color="#ffffff"),
            tickcolor="rgba(0,0,0,0)",
            linecolor="#333",
            zeroline=False,
            ticklabelposition="inside",
            ticks="inside",
        ),
    )

    # -----------------------------------------------------------------------
    # Paddable / sweet-spot zones
    # -----------------------------------------------------------------------
    fig.add_hrect(
        y0=PADDABLE_MIN_CFS, y1=PADDABLE_MAX_CFS,
        fillcolor="#2e7d32", opacity=0.12, line_width=0,
    )
    fig.add_hrect(
        y0=SWEET_SPOT_MIN, y1=SWEET_SPOT_MAX,
        fillcolor="#66bb6a", opacity=0.22, line_width=0,
    )
    # Boundary lines
    fig.add_hline(y=PADDABLE_MIN_CFS, line_dash="dot", line_color="#66bb6a", opacity=0.5, line_width=1)
    fig.add_hline(y=PADDABLE_MAX_CFS, line_dash="dot", line_color="#ef9a9a", opacity=0.5, line_width=1)

    # Zone labels (right-anchored so they don't block the data)
    for label, y, color in [
        ("SWEET SPOT", (SWEET_SPOT_MIN + SWEET_SPOT_MAX) / 2, "#66bb6a"),
        ("PADDABLE",   PADDABLE_MIN_CFS + 5,                  "#81c784"),
    ]:
        fig.add_annotation(
            x=1, xref="paper", xanchor="right",
            y=y, yref="y",
            text=label,
            showarrow=False,
            font=dict(size=9, color=color),
            opacity=0.7,
            bgcolor="rgba(0,0,0,0)",
        )

    # -----------------------------------------------------------------------
    # Precipitation — subtle bars along the bottom as an overlay
    # -----------------------------------------------------------------------
    precip_in = (all_precip["precip_mm"] / 25.4).round(3)
    precip_max = max(precip_in.max(), 0.01)
    # Scale precip to occupy the bottom 15% of the CFS y-range
    y_all = pd.concat([actual["cfs"], forecast["predicted_cfs"]])
    y_min = max(0, y_all.min() * 0.85)
    y_max = y_all.max() * 1.1
    precip_scaled = y_min + (precip_in / precip_max) * (y_max - y_min) * 0.12

    fig.add_trace(go.Bar(
        x=all_precip.index,
        y=precip_scaled,
        base=y_min,
        name="Rain",
        marker_color=np.where(all_precip.index < now_ts, "#5c6bc0", "#9575cd"),
        marker_line_width=0,
        opacity=0.6,
        hovertemplate="🌧 %{customdata:.2f}\"<extra></extra>",
        customdata=(all_precip["precip_mm"] / 25.4).round(3),
    ))

    # -----------------------------------------------------------------------
    # "Now" line
    # -----------------------------------------------------------------------
    fig.add_vline(
        x=now_ts,
        line_dash="solid",
        line_color="rgba(255,255,255,0.25)",
        line_width=1,
    )
    fig.add_annotation(
        x=now_ts, y=1, yref="paper",
        text="NOW",
        showarrow=False,
        font=dict(size=9, color="rgba(255,255,255,0.45)"),
        xanchor="left", yanchor="top",
        xshift=4,
    )

    # -----------------------------------------------------------------------
    # Actual CFS
    # -----------------------------------------------------------------------
    fig.add_trace(go.Scatter(
        x=actual.index,
        y=actual["cfs"].round(0),
        name="Actual",
        line=dict(color="#42a5f5", width=2.5),
        hovertemplate="<b>%{y:,d} CFS</b><extra>Actual</extra>",
    ))

    # -----------------------------------------------------------------------
    # Forecast CFS
    # -----------------------------------------------------------------------
    fig.add_trace(go.Scatter(
        x=forecast.index,
        y=forecast["predicted_cfs"].round(0),
        name="Forecast",
        line=dict(color="#ef5350", width=2.5, dash="dot"),
        hovertemplate="<b>%{y:,d} CFS</b><extra>Forecast</extra>",
    ))

    # Fix y-range so precip bars don't distort the scale
    fig.update_yaxes(range=[y_min * 0.9, y_max])

    return fig


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_dashboard(results: dict, output: str = OUTPUT_HTML):
    fig = build_figure(results)
    fig.write_html(
        output,
        include_plotlyjs="cdn",
        full_html=True,
        config={
            "scrollZoom": True,
            "displayModeBar": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            "toImageButtonOptions": {"filename": "tellico_forecast"},
        },
    )
    print(f"Dashboard saved → {output}")
    try:
        subprocess.Popen(["open", output])
    except Exception:
        print(f"Open {output} in your browser to view the dashboard.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tellico River interactive dashboard")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["predict", "retrain"],
        default="predict",
        help="predict: use saved model (default); retrain: retrain from scratch",
    )
    args = parser.parse_args()
    results = run_prediction(retrain=(args.command == "retrain"), verbose=True)
    generate_dashboard(results)
