import { fixed, signed, badgeReading, money, selectPoints } from './format.js';

const $ = selector => document.querySelector(selector);
const state = { data: null, range: '1y', series: 'compare', hover: null };
const chart = $('#chart');
const stage = $('#chart-stage');
let chartModel = null;
const arrow = value => value === null || value === 0 ? '·' : value > 0 ? '↗' : '↘';
const badge = (index, change) => {
  const reading = badgeReading(index, change);
  const comparison = change === null ? '无上一条数据' : `较上一交易日 ${signed(change)} 点`;
  return `<span class="change-badge ${reading.direction}" title="指数 ${reading.text}（累计收益率 ${reading.text}%）；${comparison}" aria-label="指数 ${reading.text}；${comparison}"><span aria-hidden="true">${arrow(change)}</span>${reading.text}</span>`;
};

function sparkline(asset) {
  const points = asset.points.slice(-60);
  const values = points.map(p => p[1]);
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const line = points.map((p, i) => `${(i / Math.max(1, points.length - 1) * 91 + 2).toFixed(1)},${(46 - (p[1] - min) / span * 41).toFixed(1)}`).join(' ');
  return `<svg class="sparkline" viewBox="0 0 95 50" aria-hidden="true"><polyline points="${line}" fill="none" stroke="${asset.color}" stroke-width="1.7" stroke-linejoin="round"/></svg>`;
}

function renderCards() {
  const assets = state.data.assets.filter(asset => asset.key !== 'portfolio');
  $('#asset-grid').innerHTML = assets.map(asset => `<button class="asset-card ${state.series === asset.key ? 'active' : ''}" data-asset="${asset.key}" aria-label="查看${asset.name}历史曲线，指数${fixed(asset.index)}，日变动${signed(asset.change)}点"><div class="card-top"><span class="asset-name">${asset.name}</span><span class="category">${asset.category}</span></div><div class="ticker">${asset.ticker}</div><div class="card-bottom"><div><div class="index-value">${fixed(asset.index)}</div><div class="change-line">${badge(asset.index, asset.change)}<span class="change-label">累计收益读数</span></div></div>${sparkline(asset)}</div><div class="card-date">${asset.date.replaceAll('-', '.')} <span aria-hidden="true">·</span> 指数点</div></button>`).join('');
  $('#asset-grid').setAttribute('aria-busy', 'false');
  const portfolio = state.data.assets.find(asset => asset.key === 'portfolio');
  $('#ledger-values').innerHTML = `<div class="ledger-item"><span>累计投入 / CNY</span><strong>${money(portfolio.invested)}</strong></div><div class="ledger-item"><span>当前市值 / CNY</span><strong>${money(portfolio.value)}</strong></div><div class="ledger-item"><span>账面盈亏 / CNY</span><strong>${portfolio.value >= portfolio.invested ? '+' : '−'}${money(Math.abs(portfolio.value - portfolio.invested))}</strong></div><div class="ledger-item"><span>组合指数 / 点</span><strong>${fixed(portfolio.index)}</strong>${badge(portfolio.index, portfolio.change)}</div>`;
}

function renderStatus() {
  const data = state.data;
  $('#data-status').textContent = `数据截至 ${data.asOf.replaceAll('-', '.')}`;
  const notices = [];
  if (data.isFallback) notices.push(`实时数据源暂不可用，正在展示部署时保存的 ${data.asOf} 快照，而非最新行情。`);
  if (data.earliestAsOf !== data.asOf) notices.push('部分资产数据日期不同，请以各卡片日期为准；组合包含最近一次可用估值。');
  const age = Math.floor((Date.now() - Date.parse(`${data.asOf}T00:00:00+08:00`)) / 86400000);
  if (age >= 7 && !data.isFallback) notices.push(`最新记录距今 ${age} 天。节假日不产生新数据；如超过正常休市期，请检查仓库更新状态。`);
  $('#notice').textContent = notices.join(' ');
  $('#notice').hidden = !notices.length;
}

