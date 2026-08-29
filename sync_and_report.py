#!/usr/bin/env python3
"""Daily sync + report for the GitHub Actions pipeline.

Reads the committed CSV snapshot, incrementally pulls new Tushare quotes,
recomputes the accumulation backtest, then writes CSV + SVG artifacts that
the workflow commits back to the repository.

The CSV files committed to Git are the durable "database" here; nothing needs
a local SQLite file or a long-lived market.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import market  # reuse ASSETS / fetch / clean / compute logic


ROOT = Path(__file__).resolve().parent
EXPORT_DIR = ROOT / "data" / "export"
RETURNS_CSV = EXPORT_DIR / "daily_returns.csv"
NAV_SVG = EXPORT_DIR / "nav.svg"
RETURNS_SVG = EXPORT_DIR / "returns.svg"
DAILY_CARD_SVG = EXPORT_DIR / "daily-card.svg"

DAILY_AMOUNT = 100.0            # 每只标的每日投入金额
START_DATE = date(2014, 1, 15)  # 三只 ETF 的共同历史起点

QUOTE_FIELDS = [
    "trade_date", "open", "high", "low", "close",
    "pre_close", "change", "pct_chg", "vol", "amount",
]


def quotes_path(asset_key: str) -> Path:
    """One CSV file per asset: data/export/<asset_key>.csv."""
    return EXPORT_DIR / f"{asset_key}.csv"
RETURN_FIELDS = [
    "asset_key", "trade_date", "daily_return_pct", "cumulative_return_pct", "wealth",
]

COLORS = {
    "portfolio": "#9ee5c9",
    "csi300": "#7fb2ff",
    "spx": "#ffd27f",
    "gold": "#f4a261",
}


# ---------------------------------------------------------------- CSV I/O

def load_quotes_csv() -> dict[str, dict[str, dict[str, Any]]]:
    """Return {asset_key: {trade_date: quote_row}} from the per-asset CSVs."""
    data: dict[str, dict[str, dict[str, Any]]] = {key: {} for key in market.ASSETS}
    for key in market.ASSETS:
        path = quotes_path(key)
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("trade_date"):
                    data[key][row["trade_date"]] = row
    return data


def save_quotes_csv(data: dict[str, dict[str, dict[str, Any]]]) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    for key in market.ASSETS:
        with quotes_path(key).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=QUOTE_FIELDS)
            writer.writeheader()
            for trade_date in sorted(data[key]):
                writer.writerow(data[key][trade_date])


def save_returns_csv(rows: list[dict[str, Any]]) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r["asset_key"], r["trade_date"]))
    with RETURNS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RETURN_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------- Sync

def sync_incremental(data: dict[str, dict[str, dict[str, Any]]]) -> int:
    """Pull any quotes newer than the CSV snapshot; returns number of new rows."""
    today = date.today()
    new_count = 0
    for key, asset in market.ASSETS.items():
        dates = data[key]
        if dates:
            start = date.fromisoformat(max(dates)) + timedelta(days=1)
        else:
            start = date.fromisoformat(asset["list_date"])
        if start > today:
            continue
        cleaned = market.clean_quote_rows(
            market.fetch_tushare_quotes(asset, start, today), start, today
        )
        for row in cleaned:
            data[key][row["trade_date"]] = row
            new_count += 1
    return new_count


# ---------------------------------------------------------------- Reporting

def compute_portfolio(curves: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Equal-weight portfolio wealth (forward-filled) across the three assets."""
    by_date: dict[str, dict[str, float]] = {}
    for key, curve in curves.items():
        for point in curve:
            by_date.setdefault(point["date"], {})[key] = point["wealth"]

    last_wealth = {key: 1.0 for key in curves}
    portfolio: list[dict[str, Any]] = []
    previous: float | None = None
    for trade_date in sorted(by_date):
        for key in curves:
            if key in by_date[trade_date]:
                last_wealth[key] = by_date[trade_date][key]
        wealth = sum(last_wealth.values()) / len(last_wealth)
        daily_return = (wealth / previous - 1.0) * 100.0 if previous else 0.0
        portfolio.append({
            "date": trade_date,
            "wealth": wealth,
            "daily_return_pct": daily_return,
        })
        previous = wealth
    return portfolio


