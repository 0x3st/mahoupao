const ASSET_ORDER = ["csi300", "spx", "gold"];

const state = {
  payload: null,
  activeKey: "csi300",
  chart: null,
};

const assetClasses = {
  csi300: "csi",
  spx: "spx",
  gold: "gold",
};

const $ = (selector) => document.querySelector(selector);

function escapeHTML(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function money(value, currency, compact = false) {
  const numeric = Number(value || 0);
  const options = compact
    ? { notation: "compact", maximumFractionDigits: 1 }
    : { maximumFractionDigits: Math.abs(numeric) < 100 ? 2 : 0 };
  return new Intl.NumberFormat(currency === "USD" ? "en-US" : "zh-CN", {
    style: "currency",
    currency,
    ...options,
  }).format(numeric);
}

function signedPercent(value, digits = 2) {
  const numeric = Number(value || 0);
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(digits)}%`;
}

function signedMoney(value, currency) {
  const numeric = Number(value || 0);
  return `${numeric >= 0 ? "+" : "−"}${money(Math.abs(numeric), currency)}`;
}

function compactNumber(value, currency) {
  return money(value, currency, true);
}

function formatDate(dateString, withDay = false) {
  if (!dateString) return "—";
  const date = new Date(`${dateString}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dateString;
  return new Intl.DateTimeFormat("zh-CN", withDay
    ? { year: "numeric", month: "2-digit", day: "2-digit" }
    : { year: "numeric", month: "2-digit" }
  ).format(date).replaceAll("/", ".");
}

function formatPrice(value, asset) {
  const numeric = Number(value || 0);
  const decimals = numeric >= 1000 ? 0 : numeric >= 100 ? 1 : 2;
  return `${numeric.toLocaleString("en-US", { maximumFractionDigits: decimals })} ${asset.unit_label}`;
}

function getActiveAsset() {
  return state.payload?.assets?.find((asset) => asset.key === state.activeKey) || state.payload?.assets?.[0];
}

function renderCards() {
  const grid = $("#asset-grid");
  if (!state.payload?.assets) return;
  grid.innerHTML = state.payload.assets.map((asset) => {
    const kind = assetClasses[asset.key];
    const negative = Number(asset.return_pct) < 0;
    const isDemo = asset.source === "demo";
    return `
      <article class="asset-card ${kind} ${asset.key === state.activeKey ? "active" : ""}" data-asset="${asset.key}" tabindex="0" role="button" aria-label="查看${escapeHTML(asset.label)}收益曲线">
        <div class="asset-card-head">
          <div class="asset-card-name">
            <span class="asset-swatch ${kind}-swatch"></span>
            <h3>${escapeHTML(asset.label)}</h3>
          </div>
          <span class="asset-card-code">${escapeHTML(asset.short_label)}</span>
        </div>
        <div class="asset-card-return ${negative ? "negative" : ""}">${signedPercent(asset.return_pct)}</div>
        <div class="asset-card-meta">
          <div><span>当前市值</span><strong>${money(asset.value, asset.currency)}</strong></div>
          <div><span>累计投入</span><strong>${money(asset.invested, asset.currency)}</strong></div>
        </div>
        <div class="asset-card-footer">
          <span class="asset-source">${formatDate(asset.start_date)} — ${formatDate(asset.end_date)}</span>
          <span class="source-badge ${isDemo ? "demo" : ""}">${isDemo ? "OFFLINE DEMO" : "TUSHARE"}</span>
        </div>
      </article>
    `;
  }).join("");

  grid.querySelectorAll(".asset-card").forEach((card) => {
    const activate = () => {
      state.activeKey = card.dataset.asset;
      renderCards();
      renderActiveAsset();
    };
    card.addEventListener("click", activate);
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        activate();
      }
    });
  });
}

function renderActiveAsset() {
  const asset = getActiveAsset();
  if (!asset) return;
  const source = $("#chart-source");
  $("#chart-title").textContent = asset.label;
  source.textContent = asset.source === "demo" ? "OFFLINE DEMO" : "TUSHARE DATA";
  source.classList.toggle("demo", asset.source === "demo");
  $("#chart-start").textContent = formatDate(asset.start_date);
  $("#chart-end").textContent = formatDate(asset.end_date);
  $("#detail-window").textContent = `${formatDate(asset.start_date)} — ${formatDate(asset.end_date)}`;
  $("#detail-return").textContent = signedPercent(asset.return_pct);
  $("#detail-drawdown").textContent = `${Number(asset.max_drawdown_pct || 0).toFixed(2)}%`;
  drawChart(asset);
}