function renderChart() {
  if (!state.data) return;
  const selected = state.data.assets.filter(asset => state.series === 'compare' ? asset.key !== 'portfolio' : asset.key === state.series);
  const end = selected.map(asset => asset.date).sort().at(-1);
  const series = selected.map(asset => ({ ...asset, visible: selectPoints(asset.points, state.range, end) }));
  const dates = [...new Set(series.flatMap(asset => asset.visible.map(p => p[0])))].sort();
  if (!dates.length) {
    chart.innerHTML = '<text x="30" y="60" fill="#74776f">这个区间暂无数据</text>';
    chartModel = null;
    return;
  }
  const width = Math.max(280, stage.clientWidth), height = width < 500 ? 250 : 330;
  const pad = { left: 45, right: 16, top: 16, bottom: 34 };
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  const values = series.flatMap(asset => asset.visible.map(p => p[1]));
  let low = Math.min(...values), high = Math.max(...values);
  const margin = Math.max((high - low) * .1, 1);
  low -= margin; high += margin;
  const t0 = Date.parse(dates[0]), t1 = Date.parse(dates.at(-1));
  const x = day => pad.left + (t1 === t0 ? .5 : (Date.parse(day) - t0) / (t1 - t0)) * plotW;
  const y = value => pad.top + (high - value) / (high - low) * plotH;
  chart.setAttribute('viewBox', `0 0 ${width} ${height}`);
  chart.setAttribute('tabindex', '0');
  chart.setAttribute('aria-label', `${series.map(asset => asset.name).join('、')}指数历史，从${dates[0]}至${dates.at(-1)}。指数点数，不是百分比。左右方向键可查看历史读数。`);
  const parts = [];
  for (let i = 0; i <= 4; i++) {
    const value = low + (high - low) * i / 4;
    parts.push(`<line x1="${pad.left}" y1="${y(value)}" x2="${width - pad.right}" y2="${y(value)}" stroke="#ece9e1" stroke-dasharray="3 4"/><text x="${pad.left - 12}" y="${y(value) + 3}" text-anchor="end" fill="#74776f" font-family="monospace" font-size="10">${value.toFixed(high - low < 10 ? 1 : 0)}</text>`);
  }
  if (low <= 0 && high >= 0) parts.push(`<line x1="${pad.left}" y1="${y(0)}" x2="${width - pad.right}" y2="${y(0)}" stroke="#b4afa2" stroke-dasharray="5 4"/><text x="${width - pad.right}" y="${y(0) - 6}" text-anchor="end" fill="#74776f" font-size="9">回本线</text>`);
  const ticks = width < 500 ? 3 : 5;
  for (let i = 0; i < ticks; i++) {
    const day = dates[Math.round(i / (ticks - 1) * (dates.length - 1))];
    const label = state.range === '1m' ? day.slice(5) : day.slice(0, 7);
    parts.push(`<text x="${x(day)}" y="${height - 10}" text-anchor="${i === 0 ? 'start' : i === ticks - 1 ? 'end' : 'middle'}" fill="#74776f" font-size="10" font-family="monospace">${label}</text>`);
  }
  for (const asset of series) {
    const points = asset.visible.map(p => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ');
    parts.push(`<polyline points="${points}" fill="none" stroke="${asset.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`);
    const last = asset.visible.at(-1);
    if (last) parts.push(`<circle cx="${x(last[0])}" cy="${y(last[1])}" r="3" fill="${asset.color}" stroke="#fdfcf9" stroke-width="1.5"/>`);
  }
  parts.push('<g id="crosshair" visibility="hidden"></g>');
  chart.innerHTML = parts.join('');
  $('#chart-legend').innerHTML = series.map(asset => `<span class="legend-item"><span class="legend-swatch" style="background:${asset.color}"></span>${asset.name}</span>`).join('');
  $('#chart-dates').textContent = `${dates[0].replaceAll('-', '.')} — ${dates.at(-1).replaceAll('-', '.')}`;
  chartModel = { dates, series, x, y, width, height, pad, byDate: series.map(asset => new Map(asset.visible.map(p => [p[0], p]))) };
  hideTooltip();
}

function showTooltip(index) {
  const model = chartModel;
  if (!model) return;
  index = Math.max(0, Math.min(model.dates.length - 1, index));
  state.hover = index;
  const day = model.dates[index], px = model.x(day);
  const dots = [], rows = [];
  model.series.forEach((asset, i) => {
    const point = model.byDate[i].get(day);
    rows.push(`<div class="tooltip-row"><span>${asset.name}</span><strong>${point ? fixed(point[1]) : '无记录'}</strong></div>`);
    if (point) dots.push(`<circle cx="${px}" cy="${model.y(point[1])}" r="4" fill="${asset.color}" stroke="#fdfcf9" stroke-width="2"/>`);
  });
  const crosshair = $('#crosshair');
  crosshair.setAttribute('visibility', 'visible');
  crosshair.innerHTML = `<line x1="${px}" y1="${model.pad.top}" x2="${px}" y2="${model.height - model.pad.bottom}" stroke="#aaa69a" stroke-dasharray="3 3"/>${dots.join('')}`;
  const tooltip = $('#chart-tooltip');
  tooltip.innerHTML = `<div class="tooltip-date">${day} · 指数点</div>${rows.join('')}`;
  tooltip.hidden = false;
  const left = px + 15 + tooltip.offsetWidth > model.width ? px - tooltip.offsetWidth - 15 : px + 15;
  tooltip.style.left = `${Math.max(4, left)}px`;
  tooltip.style.top = '12px';
}

function hideTooltip() {
  state.hover = null;
  $('#chart-tooltip').hidden = true;
  $('#crosshair')?.setAttribute('visibility', 'hidden');
}

chart.addEventListener('pointermove', event => {
  if (!chartModel) return;
  const px = (event.clientX - chart.getBoundingClientRect().left) * chartModel.width / chart.getBoundingClientRect().width;
  let nearest = 0, distance = Infinity;
  chartModel.dates.forEach((day, i) => { const d = Math.abs(chartModel.x(day) - px); if (d < distance) { distance = d; nearest = i; } });
  showTooltip(nearest);
});
chart.addEventListener('pointerleave', hideTooltip);
chart.addEventListener('blur', hideTooltip);
chart.addEventListener('keydown', event => {
  if (!chartModel) return;
  if (['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Escape'].includes(event.key)) event.preventDefault();
  if (event.key === 'Escape') return hideTooltip();
  if (event.key === 'Home') return showTooltip(0);
  if (event.key === 'End') return showTooltip(chartModel.dates.length - 1);
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') showTooltip((state.hover ?? chartModel.dates.length - 1) + (event.key === 'ArrowLeft' ? -1 : 1));
});

function chooseSeries(key) {
  state.series = key;
  document.querySelectorAll('[data-series]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.series === key)));
  if (state.data) { renderCards(); renderChart(); }
}
$('#series-controls').addEventListener('click', event => { const button = event.target.closest('[data-series]'); if (button) chooseSeries(button.dataset.series); });
$('#asset-grid').addEventListener('click', event => { const button = event.target.closest('[data-asset]'); if (button) chooseSeries(button.dataset.asset); });
$('#ranges').addEventListener('click', event => {
  const button = event.target.closest('[data-range]');
  if (!button) return;
  state.range = button.dataset.range;
  document.querySelectorAll('[data-range]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  renderChart();
});
new ResizeObserver(() => renderChart()).observe(stage);

async function load() {
  $('#retry').disabled = true;
  $('#error').hidden = true;
  $('#data-status').textContent = '正在读取公开账本…';
  try {
    const response = await fetch('/api/index', { signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (data.schemaVersion !== 1 || !Array.isArray(data.assets) || data.assets.length !== 4) throw new Error('Invalid data');
    state.data = data;
    renderCards(); renderStatus(); renderChart();
  } catch (error) {
    console.error('Data loading failed:', error);
    $('#error').hidden = false;
    $('#data-status').textContent = '数据暂不可用';
    $('#asset-grid').setAttribute('aria-busy', 'false');
    if (!state.data) {
      $('#asset-grid').innerHTML = '';
      $('#ledger-values').textContent = '暂无可用账本';
    }
  } finally {
    $('#retry').disabled = false;
  }
}
$('#retry').addEventListener('click', load);
load();
