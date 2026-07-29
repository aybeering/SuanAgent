"""Deterministic HTML view for strategy mark points on price series."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


MARKS_VIEW_SCHEMA_VERSION = "marks_view_v1"
YES_COLOR = "#0f766e"
FAIR_COLOR = "#94a3b8"
SIGNAL_COLOR = "#2563eb"
FILL_COLOR = "#dc2626"


def generate_marks_view(
    *,
    output_path: Path,
    run_id: str,
    workspace_id: str,
    split: str,
    market_csv_path: Path,
    mark_points: dict[str, Any],
) -> Path:
    """Write a dependency-free HTML page for price series plus mark overlays."""
    market_rows = load_market_rows(market_csv_path)
    marks = list(mark_points.get("marks", []))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_marks_view_html(
            run_id=run_id,
            workspace_id=workspace_id,
            split=split,
            market_rows=market_rows,
            mark_points=mark_points,
            marks=marks,
        ),
        encoding="utf-8",
    )
    return output_path


def load_market_rows(path: Path) -> list[dict[str, Any]]:
    """Load market CSV rows used for the price chart."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, Any]] = []
        for row in reader:
            rows.append(
                {
                    "timestamp": str(row.get("timestamp", "")),
                    "market_id": str(row.get("market_id", "")),
                    "yes_price": float(row.get("yes_price", 0.0) or 0.0),
                    "fair_value": float(row.get("fair_value", 0.0) or 0.0),
                }
            )
        return rows


def render_marks_view_html(
    *,
    run_id: str,
    workspace_id: str,
    split: str,
    market_rows: list[dict[str, Any]],
    mark_points: dict[str, Any],
    marks: list[dict[str, Any]],
) -> str:
    """Return deterministic HTML for the marks view artifact."""
    markets = sorted({str(row["market_id"]) for row in market_rows})
    if not markets:
        markets = sorted({str(mark.get("market_id", "")) for mark in marks if mark.get("market_id")})
    summary = summarize_marks(marks=marks, markets=markets, mark_points=mark_points)
    panels = []
    for market_id in markets:
        panels.append(
            render_market_panel(
                market_id=market_id,
                market_rows=[row for row in market_rows if row["market_id"] == market_id],
                marks=[mark for mark in marks if mark.get("market_id") == market_id],
            )
        )
    summary_comment = json.dumps(summary, sort_keys=True, separators=(",", ":"))
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f'<meta name="suan-marks-view-schema" content="{MARKS_VIEW_SCHEMA_VERSION}">',
            f"<title>Strategy Marks - {escape(run_id)} / {escape(workspace_id)}</title>",
            "<style>",
            marks_view_css(),
            "</style>",
            "</head>",
            "<body>",
            f"<!-- {MARKS_VIEW_SCHEMA_VERSION} -->",
            f"<!-- marks_summary:{summary_comment} -->",
            "<main>",
            "<header>",
            "<h1>Strategy Marks View</h1>",
            (
                f"<p>Run <strong>{escape(run_id)}</strong> / Workspace "
                f"<strong>{escape(workspace_id)}</strong> / Split "
                f"<strong>{escape(split)}</strong></p>"
            ),
            "</header>",
            render_summary_bar(summary),
            render_market_nav(markets),
            *panels,
            render_marks_table(marks),
            '<p class="note">Static local HTML. JSON contract in output/mark_points.json is authoritative.</p>',
            "</main>",
            "<script>",
            marks_view_js(),
            "</script>",
            "</body>",
            "</html>",
            "",
        ]
    )


def summarize_marks(
    *,
    marks: list[dict[str, Any]],
    markets: list[str],
    mark_points: dict[str, Any],
) -> dict[str, Any]:
    """Return compact summary counters for the HTML header and comment block."""
    buy_like = sum(1 for mark in marks if mark.get("action") in {"buy", "enter"})
    sell_like = sum(1 for mark in marks if mark.get("action") in {"sell", "exit"})
    signals = sum(1 for mark in marks if mark.get("kind") == "signal")
    fills = sum(1 for mark in marks if mark.get("kind") == "fill")
    return {
        "mark_count": len(marks),
        "buy_or_enter": buy_like,
        "sell_or_exit": sell_like,
        "signal_count": signals,
        "fill_count": fills,
        "market_count": len(markets),
        "input_digest_short": str(mark_points.get("input_digest", ""))[:12],
        "strategy_sha256_short": str(mark_points.get("strategy_sha256", ""))[:12],
    }


