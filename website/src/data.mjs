export const SOURCE_URL = 'https://raw.githubusercontent.com/0x3st/mahoupao/main/data/export/daily_returns.csv';
export const ASSETS = [
  { key: 'csi300', name: '沪深300', ticker: '510300.SH', category: '中国股票', color: '#426258' },
  { key: 'spx', name: '标普500', ticker: '513500.SH', category: '美股 · QDII', color: '#496a94' },
  { key: 'gold', name: '黄金', ticker: '518880.SH', category: '黄金资产', color: '#b58636' },
  { key: 'portfolio', name: '定投组合', ticker: '等额投入 · 不再平衡', category: '组合账本', color: '#b84736' },
];

// Only the project's numeric, unquoted CSV schema is accepted. Never use
// daily_return_pct: badge text is the index level, color uses its daily change.
export function parseReturns(csv) {
  const lines = csv.trim().replace(/^\uFEFF/, '').split(/\r?\n/);
  const fields = lines.shift().split(',');
  const columns = ['asset_key', 'trade_date', 'invested', 'value', 'return_pct'];
  if (columns.some(key => !fields.includes(key))) throw new Error('Unexpected CSV schema');
  const grouped = Object.fromEntries(ASSETS.map(asset => [asset.key, new Map()]));
  for (const line of lines) {
    if (!line.trim()) continue;
    const cells = line.split(',');
    if (cells.length !== fields.length) throw new Error('Malformed CSV row');
    const row = Object.fromEntries(fields.map((field, i) => [field, cells[i]]));
    if (!grouped[row.asset_key]) throw new Error('Unknown asset');
    const day = row.trade_date;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !Number.isFinite(Date.parse(day)) || new Date(day).toISOString().slice(0, 10) !== day) throw new Error('Invalid date');
    const numbers = ['return_pct', 'invested', 'value'].map(key => row[key].trim() === '' ? NaN : Number(row[key]));
    const [index, invested, value] = numbers;
    if (!numbers.every(Number.isFinite) || invested <= 0 || value < 0) throw new Error('Invalid account data');
    if (Math.abs(index - (value / invested - 1) * 100) > 0.02) throw new Error('Inconsistent account return');
    if (grouped[row.asset_key].has(day)) throw new Error('Duplicate observation');
    // Compact transport: [date, index, invested CNY, value CNY].
    grouped[row.asset_key].set(day, [day, index, invested, value]);
  }
  const assets = ASSETS.map(asset => {
    const points = [...grouped[asset.key].values()].sort((a, b) => a[0].localeCompare(b[0]));
    if (!points.length) throw new Error(`Missing asset: ${asset.key}`);
    const latest = points.at(-1);
    const previous = points.at(-2);
    return {
      ...asset, points, date: latest[0], index: latest[1], invested: latest[2], value: latest[3],
      change: previous ? Number((latest[1] - previous[1]).toFixed(4)) : null,
      previousDate: previous?.[0] ?? null,
    };
  });
  const dates = assets.map(asset => asset.date).sort();
  return { schemaVersion: 1, asOf: dates.at(-1), earliestAsOf: dates[0], startDate: assets[0].points[0][0], source: SOURCE_URL, assets };
}
