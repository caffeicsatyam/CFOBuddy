import json
import os
import re
from datetime import datetime
from typing import Literal, Optional, Union
from pathlib import Path

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from langchain_core.tools import tool

try:
    from models.chart import Chart, Session
    DB_ENABLED = Session is not None
except ImportError:
    DB_ENABLED = False

CHART_STORAGE_PATH = Path("static/charts")
CHART_STORAGE_PATH.mkdir(parents=True, exist_ok=True)


# ── Chart builder ──────────────────────────────────────────────────────────────

def _create_chart_html(
    chart_type: str,
    title: str,
    data: list[dict],
    x_label: str,
    y_label: str,
    description: str,
) -> str:
    """
    Build an interactive Plotly chart and save as a self-contained HTML file.
    Returns the file path string, or raises on failure.
    """
    keys   = list(data[0].keys())
    x_key  = keys[0]
    y_key  = keys[1] if len(keys) > 1 else keys[0]

    x_values = [item[x_key] for item in data]
    y_values = [item[y_key] for item in data]

    # ── Build figure based on chart type ──────────────────────────────────────
    if chart_type == "line":
        fig = go.Figure(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines+markers",
                line=dict(width=2, color="#4F8EF7"),
                marker=dict(size=6),
                hovertemplate=f"{x_label}: %{{x}}<br>{y_label}: %{{y:,.2f}}<extra></extra>",
            )
        )

    elif chart_type == "bar":
        fig = go.Figure(
            go.Bar(
                x=x_values,
                y=y_values,
                marker_color="#4F8EF7",
                hovertemplate=f"{x_label}: %{{x}}<br>{y_label}: %{{y:,.2f}}<extra></extra>",
            )
        )

    elif chart_type == "scatter":
        fig = go.Figure(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="markers",
                marker=dict(size=10, color="#4F8EF7", opacity=0.7),
                hovertemplate=f"{x_label}: %{{x}}<br>{y_label}: %{{y:,.2f}}<extra></extra>",
            )
        )

    elif chart_type == "area":
        fig = go.Figure(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines",
                fill="tozeroy",
                line=dict(width=2, color="#4F8EF7"),
                fillcolor="rgba(79,142,247,0.15)",
                hovertemplate=f"{x_label}: %{{x}}<br>{y_label}: %{{y:,.2f}}<extra></extra>",
            )
        )

    elif chart_type == "pie":
        fig = go.Figure(
            go.Pie(
                labels=x_values,
                values=y_values,
                hole=0.35,          # donut style — easier to read than full pie
                textinfo="label+percent",
                hovertemplate="%{label}: %{value:,.2f} (%{percent})<extra></extra>",
            )
        )

    elif chart_type == "histogram":
        fig = go.Figure(
            go.Histogram(
                x=y_values,
                marker_color="#4F8EF7",
                hovertemplate=f"Range: %{{x}}<br>Count: %{{y}}<extra></extra>",
            )
        )

    elif chart_type == "heatmap":
        # Expects data with keys: [row_key, col_key, value_key]
        if len(keys) >= 3:
            z_key    = keys[2]
            rows     = sorted(set(item[x_key] for item in data))
            cols     = sorted(set(item[y_key] for item in data))
            z_matrix = [[0.0] * len(cols) for _ in rows]
            for item in data:
                r = rows.index(item[x_key])
                c = cols.index(item[y_key])
                z_matrix[r][c] = item.get(z_key, 0)
            fig = go.Figure(
                go.Heatmap(
                    z=z_matrix,
                    x=cols,
                    y=rows,
                    colorscale="Blues",
                    hovertemplate=f"{x_key}: %{{y}}<br>{y_key}: %{{x}}<br>Value: %{{z:,.2f}}<extra></extra>",
                )
            )
        else:
            # Fallback to bar if not enough keys
            fig = go.Figure(go.Bar(x=x_values, y=y_values, marker_color="#4F8EF7"))
    else:
        # Fallback — unknown type → line
        fig = go.Figure(go.Scatter(x=x_values, y=y_values, mode="lines+markers"))

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        title=dict(text=title, font=dict(size=18, family="Arial"), x=0.5, xanchor="center"),
        xaxis_title=x_label if chart_type not in ("pie", "histogram") else "",
        yaxis_title=y_label if chart_type not in ("pie",) else "",
        template="plotly_white",
        hovermode="x unified" if chart_type in ("line", "area") else "closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=30, t=80, b=60),
        font=dict(family="Arial", size=12),
        # Subtle grid
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        # Annotations for description
        annotations=[
            dict(
                text=description,
                xref="paper", yref="paper",
                x=0.5, y=-0.12,
                showarrow=False,
                font=dict(size=11, color="#888"),
                xanchor="center",
            )
        ] if description else [],
    )

    # Rotate x-axis labels on bar/line if many points
    if chart_type in ("bar", "line", "area", "scatter") and len(x_values) > 12:
        fig.update_xaxes(tickangle=-45)

    # ── Save ──────────────────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename  = f"chart_{timestamp}.html"
    filepath  = CHART_STORAGE_PATH / filename

    # include_plotlyjs="cdn" keeps the file small (~10KB vs ~3MB);
    # the browser fetches plotly.js from CDN on first open.
    # Use include_plotlyjs=True if you need fully offline charts.
    fig.write_html(
        str(filepath),
        include_plotlyjs="cdn",
        full_html=True,
        config={
            "displayModeBar": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            "toImageButtonOptions": {
                "format": "png",
                "filename": filename.replace(".html", ""),
                "height": 600,
                "width": 1200,
                "scale": 2,
            },
        },
    )

    return str(filepath)