def render_summary_bar(summary: dict[str, Any]) -> str:
    """Return the top summary strip."""
    items = [
        ("Marks", summary["mark_count"]),
        ("Buy/Enter", summary["buy_or_enter"]),
        ("Sell/Exit", summary["sell_or_exit"]),
        ("Signals", summary["signal_count"]),
        ("Fills", summary["fill_count"]),
        ("Markets", summary["market_count"]),
        ("Input", summary["input_digest_short"]),
        ("Strategy", summary["strategy_sha256_short"]),
    ]
    cells = [
        (
            f'<div class="stat"><span class="label">{escape(label)}</span>'
            f'<span class="value">{escape(value)}</span></div>'
        )
        for label, value in items
    ]
    return '<section class="summary" aria-label="Marks summary">' + "".join(cells) + "</section>"


def render_market_nav(markets: list[str]) -> str:
    """Return market switcher controls."""
    if not markets:
        return '<nav class="market-nav"><span class="empty">No markets</span></nav>'
    buttons = []
    for index, market_id in enumerate(markets):
        selected = " selected" if index == 0 else ""
        buttons.append(
            f'<button type="button" class="market-btn{selected}" data-market="{escape(market_id)}">'
            f"{escape(market_id)}</button>"
        )
    return '<nav class="market-nav" aria-label="Market switcher">' + "".join(buttons) + "</nav>"


def render_market_panel(
    *,
    market_id: str,
    market_rows: list[dict[str, Any]],
    marks: list[dict[str, Any]],
) -> str:
    """Return one market chart panel."""
    return "\n".join(
        [
            f'<section class="panel market-panel" data-market-panel="{escape(market_id)}">',
            f"<h2>Market {escape(market_id)}</h2>",
            render_price_svg(market_id=market_id, market_rows=market_rows, marks=marks),
            '<p class="legend">'
            '<span class="swatch yes"></span> yes_price '
            '<span class="swatch fair"></span> fair_value '
            '<span class="swatch signal"></span> signal '
            '<span class="swatch fill"></span> fill'
            "</p>",
            "</section>",
        ]
    )


def render_price_svg(
    *,
    market_id: str,
    market_rows: list[dict[str, Any]],
    marks: list[dict[str, Any]],
) -> str:
    """Return an inline SVG price chart with mark overlays."""
    width = 960
    height = 360
    left = 54
    right = 24
    top = 24
    bottom = 40
    plot_width = width - left - right
    plot_height = height - top - bottom
    if not market_rows:
        return (
            f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="Empty price chart for {escape(market_id)}">'
            f'<text x="{left}" y="{top + 20}" fill="#64748b">No market rows</text></svg>'
        )

    yes_values = [float(row["yes_price"]) for row in market_rows]
    fair_values = [float(row["fair_value"]) for row in market_rows]
    mark_prices = [float(mark.get("price", 0.0) or 0.0) for mark in marks]
    values = yes_values + fair_values + mark_prices or [0.0]
    min_y = min(0.0, min(values))
    max_y = max(1.0, max(values))
    if min_y == max_y:
        min_y -= 0.05
        max_y += 0.05
    max_x = max(len(market_rows) - 1, 1)

    lines = [
        (
            f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="Price and marks for {escape(market_id)}">'
        ),
        f'<line class="axis" x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" />',
        (
            f'<line class="axis" x1="{left}" y1="{top + plot_height}" '
            f'x2="{left + plot_width}" y2="{top + plot_height}" />'
        ),
    ]
    for index in range(5):
        y = top + index * plot_height / 4
        value = max_y - index * (max_y - min_y) / 4
        lines.append(
            f'<line class="grid" x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" />'
        )
        lines.append(
            f'<text x="10" y="{y + 4:.2f}" font-size="12" fill="#475569">{value:.2f}</text>'
        )

    lines.append(
        f'<path class="series yes" d="{series_path(yes_values, min_y, max_y, max_x, left, top, plot_width, plot_height)}" />'
    )
    lines.append(
        f'<path class="series fair" d="{series_path(fair_values, min_y, max_y, max_x, left, top, plot_width, plot_height)}" />'
    )

    timestamp_to_index = {
        str(row["timestamp"]): index for index, row in enumerate(market_rows)
    }
    for mark in marks:
        ts = str(mark.get("timestamp", ""))
        if ts not in timestamp_to_index:
            continue
        index = timestamp_to_index[ts]
        x = left + (index / max_x) * plot_width
        y = scale_y(float(mark.get("price", 0.0) or 0.0), min_y, max_y, top, plot_height)
        kind = str(mark.get("kind", "signal"))
        action = str(mark.get("action", "buy"))
        mark_id = str(mark.get("mark_id", ""))
        color = FILL_COLOR if kind == "fill" else SIGNAL_COLOR
        if kind == "fill":
            lines.append(
                f'<circle class="mark fill" data-mark-id="{escape(mark_id)}" '
                f'cx="{x:.2f}" cy="{y:.2f}" r="6" fill="{color}" '
                f'stroke="#111827" stroke-width="1.5">'
                f'<title>{escape(mark_id)} {escape(action)} {escape(kind)}</title></circle>'
            )
        else:
            size = 7
            points = (
                f"{x:.2f},{y - size:.2f} {x + size:.2f},{y + size:.2f} "
                f"{x - size:.2f},{y + size:.2f}"
            )
            lines.append(
                f'<polygon class="mark signal" data-mark-id="{escape(mark_id)}" '
                f'points="{points}" fill="{color}" fill-opacity="0.85" '
                f'stroke="#111827" stroke-width="1">'
                f'<title>{escape(mark_id)} {escape(action)} {escape(kind)}</title></polygon>'
            )
    lines.append("</svg>")
    return "\n".join(lines)


