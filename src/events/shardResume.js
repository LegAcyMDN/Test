export const name = 'shardResume';
export const once = false;

/**
 * @param {number} id
 * @param {number} replayed
 */
export async function execute(client, id, replayed) {
  console.log(`[shardResume] Shard #${id} résume | events rejoués=${replayed}`);
}
