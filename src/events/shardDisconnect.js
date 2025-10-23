export const name = 'shardDisconnect';
export const once = false;

/**
 * @param {import('discord.js').CloseEvent} event
 * @param {number} id
 */
export async function execute(client, event, id) {
  console.warn(`[shardDisconnect] Shard #${id} déconnecté | code=${event?.code} reason=${event?.reason || 'n/a'}`);
}
