import { SlashCommandBuilder, PermissionFlagsBits } from 'discord.js';
import { supabase } from '../../supabase.js';
import { ensureServerRow } from '../../utils/ensureServerRow.js';
import { incrementStat } from '../../utils/stats.js';
import { mustHaveModPerms } from '../../utils/perms.js';

export const data = new SlashCommandBuilder()
  .setName('ban')
  .setDescription('Bannir un membre.')
  .addUserOption(o => o.setName('membre').setDescription('Membre').setRequired(true))
  .addStringOption(o => o.setName('raison').setDescription('Raison').setRequired(true))
  .setDefaultMemberPermissions(PermissionFlagsBits.BanMembers);

export async function execute(interaction) {
  const target = interaction.options.getMember('membre', true);
  const reason = interaction.options.getString('raison', true);

  if (!mustHaveModPerms(interaction.member)) {
    return interaction.reply({ content: 'Permissions insuffisantes.', ephemeral: true });
  }
  if (!target?.bannable) {
    return interaction.reply({ content: 'Je ne peux pas bannir ce membre.', ephemeral: true });
  }

  const guild = interaction.guild;
  const serverRow = await ensureServerRow(guild);

  await target.ban({ reason });

  await supabase.from('moderation_logs').insert({
    server_id: serverRow.id,
    user_discord_id: target.id,
    username: target.user.username,
    action_type: 'BAN',
    reason,
    is_automatic: false
  });

  await incrementStat(serverRow.id, 'bans_executed');

  await interaction.reply({ content: `🔨 ${target} banni. Raison : ${reason}` });
}