def build_returns_rows(curves: dict[str, list[dict[str, Any]]],
                       portfolio: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in market.ASSETS:
        for point in curves[key]:
            rows.append({
                "asset_key": key,
                "trade_date": point["date"],
                "daily_return_pct": point["daily_return_pct"],
                "cumulative_return_pct": round((point["wealth"] - 1.0) * 100.0, 4),
                "wealth": point["wealth"],
            })
    for point in portfolio:
        rows.append({
            "asset_key": "portfolio",
            "trade_date": point["date"],
            "daily_return_pct": round(point["daily_return_pct"], 4),
            "cumulative_return_pct": round((point["wealth"] - 1.0) * 100.0, 4),
            "wealth": round(point["wealth"], 8),
        })
    return rows


# ---------------------------------------------------------------- SVG

def _escape(text: Any) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_line_chart(path: Path, title: str, series_list: list[dict[str, Any]],
                      y_fmt, width: int = 860, height: int = 440) -> None:
    """Render one or more date-indexed lines into a standalone SVG file."""
    pad_l, pad_r, pad_t, pad_b = 64, 20, 58, 44
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    all_dates: set[str] = set()
    all_values: list[float] = []
    for series in series_list:
        for day, value in series["points"]:
            all_dates.add(day)
            all_values.append(value)
    dates = sorted(all_dates)
    if not dates:
        raise RuntimeError("没有可用于绘图的数据")

    d0 = date.fromisoformat(dates[0])
    d1 = date.fromisoformat(dates[-1])
    span_days = max((d1 - d0).days, 1)
    vmin, vmax = min(all_values), max(all_values)
    if vmin == vmax:
        vmin, vmax = vmin - 1.0, vmax + 1.0
    vrange = vmax - vmin

    def x_for(day: str) -> float:
        return pad_l + (date.fromisoformat(day) - d0).days / span_days * plot_w

    def y_for(value: float) -> float:
        return pad_t + (1.0 - (value - vmin) / vrange) * plot_h

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#101716"/>',
    ]

    # Horizontal grid lines + y-axis labels.
    for i in range(5):
        ratio = i / 4
        y = pad_t + ratio * plot_h
        value = vmax - ratio * vrange
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" '
            f'stroke="#2a3432" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_l - 10}" y="{y + 4:.1f}" fill="#7d8a88" font-size="12" '
            f'text-anchor="end">{_escape(y_fmt(value))}</text>'
        )

    # X-axis date labels (four ticks).
    for i in range(4):
        idx = round(i / 3 * (len(dates) - 1))
        x = x_for(dates[idx])
        parts.append(
            f'<text x="{x:.1f}" y="{height - pad_b + 22}" fill="#7d8a88" font-size="12" '
            f'text-anchor="middle">{dates[idx][:7]}</text>'
        )

    # Data lines.
    for series in series_list:
        points = " ".join(f"{x_for(day):.1f},{y_for(value):.1f}" for day, value in series["points"])
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{series["color"]}" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        )

    # Title.
    parts.append(
        f'<text x="{pad_l}" y="30" fill="#e6e1d5" font-size="18" font-weight="600">{_escape(title)}</text>'
    )

    # Legend (right-aligned, one item per line under the title area).
    legend_x = width - pad_r
    for series in reversed(series_list):
        label = _escape(series["name"])
        parts.append(f'<circle cx="{legend_x - 8}" cy="28" r="4" fill="{series["color"]}"/>')
        parts.append(
            f'<text x="{legend_x - 18}" y="32" fill="#a9b4b1" font-size="12" '
            f'text-anchor="end">{label}</text>'
        )
        legend_x -= 18 + len(str(series["name"])) * 13 + 16

    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _pnl_color(value: float) -> str:
    """A-share convention: red for up, green for down."""
    if value > 0:
        return "#ff5c5c"
    if value < 0:
        return "#3ddc84"
    return "#a9b4b1"


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def render_daily_card(curves: dict[str, list[dict[str, Any]]],
                      portfolio: list[dict[str, Any]]) -> None:
    """Render a GitHub-stats-style card showing the latest day's returns."""
    latest = portfolio[-1]["date"]
    items = [("组合", portfolio[-1]["daily_return_pct"])]
    for key in market.ASSETS:
        label = market.ASSETS[key]["label"].replace(" ETF", "")
        items.append((label, curves[key][-1]["daily_return_pct"]))

    width, height = 860, 140
    pad = 24
    cell_w = (width - pad * 2) / len(items)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">',
        f'<rect width="{width}" height="{height}" rx="14" fill="#101716"/>',
        f'<text x="{pad}" y="32" fill="#7d8a88" font-size="12">日收益率 · DAILY RETURN</text>',
        f'<text x="{width - pad}" y="32" fill="#7d8a88" font-size="12" text-anchor="end">{latest}</text>',
    ]

    for i, (label, value) in enumerate(items):
        if i > 0:
            x = pad + cell_w * i
            parts.append(
                f'<line x1="{x:.1f}" y1="44" x2="{x:.1f}" y2="{height - 40}" '
                f'stroke="#2a3432" stroke-width="1"/>'
            )
        cx = pad + cell_w * i + cell_w / 2
        parts.append(
            f'<text x="{cx:.1f}" y="82" fill="#a9b4b1" font-size="14" '
            f'text-anchor="middle">{_escape(label)}</text>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="116" fill="{_pnl_color(value)}" font-size="30" '
            f'font-weight="700" text-anchor="middle">{_fmt_pct(value)}</text>'
        )

    parts.append("</svg>")
    DAILY_CARD_SVG.write_text("\n".join(parts), encoding="utf-8")


