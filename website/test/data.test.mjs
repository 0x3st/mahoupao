import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { ASSETS, parseReturns } from '../src/data.mjs';
import { fixed, signed, direction, badgeReading, selectPoints } from '../public/format.js';

export function fixture() {
  return 'asset_key,trade_date,invested,value,return_pct,daily_return_pct\n' + ASSETS.map(asset => [
    `${asset.key},2026-09-29,100,120,20,999`,
    `${asset.key},2026-09-30,200,238,19,-999`,
  ].join('\n')).join('\n');
}

test('API separates the index level from daily change used for badge color', () => {
  const data = parseReturns(fixture());
  assert.equal(data.asOf, '2026-09-30');
  for (const asset of data.assets) {
    assert.equal(asset.index, 19);
    assert.equal(asset.change, -1);
    assert.equal(asset.previousDate, '2026-09-29');
  }
});

test('sorts dates and handles a single observation without invented change', () => {
  const data = parseReturns(fixture().split('\n').filter(line => !line.includes('2026-09-29')).join('\n'));
  assert.equal(data.assets[0].change, null);
  const lines = fixture().split('\n');
  assert.equal(parseReturns([lines[0], ...lines.slice(1).reverse()].join('\n')).assets[0].change, -1);
});

test('rejects bad schema, invalid numbers, dates, duplicates and incomplete data', () => {
  assert.throws(() => parseReturns('hello'));
  assert.throws(() => parseReturns(fixture().replace(',120,', ',NaN,')));
  assert.throws(() => parseReturns(fixture().replace(',120,', ',,')));
  assert.throws(() => parseReturns(fixture().replace(',20,999', ',30,999')));
  assert.throws(() => parseReturns(fixture().replace('2026-09-29', '2026-02-30')));
  assert.throws(() => parseReturns(fixture() + '\n' + fixture().split('\n')[1]));
  assert.throws(() => parseReturns(fixture().split('\n').filter(line => !line.startsWith('gold,')).join('\n')));
});

test('actual repository data is valid and daily changes match consecutive records', async () => {
  const csv = await readFile(new URL('../../data/export/daily_returns.csv', import.meta.url), 'utf8');
  const data = parseReturns(csv);
  for (const asset of data.assets) {
    assert.ok(asset.points.length > 250);
    assert.equal(asset.change, Number((asset.points.at(-1)[1] - asset.points.at(-2)[1]).toFixed(4)));
  }
});

test('display is point-based, including negative readings and no observation', () => {
  assert.equal(fixed(18.1298), '18.13');
  assert.equal(signed(.4206), '+0.42');
  assert.equal(signed(-.1446), '−0.14');
  assert.equal(signed(3.2495), '+3.25');
  assert.equal(signed(null), '—');
  assert.equal(direction(null), 'flat');
  assert.equal(direction(-1), 'down');
  assert.equal(direction(1), 'up');
});

test('badge number is the cumulative percentage without %, color is daily direction', () => {
  const cases = [
    [18.1298, .4206, '+18.13', 'up'],
    [65.7024, -.1446, '+65.70', 'down'],
    [149.7015, 3.2495, '+149.70', 'up'],
    [-9, 1, '−9.00', 'up'],
    [-12, -2, '−12.00', 'down'],
    [25, 0, '+25.00', 'flat'],
    [25, null, '+25.00', 'flat'],
  ];
  for (const [index, change, text, color] of cases) {
    assert.deepEqual(badgeReading(index, change), { text, direction: color });
  }
});

test('range selection never rebases the index', () => {
  const points = [['2020-01-01', 0], ['2026-09-01', 20], ['2026-09-30', 19]];
  assert.deepEqual(selectPoints(points, '1m', '2026-09-30'), points.slice(1));
  assert.equal(selectPoints(points, 'all', '2026-09-30'), points);
});
