"""
build_dashboard.py

The actual prototype: aggregates the mock crew-capacity / work-order-backlog /
five-year-forecast CSVs into (1) a capacity-vs-demand trend per region, (2) a
variance/status flag per region for the current month, and (3) a five-year
capital-plan trend per region -- then drafts the monthly capability narrative
that currently gets written by hand. Outputs one self-contained HTML dashboard
and one markdown report.

Run:
    python src/build_dashboard.py
Requires data/*.csv to exist first -- run generate_mock_data.py if they don't.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from narrative import generate_narrative

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ---- palette (validated categorical + status steps; see README) -----------
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"

CAT = {
    "blue": "#2a78d6",
    "orange": "#eb6834",
    "aqua": "#1baf7a",
    "yellow": "#eda100",
}
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "critical": "#d03b3b",
}
VARIANCE_THRESHOLDS = {"warning": 5.0, "critical": 15.0}  # percent


def classify(variance_pct: float) -> str:
    if variance_pct >= VARIANCE_THRESHOLDS["critical"]:
        return "critical"
    if variance_pct >= VARIANCE_THRESHOLDS["warning"]:
        return "warning"
    return "good"


def load_data():
    cap = pd.read_csv(DATA_DIR / "crew_capacity.csv")
    backlog = pd.read_csv(DATA_DIR / "work_order_backlog.csv")
    forecast = pd.read_csv(DATA_DIR / "five_year_forecast.csv")
    return cap, backlog, forecast


def aggregate(cap: pd.DataFrame, backlog: pd.DataFrame):
    demand_by_month = (
        backlog.groupby(["region", "month"])["required_hours"].sum().reset_index()
    )
    merged = cap.merge(demand_by_month, on=["region", "month"], how="left")
    merged["required_hours"] = merged["required_hours"].fillna(0)
    merged["variance_pct"] = (
        (merged["required_hours"] - merged["available_crew_hours"])
        / merged["available_crew_hours"]
        * 100
    )
    merged["status"] = merged["variance_pct"].apply(classify)
    merged = merged.sort_values(["region", "month"])
    return merged


def current_month_summary(merged: pd.DataFrame):
    latest_month = merged["month"].max()
    current = merged[merged["month"] == latest_month].copy()
    rows = [
        {
            "region": r.region,
            "required_hours": r.required_hours,
            "available_hours": r.available_crew_hours,
            "variance_pct": r.variance_pct,
            "status": r.status,
        }
        for r in current.itertuples()
    ]
    rows.sort(key=lambda r: r["variance_pct"], reverse=True)
    return rows, latest_month


# ---- chart 1: capacity vs. demand trend, small multiples per region -------
def build_trend_chart(merged: pd.DataFrame) -> go.Figure:
    regions = merged["region"].unique().tolist()
    fig = go.Figure()
    n = len(regions)
    # 2x2 grid via subplot-free trick: use plotly subplots for real small multiples
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=regions,
        shared_yaxes=False,
        horizontal_spacing=0.08,
        vertical_spacing=0.16,
    )
    positions = [(1, 1), (1, 2), (2, 1), (2, 2)]
    for (row, col), region in zip(positions, regions):
        sub = merged[merged["region"] == region]
        show_legend = (row, col) == (1, 1)
        fig.add_trace(
            go.Scatter(
                x=sub["month"],
                y=sub["available_crew_hours"],
                mode="lines+markers",
                name="Available capacity (crew-hours)",
                legendgroup="capacity",
                showlegend=show_legend,
                line=dict(color=CAT["blue"], width=2),
                marker=dict(size=6, color=CAT["blue"]),
                hovertemplate="%{x}<br>Capacity: %{y:,.0f} hrs<extra></extra>",
            ),
            row=row,
            col=col,
        )
        fig.add_trace(
            go.Scatter(
                x=sub["month"],
                y=sub["required_hours"],
                mode="lines+markers",
                name="Required demand (crew-hours)",
                legendgroup="demand",
                showlegend=show_legend,
                line=dict(color=CAT["orange"], width=2),
                marker=dict(size=6, color=CAT["orange"]),
                hovertemplate="%{x}<br>Demand: %{y:,.0f} hrs<extra></extra>",
            ),
            row=row,
            col=col,
        )

    fig.update_layout(
        title=dict(
            text="Capacity vs. Demand -- Trailing 12 Months by Region",
            font=dict(size=18, color=INK_PRIMARY),
        ),
        paper_bgcolor=PAGE,
        plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=INK_SECONDARY),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
        margin=dict(t=90, l=60, r=30, b=40),
        height=560,
    )
    fig.update_xaxes(showgrid=False, tickfont=dict(color=INK_MUTED, size=10))
    fig.update_yaxes(
        showgrid=True, gridcolor=GRIDLINE, zeroline=False, tickfont=dict(color=INK_MUTED, size=10)
    )
    for ann in fig["layout"]["annotations"]:
        ann["font"] = dict(size=13, color=INK_PRIMARY)
    return fig


# ---- chart 2: current-month variance / status by region -------------------
def build_variance_chart(summary_rows: list[dict], month_label: str) -> go.Figure:
    regions = [r["region"] for r in summary_rows]
    variances = [r["variance_pct"] for r in summary_rows]
    colors = [STATUS[r["status"]] for r in summary_rows]
    labels = [f"{r['status'].upper()} ({r['variance_pct']:+.1f}%)" for r in summary_rows]

    fig = go.Figure(
        go.Bar(
            x=variances,
            y=regions,
            orientation="h",
            marker=dict(color=colors),
            text=labels,
            textposition="outside",
            hovertemplate="%{y}<br>Variance: %{x:+.1f}%<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_width=1, line_color=INK_MUTED)
    fig.add_vline(
        x=VARIANCE_THRESHOLDS["warning"], line_width=1, line_dash="dot", line_color=STATUS["warning"]
    )
    fig.add_vline(
        x=VARIANCE_THRESHOLDS["critical"], line_width=1, line_dash="dot", line_color=STATUS["critical"]
    )
    fig.update_layout(
        title=dict(
            text=f"Demand vs. Capacity Variance -- {month_label} (negative = surplus capacity)",
            font=dict(size=18, color=INK_PRIMARY),
        ),
        paper_bgcolor=PAGE,
        plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=INK_SECONDARY),
        showlegend=False,
        margin=dict(t=70, l=140, r=100, b=50),
        height=320,
    )
    # Outside bar-end labels ("CRITICAL (+36.1%)") need headroom beyond the
    # longest bar or Plotly clips them at the plot-area edge -- pad the range
    # on whichever side the labels actually extend past.
    lo = min(variances + [0])
    hi = max(variances + [0])
    span = max(hi - lo, 1)
    fig.update_xaxes(
        title="Variance vs. available capacity (%)",
        showgrid=True,
        gridcolor=GRIDLINE,
        tickfont=dict(color=INK_MUTED, size=10),
        range=[lo - span * 0.4, hi + span * 0.4],
    )
    fig.update_yaxes(tickfont=dict(color=INK_PRIMARY, size=12))
    return fig


# ---- chart 3: five-year capital-plan forecast ------------------------------
def build_forecast_chart(forecast: pd.DataFrame) -> go.Figure:
    regions = forecast["region"].unique().tolist()
    color_order = [CAT["blue"], CAT["orange"], CAT["aqua"], CAT["yellow"]]
    fig = go.Figure()
    for region, color in zip(regions, color_order):
        sub = forecast[forecast["region"] == region]
        fig.add_trace(
            go.Scatter(
                x=sub["year"],
                y=sub["planned_hours"],
                mode="lines+markers+text",
                name=region,
                line=dict(color=color, width=2),
                marker=dict(size=8, color=color),
                text=[region if y == sub["year"].max() else "" for y in sub["year"]],
                textposition="middle right",
                textfont=dict(size=11, color=INK_PRIMARY),
                hovertemplate="%{x}<br>" + region + ": %{y:,.0f} planned hrs<extra></extra>",
            )
        )
    fig.update_layout(
        title=dict(
            text="Five-Year Capital-Plan Hours Forecast by Region",
            font=dict(size=18, color=INK_PRIMARY),
        ),
        paper_bgcolor=PAGE,
        plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=INK_SECONDARY),
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        margin=dict(t=90, l=60, r=90, b=40),
        height=420,
    )
    # Direct end-of-line region labels ("Brooklyn/Queens") need room past the
    # last year's data point or Plotly clips them at the plot-area edge.
    years = forecast["year"].unique().tolist()
    fig.update_xaxes(
        showgrid=False,
        tickfont=dict(color=INK_MUTED, size=10),
        dtick=1,
        range=[min(years) - 0.4, max(years) + 1.6],
    )
    fig.update_yaxes(
        title="Planned annual hours",
        showgrid=True,
        gridcolor=GRIDLINE,
        tickfont=dict(color=INK_MUTED, size=10),
    )
    return fig


def build_variance_table_html(summary_rows: list[dict]) -> str:
    """Plain HTML table -- the accessibility 'table view' companion to chart 2."""
    rows_html = ""
    for r in summary_rows:
        rows_html += (
            f"<tr><td>{r['region']}</td>"
            f"<td>{r['required_hours']:,.0f}</td>"
            f"<td>{r['available_hours']:,.0f}</td>"
            f"<td>{r['variance_pct']:+.1f}%</td>"
            f"<td><span class='status-pill status-{r['status']}'>{r['status'].upper()}</span></td></tr>\n"
        )
    return f"""
    <table class="data-table">
      <thead>
        <tr><th>Region</th><th>Required hrs</th><th>Available hrs</th><th>Variance</th><th>Status</th></tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8" />
