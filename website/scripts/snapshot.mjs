import { readFile, writeFile } from 'node:fs/promises';
import { parseReturns } from '../src/data.mjs';

const csv = await readFile(new URL('../../data/export/daily_returns.csv', import.meta.url), 'utf8');
const data = parseReturns(csv);
await writeFile(new URL('../public/snapshot.json', import.meta.url), JSON.stringify({
  ...data, fetchedAt: null, builtAt: new Date().toISOString(), isFallback: true,
}));
console.log(`Built fallback snapshot through ${data.asOf}; ${data.assets.length} series.`);
