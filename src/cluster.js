import 'dotenv/config';
import { ShardingManager } from 'discord.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const token = process.env.DISCORD_TOKEN;
if (!token) {
  console.error('[cluster] DISCORD_TOKEN manquant dans .env');
  process.exit(1);
}

const manager = new ShardingManager(path.join(__dirname, 'index.js'), {
  token,
  totalShards: (process.env.TOTAL_SHARDS || "auto").trim(),
  respawn: true
});

manager.on('shardCreate', shard => {
  console.log(`[cluster] Shard #${shard.id} lancé`);
});

try {
  await manager.spawn({ timeout: -1 });
} catch (e) {
  console.error('[cluster] Erreur de spawn:', e);
  process.exit(1);
}