def render_svgs(curves: dict[str, list[dict[str, Any]]],
                portfolio: list[dict[str, Any]]) -> None:
    """Write the README SVGs: daily card, net-asset-value and cumulative return."""
    latest = portfolio[-1]["date"]

    nav_series = [{
        "name": "组合(等权)",
        "color": COLORS["portfolio"],
        "points": [(p["date"], p["wealth"]) for p in portfolio],
    }]
    for key in market.ASSETS:
        nav_series.append({
            "name": market.ASSETS[key]["label"].replace(" ETF", ""),
            "color": COLORS[key],
            "points": [(p["date"], p["wealth"]) for p in curves[key]],
        })

    return_series = [{
        "name": "组合(等权)",
        "color": COLORS["portfolio"],
        "points": [(p["date"], (p["wealth"] - 1.0) * 100.0) for p in portfolio],
    }]
    for key in market.ASSETS:
        return_series.append({
            "name": market.ASSETS[key]["label"].replace(" ETF", ""),
            "color": COLORS[key],
            "points": [(p["date"], (p["wealth"] - 1.0) * 100.0) for p in curves[key]],
        })

    render_line_chart(
        NAV_SVG,
        f"每日定投 · 净值曲线（截至 {latest}）",
        nav_series,
        y_fmt=lambda v: f"{v:.2f}",
    )
    render_line_chart(
        RETURNS_SVG,
        f"每日定投 · 累计收益率（截至 {latest}）",
        return_series,
        y_fmt=lambda v: f"{v:.0f}%",
    )
    render_daily_card(curves, portfolio)


# ---------------------------------------------------------------- Main

def main() -> None:
    data = load_quotes_csv()
    new_count = sync_incremental(data)

    if new_count == 0 and all(quotes_path(key).is_file() for key in market.ASSETS):
        print("无新交易数据（周末/节假日/数据未出），跳过本次更新。")
        return

    save_quotes_csv(data)

    curves: dict[str, list[dict[str, Any]]] = {}
    for key in market.ASSETS:
        rows = [
            {"date": trade_date, "price": float(data[key][trade_date]["close"])}
            for trade_date in sorted(data[key])
            if trade_date >= START_DATE.isoformat()
        ]
        curves[key] = market.compute_backtest(key, rows, DAILY_AMOUNT)["curve"]

    portfolio = compute_portfolio(curves)
    save_returns_csv(build_returns_rows(curves, portfolio))
    render_svgs(curves, portfolio)

    print(f"新增 {new_count} 行行情，已更新 CSV + SVG（最新交易日 {portfolio[-1]['date']}）。")


if __name__ == "__main__":
    main()