<title>Electric Operations -- Monthly Capability Dashboard (Prototype)</title>
<style>
  body {{
    margin: 0;
    background: {page};
    color: {ink_primary};
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 32px 24px 64px; }}
  header h1 {{ font-size: 22px; margin-bottom: 4px; }}
  header p {{ color: {ink_secondary}; margin-top: 0; }}
  .banner {{
    background: #fff8e6; border: 1px solid #f0d98a; border-radius: 8px;
    padding: 12px 16px; font-size: 13px; color: {ink_secondary}; margin-bottom: 24px;
  }}
  .card {{
    background: {surface}; border: 1px solid {gridline}; border-radius: 10px;
    padding: 16px; margin-bottom: 28px;
  }}
  .data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }}
  .data-table th, .data-table td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid {gridline}; }}
  .data-table th {{ color: {ink_muted}; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.02em; }}
  .status-pill {{ padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; color: #fff; }}
  .status-good {{ background: {good}; }}
  .status-warning {{ background: {warning}; color: {ink_primary}; }}
  .status-critical {{ background: {critical}; }}
  .narrative {{ white-space: pre-wrap; line-height: 1.55; font-size: 14px; }}
  footer {{ color: {ink_muted}; font-size: 12px; margin-top: 24px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Electric Operations, Programs &amp; Project Planning</h1>
    <p>Monthly Capability Dashboard -- prototype, generated {generated_note}</p>
  </header>
  <div class="banner">
    This is a demo built on fabricated data to illustrate an automation concept -- it
    is not affiliated with, endorsed by, or built from any real Con Edison data or systems.
    See the README for what it's demonstrating and why.
  </div>

  <div class="card">{chart1}</div>
  <div class="card">
    {chart2}
    {table}
  </div>
  <div class="card">{chart3}</div>

  <div class="card">
    <h2>Monthly Capability Report (auto-drafted)</h2>
    <div class="narrative">{narrative}</div>
  </div>

  <footer>Generated by build_dashboard.py -- see the repo README for how to regenerate this with fresh mock data.</footer>
</div>
</body>
</html>
"""


def main():
    cap, backlog, forecast = load_data()
    merged = aggregate(cap, backlog)
    summary_rows, latest_month = current_month_summary(merged)

    fig1 = build_trend_chart(merged)
    fig2 = build_variance_chart(summary_rows, latest_month)
    fig3 = build_forecast_chart(forecast)

    narrative_md = generate_narrative(summary_rows, latest_month)
    (OUTPUT_DIR / "monthly_capability_report.md").write_text(narrative_md)

    # narrative body without the H1 (the HTML page already has its own headers)
    narrative_body = "\n".join(narrative_md.split("\n")[1:]).strip()

    html = PAGE_TEMPLATE.format(
        page=PAGE,
        ink_primary=INK_PRIMARY,
        ink_secondary=INK_SECONDARY,
        ink_muted=INK_MUTED,
        surface=SURFACE,
        gridline=GRIDLINE,
        good=STATUS["good"],
        warning=STATUS["warning"],
        critical=STATUS["critical"],
        generated_note=f"for reporting month {latest_month}",
        chart1=fig1.to_html(include_plotlyjs=True, full_html=False),
        chart2=fig2.to_html(include_plotlyjs=False, full_html=False),
        table=build_variance_table_html(summary_rows),
        chart3=fig3.to_html(include_plotlyjs=False, full_html=False),
        narrative=narrative_body,
    )

    out_path = OUTPUT_DIR / "capability_dashboard.html"
    out_path.write_text(html)
    print(f"Wrote {out_path}")
    print(f"Wrote {OUTPUT_DIR / 'monthly_capability_report.md'}")
    print("\nCurrent-month status by region:")
    for r in summary_rows:
        print(f"  {r['region']:<18} variance {r['variance_pct']:+6.1f}%  -> {r['status']}")


if __name__ == "__main__":
    main()
