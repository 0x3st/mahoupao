#!/usr/bin/env python3
"""Small, dependency-free backtest server for the accumulation dashboard.

The server keeps the Tushare token on the server side. When no token is
configured, it serves deterministic demo data so the UI remains usable.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import sqlite3
import threading
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
BACKTEST_DIR = ROOT / "data" / "backtests"
DB_PATH = ROOT / "data" / "market.db"
TODAY = date.today()
TUSHARE_URL = "https://api.tushare.pro"
COMMON_START = date(2014, 1, 15)


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
        "currency": "CNY",
        "currency_symbol": "¥",
        "default_amount": 100.0,
        "api_name": "fund_daily",
        "params": {"ts_code": "510300.SH"},
        "price_field": "close",
        "source_label": "Tushare · 510300.SH · 华泰柏瑞沪深300ETF",
        "unit_label": "元 / 份",
        "list_date": "2012-05-28",
        "demo_base": 2.5,
        "demo_drift": 0.00010,
        "demo_vol": 0.012,
        "demo_phase": 0.4,
    },
    "spx": {
        "label": "标普500 ETF",
        "short_label": "513500.SH",
        "currency": "CNY",
        "currency_symbol": "¥",
        "default_amount": 100.0,
        "api_name": "fund_daily",
        "params": {"ts_code": "513500.SH"},
        "price_field": "close",
        "source_label": "Tushare · 513500.SH · 博时标普500ETF(QDII)",
        "unit_label": "元 / 份",
        "list_date": "2014-01-15",
        "demo_base": 1.1,
        "demo_drift": 0.00023,
        "demo_vol": 0.010,
        "demo_phase": 1.7,
    },
    "gold": {
        "label": "黄金 ETF",
        "short_label": "518880.SH",
        "currency": "CNY",
        "currency_symbol": "¥",
        "default_amount": 100.0,
        "api_name": "fund_daily",
        "params": {"ts_code": "518880.SH"},
        "price_field": "close",
        "source_label": "Tushare · 518880.SH · 华安易富黄金ETF",
        "unit_label": "元 / 份",
        "list_date": "2013-07-29",
        "demo_base": 2.2,
        "demo_drift": 0.00018,
        "demo_vol": 0.008,
        "demo_phase": 3.1,
    },
}


def parse_yyyymmdd(raw: str | None, fallback: date) -> date:
    if not raw:
        return fallback
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return fallback


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


def init_db() -> sqlite3.Connection:
    """Open (and lazily initialise) the local SQLite market database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS daily_quotes (
            asset_key TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL NOT NULL,
            pre_close REAL,
            change REAL,
            pct_chg REAL,
            vol REAL,
            amount REAL,
            PRIMARY KEY (asset_key, trade_date)
        );

        CREATE TABLE IF NOT EXISTS sync_state (
            asset_key TEXT PRIMARY KEY,
            last_trade_date TEXT,
            row_count INTEGER NOT NULL DEFAULT 0,
            last_synced_at TEXT
        );
        """
    )
    conn.commit()
    return conn


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


def save_quotes(conn: sqlite3.Connection, asset_key: str, rows: list[dict[str, Any]]) -> int:
    """Persist quote rows, replacing duplicates so sync stays idempotent."""
    conn.executemany(
        """
        INSERT INTO daily_quotes
            (asset_key, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_key, trade_date) DO UPDATE SET
            open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
            pre_close=excluded.pre_close, change=excluded.change, pct_chg=excluded.pct_chg,
            vol=excluded.vol, amount=excluded.amount
        """,
        [
            (asset_key, row["trade_date"], row["open"], row["high"], row["low"], row["close"],
             row["pre_close"], row["change"], row["pct_chg"], row["vol"], row["amount"])
            for row in rows
        ],
    )
    conn.commit()
    return len(rows)


def quote_coverage(conn: sqlite3.Connection, asset_key: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT MIN(trade_date), MAX(trade_date), COUNT(*) FROM daily_quotes WHERE asset_key = ?",
        (asset_key,),
    ).fetchone()
    return {"min": row[0], "max": row[1], "count": row[2] or 0}


def sync_asset_range(conn: sqlite3.Connection, asset_key: str, start: date, end: date) -> int:
    """Fetch and persist quotes for one date window; returns the number of new rows."""
    asset = ASSETS[asset_key]
    cleaned = clean_quote_rows(fetch_tushare_quotes(asset, start, end), start, end)
    if not cleaned:
        return 0
    save_quotes(conn, asset_key, cleaned)
    total_rows = quote_coverage(conn, asset_key)["count"]
    conn.execute(
        """
        INSERT INTO sync_state(asset_key, last_trade_date, row_count, last_synced_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(asset_key) DO UPDATE SET
            last_trade_date = excluded.last_trade_date,
            row_count = excluded.row_count,
            last_synced_at = excluded.last_synced_at
        """,
        (asset_key, cleaned[-1]["trade_date"], total_rows, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    return len(cleaned)


def ensure_quotes(conn: sqlite3.Connection, asset_key: str, start: date, end: date) -> dict[str, Any]:
    """Lazily sync so local quotes cover [start, end], then report coverage."""
    asset = ASSETS[asset_key]
    coverage = quote_coverage(conn, asset_key)

    if coverage["count"] == 0:
        begin = date.fromisoformat(asset["list_date"])
        if begin <= end:
            sync_asset_range(conn, asset_key, begin, end)
    else:
        if coverage["min"] and coverage["min"] > start.isoformat():
            sync_asset_range(conn, asset_key, start, date.fromisoformat(coverage["min"]) - timedelta(days=1))
        if coverage["max"] and coverage["max"] < end.isoformat():
            sync_asset_range(conn, asset_key, date.fromisoformat(coverage["max"]) + timedelta(days=1), end)

    return quote_coverage(conn, asset_key)


def load_quotes(conn: sqlite3.Connection, asset_key: str, start: date, end: date) -> list[dict[str, Any]]:
    """Read cleaned close prices from the local market database."""
    rows = conn.execute(
        "SELECT trade_date, close FROM daily_quotes "
        "WHERE asset_key = ? AND trade_date BETWEEN ? AND ? ORDER BY trade_date",
        (asset_key, start.isoformat(), end.isoformat()),
    ).fetchall()
    return [{"date": row[0], "price": row[1]} for row in rows]


def demo_rows(asset: dict[str, Any], start: date, end: date) -> list[dict[str, Any]]:
    """Generate stable, visibly plausible demo data for an offline preview."""
    rows: list[dict[str, Any]] = []
    current = start
    previous = float(asset["demo_base"])
    index = 0

    events = (
        (date(2011, 8, 8), -0.006, 6),
        (date(2018, 12, 24), -0.005, 7),
        (date(2020, 3, 16), -0.010, 5),
        (date(2020, 4, 20), 0.006, 8),
        (date(2022, 6, 13), -0.006, 7),
    )

    def event_pulse(day: date) -> float:
        total = 0.0
        for center, amplitude, width in events:
            distance = (day - center).days
            total += amplitude * math.exp(-0.5 * (distance / width) ** 2)
        return total

    while current <= end:
        if current.weekday() < 5:
            cycle = math.sin(index * 0.071 + asset["demo_phase"]) * asset["demo_vol"] * 0.44
            medium = math.sin(index * 0.013 + asset["demo_phase"] * 2) * asset["demo_vol"] * 0.32
            daily_move = asset["demo_drift"] + cycle + medium + event_pulse(current)
            previous = max(previous * (1.0 + daily_move), 0.01)
            rows.append({"date": current.isoformat(), "price": round(previous, 4)})
            index += 1
        current += timedelta(days=1)
    return rows


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
        "currency": asset["currency"],
        "currency_symbol": asset["currency_symbol"],
        "unit_label": asset["unit_label"],
        "list_date": asset["list_date"],
        "settlement": "daily_close",
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


def run_backtest(asset_key: str, start: date, end: date, amount: float) -> dict[str, Any]:
    asset = ASSETS[asset_key]
    source = "demo"
    note = "未配置 TUSHARE_TOKEN，当前为离线演示数据"
    conn = init_db()
    try:
        ensure_quotes(conn, asset_key, start, end)
        rows = load_quotes(conn, asset_key, start, end)
        if not rows:
            raise RuntimeError("本地行情库没有覆盖指定区间")
        source = "tushare"
        note = asset["source_label"]
    except Exception as exc:  # The UI should stay useful even when an entitlement is missing.
        rows = demo_rows(asset, start, end)
        note = f"演示数据 · {str(exc)[:80]}"
    finally:
        conn.close()

    result = compute_backtest(asset_key, rows, amount)
    result["source"] = source
    result["note"] = note
    return result


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def save_backtest(payload: dict[str, Any]) -> dict[str, str]:
    """Persist a complete backtest as a private, atomic local JSON archive."""
    saved_at = datetime.now().isoformat(timespec="seconds")
    record_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    final_path = BACKTEST_DIR / f"{record_id}.json"
    temporary_path = BACKTEST_DIR / f".{record_id}.tmp"
    archive = {
        "record_id": record_id,
        "saved_at": saved_at,
        **payload,
    }
    temporary_path.write_text(
        json.dumps(archive, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary_path.replace(final_path)
    final_path.chmod(0o600)
    return {
        "id": record_id,
        "path": str(final_path.relative_to(ROOT)),
        "created_at": saved_at,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "InvestIndex/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep local development output quiet and readable.
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/backtest":
            self.handle_backtest(parse_qs(parsed.query))
            return
        self.serve_static(parsed.path)

    def handle_backtest(self, query: dict[str, list[str]]) -> None:
        start = max(parse_yyyymmdd(query.get("start_date", [None])[0], COMMON_START), COMMON_START)
        end = parse_yyyymmdd(query.get("end_date", [None])[0], TODAY)
        if start > end:
            start, end = end, start

        amounts: dict[str, float] = {}
        for key, asset in ASSETS.items():
            raw = query.get(f"amount_{key}", [str(asset["default_amount"])])[0]
            try:
                amounts[key] = max(float(raw), 0.01)
            except ValueError:
                amounts[key] = float(asset["default_amount"])

        try:
            results = [run_backtest(key, start, end, amounts[key]) for key in ASSETS]
            payload = {
                "ok": True,
                "requested_start": start.isoformat(),
                "requested_end": end.isoformat(),
                "parameters": {
                    "daily_amounts": amounts,
                    "settlement": "daily_close",
                    "fractional_units": True,
                },
                "assets": results,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }
            if query.get("save", ["0"])[0].lower() in {"1", "true", "yes"}:
                payload["record"] = save_backtest(payload)
            json_response(self, payload)
        except Exception as exc:
            json_response(self, {"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def serve_static(self, path: str) -> None:
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        if "/" in relative or relative.startswith("."):
            candidate = (ROOT / relative).resolve()
            if ROOT not in candidate.parents and candidate != ROOT:
                json_response(self, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
        else:
            candidate = ROOT / relative
        if not candidate.is_file():
            json_response(self, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }.get(candidate.suffix, "application/octet-stream")
        body = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mahoupao backtest dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Invest Index running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