def series_path(
    values: list[float],
    min_y: float,
    max_y: float,
    max_x: int,
    left: int,
    top: int,
    plot_width: int,
    plot_height: int,
) -> str:
    """Return an SVG path for one price series."""
    if not values:
        values = [0.0]
    commands = []
    for index, value in enumerate(values):
        x = left + (index / max_x) * plot_width
        y = scale_y(value, min_y, max_y, top, plot_height)
        command = "M" if index == 0 else "L"
        commands.append(f"{command}{x:.2f},{y:.2f}")
    return " ".join(commands)


def scale_y(
    value: float,
    min_y: float,
    max_y: float,
    top: int,
    plot_height: int,
) -> float:
    """Scale a data value into SVG y coordinates."""
    return top + (max_y - value) / (max_y - min_y) * plot_height


def render_marks_table(marks: list[dict[str, Any]]) -> str:
    """Return a filterable HTML table of mark points."""
    rows = []
    for mark in marks:
        mark_id = str(mark.get("mark_id", ""))
        rows.append(
            "<tr "
            f'data-mark-id="{escape(mark_id)}" '
            f'data-kind="{escape(mark.get("kind", ""))}" '
            f'data-action="{escape(mark.get("action", ""))}" '
            f'data-market="{escape(mark.get("market_id", ""))}">'
            f"<td>{escape(mark_id)}</td>"
            f"<td>{escape(mark.get('timestamp', ''))}</td>"
            f"<td>{escape(mark.get('market_id', ''))}</td>"
            f"<td>{escape(mark.get('kind', ''))}</td>"
            f"<td>{escape(mark.get('action', ''))}</td>"
            f"<td>{escape(mark.get('side', ''))}</td>"
            f"<td>{format_number(mark.get('price'))}</td>"
            f"<td>{format_number(mark.get('stake'))}</td>"
            f"<td>{format_number(mark.get('quantity'))}</td>"
            f"<td>{escape(mark.get('reason', ''))}</td>"
            "</tr>"
        )
    body = "\n".join(rows) if rows else '<tr><td colspan="10">No marks</td></tr>'
    return "\n".join(
        [
            '<section class="panel">',
            "<h2>Mark Points</h2>",
            '<div class="filters">',
            '<label>Kind <select id="filter-kind"><option value="">all</option>'
            '<option value="signal">signal</option><option value="fill">fill</option></select></label>',
            '<label>Action <select id="filter-action"><option value="">all</option>'
            '<option value="buy">buy</option><option value="sell">sell</option>'
            '<option value="enter">enter</option><option value="exit">exit</option></select></label>',
            '<label>Market <input id="filter-market" type="text" placeholder="market_id"></label>',
            "</div>",
            "<table id=\"marks-table\">",
            "<thead><tr>"
            "<th>mark_id</th><th>timestamp</th><th>market_id</th><th>kind</th>"
            "<th>action</th><th>side</th><th>price</th><th>stake</th>"
            "<th>quantity</th><th>reason</th>"
            "</tr></thead>",
            f"<tbody>\n{body}\n</tbody>",
            "</table>",
            "</section>",
        ]
    )


