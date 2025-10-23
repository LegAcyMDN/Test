export const name = 'shardReady';
export const once = false;

/**
 * @param {import('discord.js').Client} client
 * @param {number} id - shard id
 * @param {Set<string>} unavailableGuilds
 */
export async function execute(client, id, unavailableGuilds) {
  console.log(`[shardReady] Shard #${id} prêt | guilds indisponibles: ${unavailableGuilds?.size ?? 0}`);
}