# ── Tools ──────────────────────────────────────────────────────────────────────

@tool
def generate_chart(
    chart_type: Literal["bar", "line", "pie", "scatter", "area", "histogram", "heatmap"],
    title: str,
    data: Union[list[dict], str],
    x_label: str = "",
    y_label: str = "",
    description: str = "",
    thread_id: Optional[str] = None,
) -> str:
    """
    Generate an interactive Plotly chart and save as an HTML file.

    Use this tool when:
    - User asks to visualize data
    - Showing trends over time           → "line" or "area"
    - Comparing categories               → "bar"
    - Showing proportions / breakdown    → "pie"
    - Showing correlations               → "scatter"
    - Showing value distributions        → "histogram"
    - Showing a matrix of values         → "heatmap"

    Args:
        chart_type:  One of bar, line, pie, scatter, area, histogram, heatmap
        title:       Clear, descriptive chart title
        data:        List of dicts OR JSON string.
                     Example: [{"month": "Jan", "revenue": 1000}, ...]
                     For heatmap, provide three keys: [row, col, value]
        x_label:     X-axis label (e.g. "Month", "Date")
        y_label:     Y-axis label (e.g. "Revenue ($M)", "Count")
        description: Optional subtitle / annotation shown below the chart
        thread_id:   Optional conversation thread ID for tracking

    Returns:
        Confirmation message with file path and URL.
        Charts are interactive HTML — users can zoom, pan, hover, and download as PNG.
    """
    # Parse JSON string if needed
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            return f"Chart Error: Invalid JSON data — {e}"

    if not data:
        return "Chart Error: No data provided."
    if not isinstance(data, list):
        return f"Chart Error: data must be a list, got {type(data).__name__}."
    if not all(isinstance(item, dict) for item in data):
        return "Chart Error: every item in data must be a dict."

    # Enforce consistent keys
    if len(data) > 1:
        first_keys = set(data[0].keys())
        if not all(set(item.keys()) == first_keys for item in data):
            return "Chart Error: all data items must have the same keys."

    # Cap at 500 points (Plotly handles more than matplotlib, but keep it sane)
    original_count = len(data)
    if len(data) > 500:
        data  = data[:500]
        title = f"{title} (first 500 of {original_count} points)"

    try:
        chart_path = _create_chart_html(
            chart_type=chart_type,
            title=title,
            data=data,
            x_label=x_label or "X-Axis",
            y_label=y_label or "Y-Axis",
            description=description,
        )
    except Exception as e:
        return f"Chart Error: Failed to generate chart — {e}"

    chart_filename = Path(chart_path).name
    chart_url      = f"/charts/{chart_filename}"

    if DB_ENABLED:
        try:
            session      = Session()
            chart_record = Chart(
                chart_type  = chart_type,
                title       = title,
                file_path   = chart_path,
                file_url    = chart_url,
                x_label     = x_label or "X-Axis",
                y_label     = y_label or "Y-Axis",
                description = description or f"{chart_type.capitalize()} chart: {title}",
                data_points = len(data),
                thread_id   = thread_id,
            )
            session.add(chart_record)
            session.commit()
            session.close()
        except Exception as db_error:
            print(f"Warning: could not save chart to database: {db_error}")

    chart_meta = json.dumps({"url": chart_url, "title": title, "type": chart_type})

    return (
        f"Chart created successfully!\n\n"
        f"**{title}**\n"
        f"- Type:        {chart_type.capitalize()} (interactive Plotly)\n"
        f"- Data points: {len(data)}\n"
        f"- URL:         `{chart_url}`\n\n"
        f"The chart is an interactive HTML file. Users can zoom, pan, hover for values, "
        f"and download as PNG via the toolbar.\n\n"
        f"CHART_JSON:{chart_meta}"
    )


