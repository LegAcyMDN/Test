export const name = 'shardError';
export const once = false;

/**
 * @param {Error} error
 * @param {number} id
 */
export async function execute(client, error, id) {
  console.error(`[shardError] Shard #${id} erreur:`, error?.message || error);
}
