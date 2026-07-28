// Tiny WebRTC signalling relay for "PLAY ONLINE" room codes.
//
// The browsers still talk peer-to-peer; this endpoint only passes the two SDP
// blobs between them so players exchange a 4-character code instead of pasting
// a 4KB blob twice.
//
// Storage: Vercel KV / Upstash Redis over its REST API when the env vars are
// present (survives across lambda instances — this is the reliable path), with
// an in-memory Map fallback so local `vercel dev` and single-instance
// deployments still work.
//
//   POST /api/signal  {room, role:'offer'|'answer', sdp}   -> {ok:true}
//   GET  /api/signal?room=ABCD&role=offer|answer           -> {sdp} | 404
//
// Entries expire after ROOM_TTL seconds so codes can be reused.

const ROOM_TTL = 600;

const KV_URL =
  process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL || '';
const KV_TOKEN =
  process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN || '';
const hasKV = !!(KV_URL && KV_TOKEN);

const mem = new Map(); // key -> {sdp, exp}

async function kv(path) {
  const r = await fetch(`${KV_URL}/${path}`, {
    headers: { Authorization: `Bearer ${KV_TOKEN}` },
  });
  if (!r.ok) throw new Error(`kv ${r.status}`);
  return r.json();
}

async function put(key, sdp) {
  if (hasKV) {
    await kv(`set/${encodeURIComponent(key)}/${encodeURIComponent(sdp)}?EX=${ROOM_TTL}`);
    return;
  }
  mem.set(key, { sdp, exp: Date.now() + ROOM_TTL * 1000 });
}

async function get(key) {
  if (hasKV) {
    const j = await kv(`get/${encodeURIComponent(key)}`);
    return j && j.result ? j.result : null;
  }
  const e = mem.get(key);
  if (!e) return null;
  if (e.exp < Date.now()) { mem.delete(key); return null; }
  return e.sdp;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'content-type');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();

  try {
    if (req.method === 'POST') {
      const body =
        typeof req.body === 'string' ? JSON.parse(req.body || '{}') : req.body || {};
      const { room, role, sdp } = body;
      if (!room || !role || !sdp) return res.status(400).json({ error: 'room, role and sdp required' });
      if (!/^[A-Z0-9]{4,8}$/.test(room)) return res.status(400).json({ error: 'bad room code' });
      if (role !== 'offer' && role !== 'answer') return res.status(400).json({ error: 'bad role' });
      if (sdp.length > 60000) return res.status(413).json({ error: 'sdp too large' });
      await put(`nce:${room}:${role}`, sdp);
      return res.status(200).json({ ok: true, store: hasKV ? 'kv' : 'memory' });
    }

    if (req.method === 'GET') {
      const room = String(req.query.room || '').toUpperCase();
      const role = String(req.query.role || '');
      if (!/^[A-Z0-9]{4,8}$/.test(room) || (role !== 'offer' && role !== 'answer'))
        return res.status(400).json({ error: 'room and role required' });
      const sdp = await get(`nce:${room}:${role}`);
      if (!sdp) return res.status(404).json({ error: 'not ready' });
      return res.status(200).json({ sdp });
    }

    return res.status(405).json({ error: 'method not allowed' });
  } catch (e) {
    return res.status(500).json({ error: String((e && e.message) || e) });
  }
}
