// Cloudflare Pages Function — same-origin proxy for the Tavily Search API.
// Bahi's CA Lookup uses a BYO Tavily key; the browser can't call api.tavily.com
// directly (CORS + the key would be exposed in client code), so this forwards
// the user's key. Stateless: the key is read from the request header and passed
// straight through — never logged, never stored. Deploys with Cloudflare Pages
// (functions/ dir); the client calls it at the same origin: POST /api/tavily.
//
// Request:  POST /api/tavily   header  x-tavily-key: tvly-...
//           body { query, max_results?, search_depth? }
// Response: Tavily's JSON passed through (status preserved).

function cors(origin) {
  return {
    'content-type': 'application/json',
    'access-control-allow-origin': origin,
    'access-control-allow-methods': 'POST, OPTIONS',
    'access-control-allow-headers': 'content-type, x-tavily-key',
  };
}

export async function onRequestOptions(context) {
  const origin = new URL(context.request.url).origin;
  return new Response(null, { status: 204, headers: cors(origin) });
}

export async function onRequestPost(context) {
  const { request } = context;
  const origin = new URL(request.url).origin;
  const headers = cors(origin);

  const key = request.headers.get('x-tavily-key') || '';
  if (!key) return new Response(JSON.stringify({ error: 'Missing Tavily key' }), { status: 401, headers });

  let body;
  try { body = await request.json(); } catch (_) {
    return new Response(JSON.stringify({ error: 'Invalid JSON body' }), { status: 400, headers });
  }
  const query = String((body && body.query) || '').trim().slice(0, 400);
  if (!query) return new Response(JSON.stringify({ error: 'Empty query' }), { status: 400, headers });

  const payload = {
    query,
    search_depth: body && body.search_depth === 'advanced' ? 'advanced' : 'basic',
    max_results: Math.min(Math.max(parseInt((body && body.max_results), 10) || 5, 1), 10),
    include_answer: false,
    include_raw_content: false,
  };

  let res;
  try {
    res = await fetch('https://api.tavily.com/search', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'authorization': 'Bearer ' + key },
      body: JSON.stringify(payload),
    });
  } catch (_) {
    return new Response(JSON.stringify({ error: 'Tavily request failed' }), { status: 502, headers });
  }

  // Pass Tavily's response straight through (status preserved). No logging.
  const text = await res.text();
  return new Response(text, { status: res.status, headers });
}
