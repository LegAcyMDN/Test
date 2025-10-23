// src/utils/shardReporter.js
import { supabase } from '../supabase.js';

const wait = (ms) => new Promise(r => setTimeout(r, ms));

function getMetrics(client) {
  const ping = Math.max(-1, Math.round(client.ws.ping));
  const guilds = client.guilds.cache.size;
  const users = client.guilds.cache.reduce((a, g) => a + (g.memberCount || 0), 0);
  const uptimeSeconds = Math.floor((client.uptime || 0) / 1000);

  return { ping, guilds, users, uptimeSeconds };
}

// Upsert status + métriques pour CE shard
async function upsertShardRow(client, statusOverride = null) {
  const shardId = client.shard?.ids?.[0] ?? 0;
  const status = statusOverride ?? 'online';
  const { ping, guilds, users, uptimeSeconds } = getMetrics(client);

  const payload = {
    shard_id: shardId,
    status,
    guilds_count: guilds,
    users_count: users,
    ping,
    uptime_seconds: uptimeSeconds,
    last_heartbeat: new Date().toISOString(),
    updated_at: new Date().toISOString()
  };

  const { error } = await supabase
    .from('bot_shards')
    .upsert(payload, { onConflict: 'shard_id' });
  if (error) throw error;
}

export function startShardReporter(client) {
  const shardId = client.shard?.ids?.[0] ?? 0;
  const baseInterval = parseInt(process.env.SHARD_REPORT_INTERVAL || '15000', 10);
  const timeoutMs = parseInt(process.env.SHARD_REPORT_TIMEOUT || '5000', 10);
  const jitter = Math.floor(Math.random() * 3000); // évite un thundering herd
  let stopped = false;

  // 1) Premier upsert dès que possible
  (async () => {
    try { await upsertShardRow(client, 'online'); } catch (e) { console.error('[shardReporter] first upsert failed:', e.message || e); }
  })();

  // 2) Boucle heartbeat
  (async () => {
    while (!stopped) {
      const start = Date.now();
      try {
        // timeout "manuel"
        const p = upsertShardRow(client);
        const timed = Promise.race([
          p,
          new Promise((_, rej) => setTimeout(() => rej(new Error('supabase timeout')), timeoutMs))
        ]);
        await timed;
      } catch (e) {
        console.error(`[shardReporter] upsert shard #${shardId} failed:`, e.message || e);
      }
      const elapsed = Date.now() - start;
      const sleep = Math.max(1000, baseInterval + jitter - elapsed);
      await wait(sleep);
    }
  })();

  // 3) Expose un stopper propre
  const stop = async (status = 'offline') => {
    stopped = true;
    try { await upsertShardRow(client, status); } catch {}
  };

  // 4) Hooks process (graceful)
  const onExit = async () => {
    await stop('offline');
    process.exit(0);
  };
  process.on('SIGTERM', onExit);
  process.on('SIGINT', onExit);
  process.on('beforeExit', async () => { await stop('offline'); });

  // 5) Hooks gateway (mise à jour du statut)
  client.on('shardDisconnect', async (_event, id) => {
    if (id !== shardId) return;
    try { await upsertShardRow(client, 'disconnected'); } catch {}
  });

  client.on('shardResume', async (id) => {
    if (id !== shardId) return;
    try { await upsertShardRow(client, 'online'); } catch {}
  });

  client.on('shardError', async (_err, id) => {
    if (id !== shardId) return;
    try { await upsertShardRow(client, 'error'); } catch {}
  });

  return { stop };
}
