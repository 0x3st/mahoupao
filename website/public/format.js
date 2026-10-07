export const fixed = value => Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const signed = value => value === null ? '—' : `${value < 0 && Math.abs(value) >= 0.005 ? '−' : '+'}${fixed(Math.abs(value))}`;
export const direction = value => value === null || value === 0 ? 'flat' : value > 0 ? 'up' : 'down';
export const badgeReading = (index, change) => ({ text: signed(index), direction: direction(change) });
export const money = value => `¥${Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;

export function selectPoints(points, range, endDate) {
  if (range === 'all') return points;
  const days = { '1m': 31, '1y': 365, '3y': 1095 }[range];
  const cutoff = new Date(Date.parse(endDate) - days * 86400000).toISOString().slice(0, 10);
  return points.filter(point => point[0] >= cutoff);
}
