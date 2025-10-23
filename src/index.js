// src/index.js (extraits pertinents)
import 'dotenv/config';
import { Client, Collection, GatewayIntentBits, Events, REST, Routes } from 'discord.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateEnv } from './utils/validateEnv.js';
import { ensureServerRow } from './utils/ensureServerRow.js';
import { supabase } from './supabase.js';
import { loadCommands } from './utils/loadCommands.js';
import { logger } from './utils/logger.js';

validateEnv(['DISCORD_TOKEN', 'DISCORD_CLIENT_ID', 'SUPABASE_URL', 'SUPABASE_KEY']);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent
  ]
});

// ===== Chargement des commandes avec logs =====
client.commands = new Collection();
const commandsPath = path.join(__dirname, 'commands');
const { jsonList, flatList } = await loadCommands(client.commands, commandsPath);

// ===== Chargement des events (si tu as ajouté le dossier events/ précédemment) =====
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
{
  const eventsPath = path.join(__dirname, 'events');
  if (fs.existsSync(eventsPath)) {
    const files = fs.readdirSync(eventsPath).filter(f => f.endsWith('.js'));
    for (const file of files) {
      const fileURL = pathToFileURL(path.join(eventsPath, file)).href;
      const event = await import(fileURL);
      if (event.once) client.once(event.name, (...args) => event.execute(client, ...args));
      else client.on(event.name, (...args) => event.execute(client, ...args));
    }
    logger.info(`[events] ${files.length} event(s) chargé(s)`);
  } else {
    logger.warn(`[events] dossier non trouvé, saut du chargement des events`);
  }
}

// ===== REST helper =====
const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
const appId = process.env.DISCORD_CLIENT_ID;

async function registerCommandsForGuild(guildId) {
  try {
    const res = await rest.put(Routes.applicationGuildCommands(appId, guildId), { body: jsonList });
    // res = array of application commands
    logger.info(`[commands] Guild ${guildId}: upsert OK (${Array.isArray(res) ? res.length : '?'} cmd)`);
    if (process.env.LOG_LEVEL?.toLowerCase() === 'debug') {
      logger.debug(`[commands] Guild ${guildId}: ${flatList.map(n => `/${n}`).join(', ')}`);
    }
  } catch (e) {
    logger.error(`[commands] Guild ${guildId}: upsert FAIL`, e?.message || e);
  }
}

async function registerCommandsGlobal() {
  try {
    const res = await rest.put(Routes.applicationCommands(appId), { body: jsonList });
    logger.info(`[commands] Global: upsert demandé (${Array.isArray(res) ? res.length : '?' } cmd)`);
  } catch (e) {
    logger.error('[commands] Global: FAIL', e?.message || e);
  }
}

// ===== Lifecycle =====
client.once(Events.ClientReady, async () => {
  const shardId = client.shard?.ids?.[0] ?? 0;
  logger.info(`[ready] Connecté en tant que ${client.user.tag} | shard ${shardId}`);

  if ((process.env.REGISTER_SCOPE || 'guild').toLowerCase() === 'global') {
    await registerCommandsGlobal();
  }

  for (const g of client.guilds.cache.values()) {
    await registerCommandsForGuild(g.id);
    try { await ensureServerRow(g); } catch (e) { logger.error('ensureServerRow', e); }
    await new Promise(r => setTimeout(r, 400));
  }
});

client.on(Events.GuildCreate, async (guild) => {
  logger.info(`[guildCreate] Bot ajouté sur ${guild.name} (${guild.id})`);
  try { await ensureServerRow(guild); } catch (e) { logger.error('ensureServerRow', e); }
  await registerCommandsForGuild(guild.id);
});

// Interaction handler (inchangé)
client.on(Events.InteractionCreate, async (interaction) => {
  if (!interaction.isChatInputCommand()) return;
  const cmd = client.commands.get(interaction.commandName);
  if (!cmd) return;
  try {
    await cmd.execute(interaction);
  } catch (e) {
    logger.error(`[interaction] /${interaction.commandName}`, e);
    const reply = { content: 'Erreur pendant la commande.', ephemeral: true };
    if (interaction.deferred || interaction.replied) await interaction.followUp(reply);
    else await interaction.reply(reply);
  }
});

client.login(process.env.DISCORD_TOKEN);
