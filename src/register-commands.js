import 'dotenv/config';
import { REST, Routes } from 'discord.js';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { validateEnv } from './utils/validateEnv.js';

validateEnv(['DISCORD_TOKEN', 'DISCORD_CLIENT_ID']);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const commands = [];
const foldersPath = path.join(__dirname, 'commands');
for (const folder of fs.readdirSync(foldersPath)) {
  const commandsPath = path.join(foldersPath, folder);
  for (const file of fs.readdirSync(commandsPath)) {
    if (!file.endsWith('.js')) continue;
    const modURL = pathToFileURL(path.join(commandsPath, file)).href;
    const { data } = await import(modURL);
    commands.push(data.toJSON());
  }
}

const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
const appId = process.env.DISCORD_CLIENT_ID;

const guildIds = (process.env.DISCORD_PUBLIC_GUILD_IDS ?? '')
  .split(',').map(s => s.trim()).filter(Boolean);

if (guildIds.length === 0) {
  // Enregistrer global si aucune guild spécifiée
  await rest.put(Routes.applicationCommands(appId), { body: commands });
  console.log('✔ Slash commands enregistrées en **global** (propagation lente)');
} else {
  for (const gid of guildIds) {
    await rest.put(Routes.applicationGuildCommands(appId, gid), { body: commands });
    console.log(`✔ Slash commands enregistrées sur ${gid}`);
    await new Promise(r => setTimeout(r, 300));
  }
}
