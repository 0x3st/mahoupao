# Mahoupao (马后炮)

[中文文档](README.md) · English

A backtesting prototype that compares three on-exchange ETFs under a "fixed daily after-close contribution" strategy.

> "马后炮" (mahoupao) is Chinese for "hindsight" — a fitting name for a backtest tool.

This is an offline backtest tool: no intraday quotes, no auto-refresh. The page only previews on load; a local archive is written only after you click "Run & Save".

## Daily Data Snapshot

The charts below are regenerated automatically by GitHub Actions every day from real Tushare data.

### Net-asset-value curve (equal-weight portfolio + three assets)

![Net asset value](data/export/nav.svg)

### Cumulative return

![Cumulative return](data/export/returns.svg)

> Methodology: 100 CNY is invested at each day's close into each asset; NAV/returns exclude the effect of additional contributions. Data is as of the latest trading day, and the update is skipped automatically on weekends/holidays when there is no new data.

## Backtest Methodology

- Default start: `2014-01-15`, the earliest common history of the three ETFs
- Each asset uses its own trading calendar; non-trading days are not settled
- Settlement and valuation happen once per day at the closing price
- CSI 300: `510300.SH`, Huatai-PineBridge CSI 300 ETF
- S&P 500: `513500.SH`, Bosera S&P 500 ETF (QDII)
- Gold: `518880.SH`, Huaan Yifu Gold ETF
- Without a token the tool falls back to stable offline demo data, so you can explore the UI and logic first

This version allows fractional shares at a fixed amount, ideal for observing the "100 CNY per day" wealth curve. Real on-exchange trading also involves 100-share lots, fees, dividends and premium/discount; a "whole-lot + cash carry" mode may be added later.

## Backtest Archive

Every "Run & Save" stores the parameters, the full daily curves of the three ETFs and summary metrics to:

```text
data/backtests/<backtest-id>.json
```

Archives are excluded from Git by default and never contain the Tushare token.

## ETF Universe

- CSI 300: default `510300.SH`; alternatives `510310.SH`, `159919.SZ`
- S&P 500: default `513500.SH`; alternatives `513650.SH`, `159655.SZ`
- Gold: default `518880.SH`; alternatives `159934.SZ`, `159937.SZ`

## GitHub Actions Daily Update

The repo ships with `.github/workflows/daily-update.yml`, which runs daily around 20:30 Beijing time:

1. Incrementally pulls new Tushare quotes
2. Recomputes daily returns
3. Commits the updated CSV + SVG under `data/export/`

First-time setup:

1. Add `TUSHARE_TOKEN` under `Settings → Secrets and variables → Actions`
2. (Optional) trigger once manually: `Actions → Daily update → Run workflow`

On weekends/holidays with no new data the workflow skips committing. Data files:

- `data/export/quotes.csv` — full daily OHLCV snapshot of the three ETFs (preview/diff/download)
- `data/export/daily_returns.csv` — daily return, cumulative return and NAV per asset + equal-weight portfolio
- `data/export/nav.svg` / `returns.svg` — NAV and return charts

## Running Locally

```bash
cp .env.example .env
# edit .env and fill in your Tushare Pro token
python3 server.py
```

Or skip `.env` and run `export TUSHARE_TOKEN="your Tushare Pro token"` first.

Then open <http://127.0.0.1:8000>.

You can also run without a token; the page will be clearly marked `OFFLINE DEMO`.

Tushare API reference:

- [ETF daily quotes](https://tushare.pro/document/2?doc_id=127)
- [Mutual fund list](https://tushare.pro/document/1?doc_id=19)
- [HTTP API](https://tushare.pro/document/1?doc_id=40)
