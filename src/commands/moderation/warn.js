import { SlashCommandBuilder, PermissionFlagsBits } from 'discord.js';
import { supabase } from '../../supabase.js';
import { ensureServerRow } from '../../utils/ensureServerRow.js';
import { incrementStat } from '../../utils/stats.js';
import { mustHaveModPerms } from '../../utils/perms.js';

export const data = new SlashCommandBuilder()
  .setName('warn')
  .setDescription('Avertir un membre (log en base).')
  .addUserOption(o => o.setName('membre').setDescription('Membre').setRequired(true))
  .addStringOption(o => o.setName('raison').setDescription('Raison').setRequired(true))
  .setDefaultMemberPermissions(PermissionFlagsBits.ModerateMembers);

export async function execute(interaction) {
  const target = interaction.options.getUser('membre', true);
  const reason = interaction.options.getString('raison', true);

  if (!mustHaveModPerms(interaction.member)) {
    return interaction.reply({ content: 'Permissions insuffisantes.', ephemeral: true });
  }

  const guild = interaction.guild;
  const serverRow = await ensureServerRow(guild);

  const { error } = await supabase.from('moderation_logs').insert({
    server_id: serverRow.id,
    user_discord_id: target.id,
    username: target.username,
    action_type: 'WARN',
    reason,
    is_automatic: false,
    message_content: null
  });
  if (error) {
    console.error(error);
    return interaction.reply({ content: 'Erreur lors de l’écriture du log.', ephemeral: true });
  }

  await incrementStat(serverRow.id, 'warnings_issued');

  await interaction.reply({ content: `⚠️ ${target} a été averti : ${reason}` });
  try { await target.send(`Tu as reçu un avertissement sur **${guild.name}** : ${reason}`); } catch {}
}