function sampleCurve(curve, maxPoints = 700) {
  if (curve.length <= maxPoints) return curve;
  const sampled = [];
  const stride = (curve.length - 1) / (maxPoints - 1);
  for (let index = 0; index < maxPoints; index += 1) {
    sampled.push(curve[Math.round(index * stride)]);
  }
  return sampled;
}

function drawChart(asset) {
  const canvas = $("#performance-chart");
  const wrap = $("#chart-wrap");
  const empty = $("#chart-empty");
  const curve = asset.curve || [];
  if (!curve.length) {
    empty.style.display = "grid";
    return;
  }
  empty.style.display = "none";

  const rect = wrap.getBoundingClientRect();
  const width = Math.max(260, rect.width);
  const height = Math.max(240, rect.height);
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const data = sampleCurve(curve);
  const padding = { top: 23, right: 20, bottom: 34, left: 54 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const values = data.flatMap((point) => [Number(point.value), Number(point.invested)]);
  const maxValue = Math.max(...values, 1);
  const minValue = Math.max(0, Math.min(...values) * 0.86);
  const range = Math.max(maxValue - minValue, 1);
  const xFor = (index) => padding.left + (index / Math.max(data.length - 1, 1)) * plotWidth;
  const yFor = (value) => padding.top + (1 - (value - minValue) / range) * plotHeight;

  ctx.font = "9px SFMono-Regular, Consolas, monospace";
  ctx.lineWidth = 1;
  for (let index = 0; index < 5; index += 1) {
    const ratio = index / 4;
    const y = padding.top + ratio * plotHeight;
    ctx.strokeStyle = "rgba(238, 233, 221, 0.09)";
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
    ctx.fillStyle = "rgba(238, 233, 221, 0.32)";
    ctx.fillText(compactNumber(maxValue - ratio * range, asset.currency), 0, y + 3);
  }

  const valuePath = new Path2D();
  const investedPath = new Path2D();
  data.forEach((point, index) => {
    const x = xFor(index);
    const valueY = yFor(Number(point.value));
    const investedY = yFor(Number(point.invested));
    if (index === 0) {
      valuePath.moveTo(x, valueY);
      investedPath.moveTo(x, investedY);
    } else {
      valuePath.lineTo(x, valueY);
      investedPath.lineTo(x, investedY);
    }
  });

  const areaPath = new Path2D(valuePath);
  areaPath.lineTo(xFor(data.length - 1), padding.top + plotHeight);
  areaPath.lineTo(xFor(0), padding.top + plotHeight);
  areaPath.closePath();
  const fill = ctx.createLinearGradient(0, padding.top, 0, padding.top + plotHeight);
  fill.addColorStop(0, "rgba(158, 229, 201, 0.20)");
  fill.addColorStop(1, "rgba(158, 229, 201, 0.005)");
  ctx.fillStyle = fill;
  ctx.fill(areaPath);

  ctx.strokeStyle = "rgba(238, 233, 221, 0.32)";
  ctx.setLineDash([4, 5]);
  ctx.stroke(investedPath);
  ctx.setLineDash([]);
  ctx.strokeStyle = "#9ee5c9";
  ctx.lineWidth = 2;
  ctx.stroke(valuePath);

  const yearLabels = [0, Math.floor((data.length - 1) / 2), data.length - 1];
  ctx.fillStyle = "rgba(238, 233, 221, 0.32)";
  ctx.font = "9px SFMono-Regular, Consolas, monospace";
  yearLabels.forEach((index) => {
    const x = xFor(index);
    const label = data[index]?.date?.slice(0, 7).replace("-", ".") || "";
    ctx.textAlign = index === 0 ? "left" : index === data.length - 1 ? "right" : "center";
    ctx.fillText(label, x, height - 9);
  });
  ctx.textAlign = "left";

  state.chart = { data, xFor, yFor, padding, width, height };
}

function hideTooltip() {
  $("#chart-tooltip").classList.remove("visible");
}

function handleChartPointer(event) {
  if (!state.chart) return;
  const wrap = $("#chart-wrap");
  const tooltip = $("#chart-tooltip");
  const bounds = wrap.getBoundingClientRect();
  const localX = Math.max(state.chart.padding.left, Math.min(bounds.width - state.chart.padding.right, event.clientX - bounds.left));
  const ratio = (localX - state.chart.padding.left) / (bounds.width - state.chart.padding.left - state.chart.padding.right);
  const index = Math.max(0, Math.min(state.chart.data.length - 1, Math.round(ratio * (state.chart.data.length - 1))));
  const point = state.chart.data[index];
  const asset = getActiveAsset();
  if (!point || !asset) return;
  tooltip.innerHTML = `
    <div class="tooltip-date">${formatDate(point.date, true)}</div>
    <div class="tooltip-line"><span>账户市值</span><strong>${money(point.value, asset.currency)}</strong></div>
    <div class="tooltip-line invested"><span>累计投入</span><strong>${money(point.invested, asset.currency)}</strong></div>
  `;
  tooltip.style.left = `${Math.min(Math.max(localX, 16), bounds.width - 158)}px`;
  tooltip.style.top = `${Math.max(8, state.chart.yFor(Number(point.value)) - 36)}px`;
  tooltip.classList.add("visible");
}

function updateStatus() {
  if (!state.payload?.assets) return;
  const hasDemo = state.payload.assets.some((asset) => asset.source === "demo");
  const hasLive = state.payload.assets.some((asset) => asset.source !== "demo");
  $("#data-status").textContent = hasDemo && hasLive
    ? "部分使用离线演示数据"
    : hasDemo ? "离线演示数据 · 可接入 Tushare" : state.payload.record
      ? `回测已保存 · ${state.payload.record.id}`
      : "Tushare 历史数据已载入";
  $("#today-readout").textContent = state.payload.generated_at
    ? `CALCULATED ${state.payload.generated_at.replace("T", " ")}`
    : "—";
}

async function loadBacktest({ save = false } = {}) {
  const button = document.querySelector(".run-button");
  const originalText = button.querySelector("span").textContent;
  button.disabled = true;
  button.querySelector("span").textContent = "计算中…";
  document.body.classList.add("is-loading");

  const start = $("#start-date").value || "2014-01-15";
  const params = new URLSearchParams({
    start_date: start.replaceAll("-", ""),
    amount_csi300: $("#amount-csi").value || "100",
    amount_spx: $("#amount-spx").value || "100",
    amount_gold: $("#amount-gold").value || "100",
  });
  if (save) params.set("save", "1");

  try {
    const response = await fetch(`/api/backtest?${params.toString()}`);
    const payload = await response.json();
    if (!payload.ok) throw new Error(payload.error || "回测失败");
    state.payload = payload;
    if (!payload.assets.some((asset) => asset.key === state.activeKey)) state.activeKey = payload.assets[0].key;
    renderCards();
    renderActiveAsset();
    updateStatus();
    const archiveNote = $("#archive-note");
    if (payload.record) {
      archiveNote.classList.add("saved");
      archiveNote.querySelector("p").textContent = `已保存：${payload.record.id} · ${payload.record.path}`;
    } else {
      archiveNote.classList.remove("saved");
      archiveNote.querySelector("p").textContent = "当前为预览结果；点击“运行并保存”后，完整数据会写入本地回测档案。";
    }
  } catch (error) {
    $("#data-status").textContent = `回测暂不可用 · ${error.message}`;
    $("#chart-empty").textContent = "请通过 server.py 启动本地回测服务";
    $("#chart-empty").style.display = "grid";
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = originalText;
    document.body.classList.remove("is-loading");
  }
}

$("#backtest-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadBacktest({ save: true });
});

$("#chart-wrap").addEventListener("pointermove", handleChartPointer);
$("#chart-wrap").addEventListener("pointerleave", hideTooltip);
window.addEventListener("resize", () => {
  if (state.payload) drawChart(getActiveAsset());
});

$("#today-readout").textContent = `DEFAULT ${new Date().getFullYear()}`;
loadBacktest({ save: false });
