import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import worker from '../src/worker.mjs';

const csv = await readFile(new URL('../../data/export/daily_returns.csv', import.meta.url), 'utf8');
const request = () => new Request('https://example.com/api/index');

test('API fetches, caches and serves validated public data', async t => {
  const pending = [];
  let stored;
  t.mock.method(globalThis, 'fetch', async () => new Response(csv));
  const oldCache = globalThis.caches;
  globalThis.caches = { default: { match: async () => undefined, put: async (key, response) => { stored = response; } } };
  t.after(() => { globalThis.caches = oldCache; });
  const response = await worker.fetch(request(), {}, { waitUntil: promise => pending.push(promise) });
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.equal(data.isFallback, false);
  assert.equal(data.assets.length, 4);
  await Promise.all(pending);
  assert.ok(stored);
  globalThis.caches.default.match = async () => stored.clone();
  assert.equal((await (await worker.fetch(request(), {}, {})).json()).asOf, data.asOf);
});

test('upstream failure explicitly labels the packaged snapshot as fallback', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('unavailable', { status: 503 }));
  const oldCache = globalThis.caches;
  globalThis.caches = { default: { match: async () => undefined } };
  t.after(() => { globalThis.caches = oldCache; });
  const env = { ASSETS: { fetch: async () => Response.json({ asOf: '2026-09-30', isFallback: false }) } };
  const response = await worker.fetch(request(), env, {});
  assert.equal((await response.json()).isFallback, true);
  env.ASSETS.fetch = async () => new Response('missing', { status: 404 });
  assert.equal((await worker.fetch(request(), env, {})).status, 503);
});

test('rejects writes and unknown API routes', async () => {
  assert.equal((await worker.fetch(new Request('https://example.com/api/index', { method: 'POST' }), {}, {})).status, 405);
  assert.equal((await worker.fetch(new Request('https://example.com/api/missing'), {}, {})).status, 404);
});
