import { SlashCommandBuilder, PermissionFlagsBits } from 'discord.js';
import { supabase } from '../../supabase.js';
import { ensureServerRow } from '../../utils/ensureServerRow.js';
import { incrementStat } from '../../utils/stats.js';
import { mustHaveModPerms } from '../../utils/perms.js';

export const data = new SlashCommandBuilder()
  .setName('timeout')
  .setDescription('Timeout un membre (minutes).')
  .addUserOption(o => o.setName('membre').setDescription('Membre').setRequired(true))
  .addIntegerOption(o => o.setName('minutes').setDescription('Durée').setRequired(true))
  .addStringOption(o => o.setName('raison').setDescription('Raison').setRequired(true))
  .setDefaultMemberPermissions(PermissionFlagsBits.ModerateMembers);

export async function execute(interaction) {
  const target = interaction.options.getMember('membre', true);
  const minutes = interaction.options.getInteger('minutes', true);
  const reason = interaction.options.getString('raison', true);

  if (!mustHaveModPerms(interaction.member)) {
    return interaction.reply({ content: 'Permissions insuffisantes.', ephemeral: true });
  }
  if (!target?.moderatable) {
    return interaction.reply({ content: 'Je ne peux pas modérer ce membre.', ephemeral: true });
  }

  const guild = interaction.guild;
  const serverRow = await ensureServerRow(guild);

  await target.timeout(minutes * 60_000, reason);

  await supabase.from('moderation_logs').insert({
    server_id: serverRow.id,
    user_discord_id: target.id,
    username: target.user.username,
    action_type: 'TIMEOUT',
    reason,
    is_automatic: false
  });

  await incrementStat(serverRow.id, 'timeouts_applied');

  await interaction.reply({ content: `⏱️ ${target} timeout ${minutes} min. Raison : ${reason}` });
}