@tool
def prepare_chart_data(
    sql_result: str,
    x_column: str,
    y_column: str,
    limit: int = 100,
) -> str:
    """
    Transform a sql_query result or get_financial_data history result into JSON ready for generate_chart.
    Call this BEFORE generate_chart when working from SQL output or stock price history.

    Args:
        sql_result: The formatted result string returned by sql_query or get_financial_data(data_type="history")
        x_column:   Column name to use as x-axis / labels
        y_column:   Column name to use as y-axis / values
        limit:      Max data points to return (default 100)

    Returns:
        JSON string of [{x_column: ..., y_column: ...}, ...] ready for generate_chart
    """
    try:
        finance_data = _parse_finance_history(sql_result, x_column, y_column, limit)
        if finance_data:
            return json.dumps(finance_data)

        lines = sql_result.strip().split("\n")

        # Find the header line (contains | but not a separator)
        header_line = next(
            (i for i, l in enumerate(lines) if "|" in l and not l.strip().startswith("-")),
            None,
        )
        if header_line is None:
            return json.dumps([])

        headers    = [h.strip() for h in lines[header_line].split("|")]
        data_start = header_line + 2  # skip separator line

        data = []
        for line in lines[data_start:]:
            if not line.strip() or not "|" in line or line.strip().startswith("..."):
                continue
            values = [v.strip() for v in line.split("|")]
            if len(values) != len(headers):
                continue
            row = dict(zip(headers, values))
            if x_column in row and y_column in row:
                data.append({
                    x_column: row[x_column],
                    y_column: _parse_number(row[y_column]),
                })
            if len(data) >= limit:
                break

        return json.dumps(data)

    except Exception:
        return json.dumps([])


def _parse_finance_history(result: str, x_column: str, y_column: str, limit: int) -> list[dict]:
    """Parse get_financial_data(data_type='history') output into chart rows."""
    metric_aliases = {
        "open": "open",
        "o": "open",
        "high": "high",
        "h": "high",
        "low": "low",
        "l": "low",
        "close": "close",
        "c": "close",
        "price": "close",
        "volume": "volume",
        "v": "volume",
    }
    requested_metric = metric_aliases.get(y_column.strip().lower(), y_column.strip().lower())
    x_key = x_column.strip() or "datetime"
    y_key = y_column.strip() or requested_metric
    rows: list[dict] = []

    for raw_line in result.strip().splitlines():
        line = raw_line.strip()
        if "|" not in line or line.lower().startswith("price history"):
            continue

        date_part, values_part = line.split("|", 1)
        values: dict[str, object] = {}
        for key, value in re.findall(r"\b([OHLCV]):\s*([^\s]+)", values_part, flags=re.IGNORECASE):
            normalized_key = metric_aliases.get(key.strip().lower())
            if normalized_key:
                values[normalized_key] = _parse_number(value)

        if requested_metric in values:
            rows.append({x_key: date_part.strip(), y_key: values[requested_metric]})
            if len(rows) >= limit:
                break

    return sorted(rows, key=lambda row: str(row.get(x_key, "")))


def _parse_number(value: str):
    """Parse a formatted number string to float; return original string if not numeric."""
    try:
        return float(value.replace(",", "").replace("$", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return value


@tool
def list_charts(thread_id: Optional[str] = None, limit: int = 10) -> str:
    """
    List recently created charts, optionally filtered by conversation thread.

    Args:
        thread_id: Optional thread ID to filter by conversation
        limit:     Max charts to return (default 10)
    """
    if not DB_ENABLED:
        # Fall back to listing files on disk
        files = sorted(CHART_STORAGE_PATH.glob("chart_*.html"), reverse=True)[:limit]
        if not files:
            return "No charts found."
        result = [{"file": f.name, "url": f"/charts/{f.name}"} for f in files]
        return json.dumps(result, indent=2)

    try:
        session = Session()
        query   = session.query(Chart)
        if thread_id:
            query = query.filter(Chart.thread_id == thread_id)
        charts     = query.order_by(Chart.created_at.desc()).limit(limit).all()
        chart_list = [chart.to_dict() for chart in charts]
        session.close()
        return json.dumps(chart_list, indent=2) if chart_list else "No charts found."
    except Exception as e:
        return f"Error listing charts: {e}"
