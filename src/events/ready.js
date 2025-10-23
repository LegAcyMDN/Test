import { startShardReporter } from '../utils/shardReporter.js';


export const name = 'ready';
export const once = true;

export async function execute(client) {
  const shardId = client.shard?.ids?.[0] ?? 0;
  const shardCount = client.shard?.count ?? 1;

  // Récupère un snapshot de tous les shards (si manager sharde réellement)
  let snapshot = [];
  try {
    snapshot = await client.shard?.broadcastEval(c => ({
      id: c.shard.ids[0],
      ping: Math.round(c.ws.ping),
      guilds: c.guilds.cache.size,
      users: c.guilds.cache.reduce((a, g) => a + g.memberCount, 0)
    })) ?? [];
  } catch { /* pas de sharding "multi" → ignore */ }

  console.log(`────────────────────────────────────────`);
  console.log(`✅ ${client.user.tag} en ligne`);
  console.log(`🧩 Shard courant: #${shardId}/${shardCount - 1}`);
  if (snapshot.length) {
    const totalGuilds = snapshot.reduce((a, s) => a + s.guilds, 0);
    const totalUsers  = snapshot.reduce((a, s) => a + s.users, 0);
    const avgPing     = Math.round(snapshot.reduce((a, s) => a + s.ping, 0) / snapshot.length);
    console.log(`📊 Shards actifs: ${snapshot.length} | Ping moyen: ${avgPing}ms | Guilds: ${totalGuilds} | Users: ${totalUsers}`);
    snapshot.sort((a,b)=>a.id-b.id).forEach(s =>
      console.log(`   #${s.id} → ping=${s.ping}ms | guilds=${s.guilds} | users=${s.users}`)
    );
  } else {
    console.log(`📊 Guilds (shard): ${client.guilds.cache.size}`);
  }
  console.log(`────────────────────────────────────────`);
  startShardReporter(client);
}
