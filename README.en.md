# Mahoupao (马后炮)

[中文文档](README.md) · English

A daily-updating ETF accumulation data pipeline: it pulls real Tushare quotes, computes returns for a "fixed daily after-close contribution" strategy, and publishes CSV snapshots plus NAV/return charts to this repo. Data is the only thing this repository cares about.

## Daily Data Snapshot

The charts below are regenerated automatically by GitHub Actions every day from real Tushare data.

### Latest trading day returns (red up, green down)

![CSI 300](data/export/badge-csi300.svg) ![S&P 500](data/export/badge-spx.svg) ![Gold](data/export/badge-gold.svg)

### Net-asset-value curve (equal-weight portfolio + three assets)

![Net asset value](data/export/nav.svg)

### Cumulative return

![Cumulative return](data/export/returns.svg)

> Methodology: 100 CNY is invested at each day's close into each asset; NAV/returns exclude the effect of additional contributions. Data is as of the latest trading day, and the update is skipped automatically on weekends/holidays when there is no new data.

## Data Files

- `data/export/csi300.csv` / `spx.csv` / `gold.csv` — per-asset daily OHLCV snapshots (preview/diff/download)
- `data/export/daily_returns.csv` — daily return, cumulative return and NAV per asset + equal-weight portfolio
- `data/export/badge-csi300.svg` / `badge-spx.svg` / `badge-gold.svg` — per-asset daily-return shield badges (red up, green down)
- `data/export/nav.svg` / `returns.svg` — NAV chart and cumulative return chart

## Backtest Methodology

- Default start: `2014-01-15`, the earliest common history of the three ETFs
- Each asset uses its own trading calendar; non-trading days are not settled
- Settlement and valuation happen once per day at the closing price
- CSI 300: `510300.SH`, Huatai-PineBridge CSI 300 ETF
- S&P 500: `513500.SH`, Bosera S&P 500 ETF (QDII)
- Gold: `518880.SH`, Huaan Yifu Gold ETF

This version allows fractional shares at a fixed amount, ideal for observing the "100 CNY per day" wealth curve. Real on-exchange trading also involves 100-share lots, fees, dividends and premium/discount.

## GitHub Actions Daily Update

The repo ships with `.github/workflows/daily-update.yml`, which runs daily around 20:30 Beijing time:

1. Incrementally pulls new Tushare quotes
2. Recomputes daily returns
3. Commits the updated CSV + SVG under `data/export/`

First-time setup:

1. Add `TUSHARE_TOKEN` under `Settings → Secrets and variables → Actions`
2. (Optional) trigger once manually: `Actions → Daily update → Run workflow`

On weekends/holidays with no new data the workflow skips committing.

## Running Locally

```bash
cp .env.example .env
# edit .env and fill in your Tushare Pro token
python3 sync_and_report.py
```

The script incrementally pulls new quotes and regenerates the CSV + SVG files under `data/export/`.

Tushare API reference:

- [ETF daily quotes](https://tushare.pro/document/2?doc_id=127)
- [Mutual fund list](https://tushare.pro/document/1?doc_id=19)
- [HTTP API](https://tushare.pro/document/1?doc_id=40)
