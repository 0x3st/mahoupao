#!/usr/bin/env python3
"""Market data + backtest math, dependency-free.

Fetches Tushare fund daily quotes and computes a fixed daily contribution
backtest. The only consumer is sync_and_report.py (the GitHub Actions pipeline).
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
TUSHARE_URL = "https://api.tushare.pro"


def load_local_env() -> None:
    """Load a tiny .env file without adding a dependency."""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()

ASSETS: dict[str, dict[str, Any]] = {
    "csi300": {
        "label": "沪深300 ETF",
        "short_label": "510300.SH",
        "api_name": "fund_daily",
        "params": {"ts_code": "510300.SH"},
        "list_date": "2012-05-28",
        "source_label": "Tushare · 510300.SH · 华泰柏瑞沪深300ETF",
    },
    "spx": {
        "label": "标普500 ETF",
        "short_label": "513500.SH",
        "api_name": "fund_daily",
        "params": {"ts_code": "513500.SH"},
        "list_date": "2014-01-15",
        "source_label": "Tushare · 513500.SH · 博时标普500ETF(QDII)",
    },
    "gold": {
        "label": "黄金 ETF",
        "short_label": "518880.SH",
        "api_name": "fund_daily",
        "params": {"ts_code": "518880.SH"},
        "list_date": "2013-07-29",
        "source_label": "Tushare · 518880.SH · 华安易富黄金ETF",
    },
}


def yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def request_tushare(api_name: str, params: dict[str, Any], fields: str) -> list[dict[str, Any]]:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("未配置 TUSHARE_TOKEN")

    payload = {
        "api_name": api_name,
        "token": token,
        "params": params,
        "fields": fields,
    }
    request = Request(
        TUSHARE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "mahoupao/0.1"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))

    if body.get("code") not in (0, None):
        raise RuntimeError(body.get("msg") or "Tushare 返回错误")
    data = body.get("data") or {}
    fields_list = data.get("fields") or []
    items = data.get("items") or []
    return [dict(zip(fields_list, row)) for row in items]


QUOTE_FIELDS = "trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "NaN"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_tushare_quotes(asset: dict[str, Any], start: date, end: date) -> list[dict[str, Any]]:
    """Fetch full OHLCV rows in safe date windows so long histories are never silently truncated."""
    rows: list[dict[str, Any]] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(end, chunk_start + timedelta(days=730))
        rows.extend(request_tushare(
            asset["api_name"],
            {
                **asset["params"],
                "start_date": yyyymmdd(chunk_start),
                "end_date": yyyymmdd(chunk_end),
            },
            QUOTE_FIELDS,
        ))
        chunk_start = chunk_end + timedelta(days=1)
    return rows


def clean_quote_rows(rows: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    """Dedupe and validate raw Tushare rows into date-keyed quote dicts."""
    cleaned: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw_date = row.get("trade_date") or row.get("cal_date")
        close = _safe_float(row.get("close"))
        if raw_date is None or close is None or close <= 0:
            continue
        trade_day: date | None = None
        for fmt in ("%Y%m%d", "%Y-%m-%d"):
            try:
                trade_day = datetime.strptime(str(raw_date), fmt).date()
                break
            except ValueError:
                pass
        if trade_day is None or not (start <= trade_day <= end):
            continue
        cleaned[trade_day.isoformat()] = {
            "trade_date": trade_day.isoformat(),
            "open": _safe_float(row.get("open")),
            "high": _safe_float(row.get("high")),
            "low": _safe_float(row.get("low")),
            "close": close,
            "pre_close": _safe_float(row.get("pre_close")),
            "change": _safe_float(row.get("change")),
            "pct_chg": _safe_float(row.get("pct_chg")),
            "vol": _safe_float(row.get("vol")),
            "amount": _safe_float(row.get("amount")),
        }
    return [cleaned[key] for key in sorted(cleaned)]


def xirr(cashflows: list[tuple[date, float]]) -> float | None:
    if len(cashflows) < 2 or not any(value > 0 for _, value in cashflows):
        return None
    origin = cashflows[0][0]

    def npv(rate: float) -> float:
        return sum(value / ((1.0 + rate) ** (((day - origin).days) / 365.0)) for day, value in cashflows)

    low, high = -0.9999, 10.0
    low_value, high_value = npv(low), npv(high)
    for _ in range(12):
        if low_value * high_value <= 0:
            break
        high *= 2
        high_value = npv(high)
    else:
        return None

    for _ in range(100):
        middle = (low + high) / 2
        middle_value = npv(middle)
        if abs(middle_value) < 1e-8:
            return middle
        if low_value * middle_value <= 0:
            high, high_value = middle, middle_value
        else:
            low, low_value = middle, middle_value
    return (low + high) / 2


def compute_backtest(asset_key: str, rows: list[dict[str, Any]], amount: float) -> dict[str, Any]:
    """Core accumulation math over a list of {date, price} rows."""
    asset = ASSETS[asset_key]
    units = 0.0
    invested = 0.0
    previous_value: float | None = None
    wealth = 1.0
    peak_wealth = 1.0
    max_drawdown = 0.0
    curve: list[dict[str, Any]] = []
    cashflows: list[tuple[date, float]] = []

    for row in rows:
        price = float(row["price"])
        trade_day = date.fromisoformat(row["date"])
        contribution = float(amount)
        previous_units = units
        units += contribution / price
        invested += contribution
        value = units * price
        marked_previous_value = previous_units * price
        if previous_value is not None and previous_value > 0:
            daily_pnl = marked_previous_value - previous_value
            daily_return = daily_pnl / previous_value
            wealth *= 1.0 + daily_return
        else:
            daily_pnl = 0.0
            daily_return = 0.0
        peak_wealth = max(peak_wealth, wealth)
        drawdown = wealth / peak_wealth - 1.0
        max_drawdown = min(max_drawdown, drawdown)
        cashflows.append((trade_day, -contribution))
        curve.append({
            "date": row["date"],
            "price": round(price, 6),
            "invested": round(invested, 2),
            "value": round(value, 2),
            "profit": round(value - invested, 2),
            "return_pct": round((value / invested - 1.0) * 100.0, 4),
            "daily_pnl": round(daily_pnl, 2),
            "daily_return_pct": round(daily_return * 100.0, 4),
            "drawdown_pct": round(drawdown * 100.0, 4),
            "wealth": round(wealth, 8),
        })
        previous_value = value

    if not curve:
        raise RuntimeError("回测区间没有可用交易日")

    final = curve[-1]
    cashflows.append((date.fromisoformat(final["date"]), float(final["value"])))
    annualized = xirr(cashflows)
    return {
        "key": asset_key,
        "label": asset["label"],
        "short_label": asset["short_label"],
        "list_date": asset["list_date"],
        "start_date": curve[0]["date"],
        "end_date": curve[-1]["date"],
        "trading_days": len(curve),
        "invested": final["invested"],
        "value": final["value"],
        "profit": final["profit"],
        "return_pct": final["return_pct"],
        "annualized_pct": None if annualized is None else round(annualized * 100.0, 4),
        "max_drawdown_pct": round(max_drawdown * 100.0, 4),
        "units": round(units, 8),
        "latest_price": final["price"],
        "latest_daily_pnl": final["daily_pnl"],
        "latest_daily_return_pct": final["daily_return_pct"],
        "curve": curve,
    }
