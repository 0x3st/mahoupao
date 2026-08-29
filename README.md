# 马后炮 / Mahoupao

中文 · [English](README.en.md)

一个用于比较三只场内 ETF“每日收市固定投入”的历史回测原型。

这是离线回测工具，不做盘中行情或自动刷新。页面打开时只预览；点击“运行并保存”后，才会生成一份本地档案。

## 每日数据快照

下面的图表由 GitHub Actions 每天自动更新，数据来自 Tushare 真实行情。

### 净值曲线（等权组合 + 三只标的）

![净值曲线](data/export/nav.svg)

### 累计收益率

![累计收益率](data/export/returns.svg)

> 口径：每日收市后按收盘价每只投入 100 元；净值/收益率均排除追加资金影响。数据截至最近一个交易日，周末/节假日无新数据时自动跳过。

## 回测口径

- 默认起点：`2014-01-15`，三只 ETF 的共同历史起点
- 每个标的使用自己的交易日历；非交易日不结算
- 每个交易日收市后按收盘价完成一次结算和估值
- 沪深300：`510300.SH`，华泰柏瑞沪深300ETF
- 标普500：`513500.SH`，博时标普500ETF(QDII)
- 黄金：`518880.SH`，华安易富黄金ETF
- 未配置 Token 时自动使用稳定的离线演示数据，方便先看界面和回测逻辑

这版按固定金额允许买入小数份额，适合观察“每天投入100元”的资金曲线；真实场内交易通常还要考虑100份整数手、手续费、分红和申赎/折溢价。后续可以增加“整数手+现金结转”模式。

## 回测档案

每次点击“运行并保存”，系统都会把本次参数、三只 ETF 的完整每日曲线和汇总指标保存到：

```text
data/backtests/<回测编号>.json
```

档案文件默认不纳入 Git，且不会写入 Tushare Token。

## ETF 备选池

- 沪深300：默认 `510300.SH`；备选 `510310.SH`、`159919.SZ`
- 标普500：默认 `513500.SH`；备选 `513650.SH`、`159655.SZ`
- 黄金：默认 `518880.SH`；备选 `159934.SZ`、`159937.SZ`

## GitHub Actions 每日更新

仓库自带 `.github/workflows/daily-update.yml`，每天北京时间 20:30 左右自动运行：

1. 增量拉取 Tushare 新行情
2. 重新核算每日收益率
3. 更新 `data/export/` 下的 CSV 与 SVG 并提交

首次使用只需两步：

1. 在仓库 `Settings → Secrets and variables → Actions` 添加 `TUSHARE_TOKEN`
2. （可选）手动触发一次：`Actions → Daily update → Run workflow`

周末/节假日无新数据时，workflow 会自动跳过提交。数据文件说明：

- `data/export/quotes.csv`：三只 ETF 的完整日线行情快照（可预览/diff/下载）
- `data/export/daily_returns.csv`：每只标的 + 等权组合的每日收益率、累计收益率、净值
- `data/export/nav.svg` / `returns.svg`：净值与收益率曲线图

## 运行

```bash
cp .env.example .env
# 编辑 .env，填入你的 Tushare Pro Token
python3 server.py
```

也可以不创建 `.env`，直接执行 `export TUSHARE_TOKEN="你的 Tushare Pro Token"`。

然后打开 <http://127.0.0.1:8000>。

没有 Token 也可以直接运行，页面会明确标记为 `OFFLINE DEMO`。

Tushare 接口说明：

- [ETF日线行情](https://tushare.pro/document/2?doc_id=127)
- [公募基金列表](https://tushare.pro/document/1?doc_id=19)
- [HTTP 调取方式](https://tushare.pro/document/1?doc_id=40)