def marks_view_css() -> str:
    """Return compact CSS for the marks view page."""
    return f"""
:root {{
  color-scheme: light;
  --bg: #f1f5f9;
  --ink: #0f172a;
  --muted: #64748b;
  --panel: #ffffff;
  --line: #cbd5e1;
  --yes: {YES_COLOR};
  --fair: {FAIR_COLOR};
  --signal: {SIGNAL_COLOR};
  --fill: {FILL_COLOR};
  font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
}}
body {{ margin: 0; background: linear-gradient(180deg, #e2e8f0 0%, var(--bg) 220px); color: var(--ink); }}
main {{ max-width: 1100px; margin: 0 auto; padding: 28px 20px 48px; }}
header {{ margin-bottom: 16px; }}
h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: -0.02em; }}
h2 {{ margin: 0 0 12px; font-size: 18px; }}
p {{ margin: 0; color: var(--muted); }}
.summary {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 10px;
  margin: 16px 0;
}}
.stat {{
  background: rgba(255,255,255,0.9);
  border: 1px solid var(--line);
  padding: 10px 12px;
}}
.stat .label {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }}
.stat .value {{ display: block; margin-top: 4px; font-size: 18px; font-weight: 600; }}
.market-nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 4px; }}
.market-btn {{
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink);
  padding: 8px 12px;
  cursor: pointer;
}}
.market-btn.selected {{ background: #0f172a; color: #fff; border-color: #0f172a; }}
.panel {{
  background: var(--panel);
  border: 1px solid var(--line);
  padding: 18px;
  margin: 14px 0;
}}
.market-panel {{ display: none; }}
.market-panel.active {{ display: block; }}
.chart {{ width: 100%; height: auto; display: block; border: 1px solid #e2e8f0; background: #fff; }}
.axis {{ stroke: #94a3b8; stroke-width: 1; }}
.grid {{ stroke: #e2e8f0; stroke-width: 1; }}
.series {{ fill: none; stroke-width: 2.5; }}
.series.yes {{ stroke: var(--yes); }}
.series.fair {{ stroke: var(--fair); stroke-dasharray: 4 4; stroke-width: 1.5; }}
.legend {{ margin-top: 10px; color: var(--muted); font-size: 13px; }}
.swatch {{
  display: inline-block;
  width: 12px;
  height: 12px;
  margin: 0 4px 0 10px;
  vertical-align: -1px;
  border: 1px solid #334155;
}}
.swatch.yes {{ background: var(--yes); }}
.swatch.fair {{ background: var(--fair); }}
.swatch.signal {{ background: var(--signal); }}
.swatch.fill {{ background: var(--fill); border-radius: 50%; }}
.filters {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }}
label {{ color: var(--muted); font-size: 13px; }}
select, input {{ margin-left: 6px; padding: 6px 8px; border: 1px solid var(--line); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ border-bottom: 1px solid #e2e8f0; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #f8fafc; color: #334155; position: sticky; top: 0; }}
tr.highlight {{ background: #ecfeff; }}
.mark {{ cursor: pointer; }}
.note {{ color: var(--muted); font-size: 13px; margin-top: 8px; }}
""".strip()


def marks_view_js() -> str:
    """Return minimal inline JS for market switching and row highlighting."""
    return """
(function () {
  const panels = Array.from(document.querySelectorAll("[data-market-panel]"));
  const buttons = Array.from(document.querySelectorAll(".market-btn"));
  function showMarket(marketId) {
    panels.forEach((panel) => {
      panel.classList.toggle("active", panel.getAttribute("data-market-panel") === marketId);
    });
    buttons.forEach((button) => {
      button.classList.toggle("selected", button.getAttribute("data-market") === marketId);
    });
  }
  if (buttons.length) {
    showMarket(buttons[0].getAttribute("data-market"));
  }
  buttons.forEach((button) => {
    button.addEventListener("click", () => showMarket(button.getAttribute("data-market")));
  });
  const kind = document.getElementById("filter-kind");
  const action = document.getElementById("filter-action");
  const market = document.getElementById("filter-market");
  const rows = Array.from(document.querySelectorAll("#marks-table tbody tr[data-mark-id]"));
  function applyFilters() {
    const kindValue = kind ? kind.value : "";
    const actionValue = action ? action.value : "";
    const marketValue = market ? market.value.trim().toLowerCase() : "";
    rows.forEach((row) => {
      const okKind = !kindValue || row.getAttribute("data-kind") === kindValue;
      const okAction = !actionValue || row.getAttribute("data-action") === actionValue;
      const rowMarket = (row.getAttribute("data-market") || "").toLowerCase();
      const okMarket = !marketValue || rowMarket.indexOf(marketValue) !== -1;
      row.style.display = okKind && okAction && okMarket ? "" : "none";
    });
  }
  [kind, action, market].forEach((el) => {
    if (el) el.addEventListener("input", applyFilters);
    if (el) el.addEventListener("change", applyFilters);
  });
  document.querySelectorAll(".mark").forEach((node) => {
    node.addEventListener("click", () => {
      const markId = node.getAttribute("data-mark-id");
      rows.forEach((row) => {
        const match = row.getAttribute("data-mark-id") === markId;
        row.classList.toggle("highlight", match);
        if (match) row.scrollIntoView({ block: "nearest" });
      });
    });
  });
})();
""".strip()


def format_number(value: object) -> str:
    """Return stable numeric text for table cells."""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6f}"
    if value is None:
        return ""
    return escape(value)


def escape(value: object) -> str:
    """HTML-escape a value."""
    return html.escape(str(value), quote=True)
