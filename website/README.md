# 马后炮指数网站

在线地址：**https://mahoupao-index.leiwu3.workers.dev**

原生 HTML / CSS / JavaScript + Cloudflare Worker，无前端框架、外部字体或分析追踪。部署只上传 `public/` 与 Worker 代码，不上传仓库 `.env`、Tushare 凭据或 `mcm/`。

## 数据流与口径

```text
Tushare → 原有 GitHub Actions → data/export/daily_returns.csv
                                    ↓ 公开 GitHub raw URL
浏览器 ← /api/index ← Cloudflare Worker（边缘缓存）
```

- 指数水平直接使用 CSV 的 `return_pct` 数值，不显示 `%`。
- badge 数值为当前记录的 `return_pct`，即累计收益率的百分数值，不带 `%`；正负号表示累计盈亏。
- badge 颜色按当前记录的 `return_pct` − 上一条记录的 `return_pct` 确定：红涨绿跌，持平或无上一条记录时灰色。差值不作为徽章数值显示。
- **不使用 `daily_return_pct` 作为 badge 的数值或颜色依据**，也不重新计算另一套回测。
- 各资产按自己的相邻记录比较；组合沿用现有 CSV 的账户市值及累计投入口径。
- 图表支持 1 个月、1 年、3 年和全历史；区间仅截取显示，不重置定投起点。短区间分别取最近 31 / 365 / 1095 个自然日。
- 图表支持指针悬浮读数，以及聚焦后用左右方向键、Home、End 和 Escape 操作。
- API 与上游行情各缓存约 5 分钟，浏览器 API 缓存 60 秒。仓库有新数据后，重新打开或刷新网页即可读取；无需每日重新部署网站。
- 实时源失败时退回部署时生成的 `public/snapshot.json`，页面明确提示“快照”和数据日期。生成的快照不提交 Git，部署前自动重建。
- 最新记录超过 7 个自然日会显示提醒（包括节假日），不把旧数据伪装成实时行情。获取时间与行情截止日分开记录。

## 本地运行

需要 Node.js 22+ 和已安装的 Wrangler 4（首次可运行 `npm install -g wrangler@4`）。网站自身没有 npm 运行时依赖。

```bash
cd website
npm run snapshot   # 从本地 CSV 生成容灾快照
npm test
npm run dev        # 默认 http://localhost:8787
```

## 部署

仅在明确批准发布后执行：

```bash
wrangler login     # 本机尚未登录时才需要
cd website
npm run deploy    # 重建快照 → 测试 → 发布
```

Worker 名称为 `mahoupao-index`，配置见 `wrangler.jsonc`。当前使用 `workers.dev` 子域名，不更改现有域名、DNS 或其他 Worker。无需 KV、D1 或 Tushare Secret。

## 文件

- `src/data.mjs`：校验 CSV，组织历史序列和日变动。
- `src/worker.mjs`：同源 `/api/index`、缓存、快照回退和错误响应。
- `public/`：网站、响应式布局、交互 SVG 曲线及安全响应头。
- `scripts/snapshot.mjs`：生成容灾快照。
- `test/`：Node 内置测试，涵盖指标口径、异常数据、区间选择、API 缓存与回退。

该网站是现有定投账本的展示层，不新增预测信号，也不改变原有行情同步工作流。
