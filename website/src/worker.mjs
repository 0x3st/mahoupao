import { parseReturns, SOURCE_URL } from './data.mjs';

function json(data, status = 200, cache = 'public, max-age=60, s-maxage=300') {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': cache,
      'X-Content-Type-Options': 'nosniff',
      'Access-Control-Allow-Origin': '*',
    },
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname !== '/api/index') {
      if (url.pathname.startsWith('/api/')) return json({ error: 'Not found' }, 404, 'no-store');
      return env.ASSETS.fetch(request);
    }
    if (request.method !== 'GET') return new Response('Method not allowed', { status: 405, headers: { Allow: 'GET' } });
    // Ignore arbitrary query parameters to avoid duplicate cache entries.
    const cacheKey = new Request(`${url.origin}/api/index`);
    const cache = caches.default;
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
    try {
      const upstream = await fetch(SOURCE_URL, {
        headers: { Accept: 'text/csv', 'User-Agent': 'Mahoupao-Index/1.0' },
        signal: AbortSignal.timeout(10000),
        cf: { cacheTtl: 300, cacheEverything: true },
      });
      if (!upstream.ok) throw new Error(`Upstream status ${upstream.status}`);
      const data = parseReturns(await upstream.text());
      const response = json({ ...data, fetchedAt: new Date().toISOString(), isFallback: false });
      ctx.waitUntil(cache.put(cacheKey, response.clone()).catch(error => console.error('Cache write failed', error.message)));
      return response;
    } catch (error) {
      console.error('Live data unavailable:', error.message);
      try {
        const snapshot = await env.ASSETS.fetch(new Request(new URL('/snapshot.json', url)));
        if (!snapshot.ok) throw new Error('Snapshot missing');
        const data = await snapshot.json();
        return json({ ...data, isFallback: true }, 200, 'public, max-age=30');
      } catch {
        return json({ error: '暂时无法读取数据，请稍后重试。' }, 503, 'no-store');
      }
    }
  },
};
