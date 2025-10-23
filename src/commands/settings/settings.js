import { SlashCommandBuilder, PermissionFlagsBits } from 'discord.js';
import { supabase } from '../../supabase.js';
import { ensureServerRow } from '../../utils/ensureServerRow.js';

export const data = new SlashCommandBuilder()
  .setName('settings')
  .setDescription('Voir/Modifier les paramètres de modération.')
  .addSubcommand(sc => sc.setName('get').setDescription('Afficher les paramètres'))
  .addSubcommand(sc => sc
    .setName('set')
    .setDescription('Modifier un paramètre')
    .addStringOption(o => o.setName('key').setDescription('Nom du paramètre').setRequired(true))
    .addStringOption(o => o.setName('value').setDescription('Valeur').setRequired(true)))
  .setDefaultMemberPermissions(PermissionFlagsBits.Administrator);

export async function execute(interaction) {
  const guild = interaction.guild;
  const sub = interaction.options.getSubcommand();
  const serverRow = await ensureServerRow(guild);

  const { data: settings, error } = await supabase
    .from('moderation_settings')
    .select('*')
    .eq('server_id', serverRow.id)
    .single();
  if (error) return interaction.reply({ content: 'Erreur chargement paramètres.', ephemeral: true });

  if (sub === 'get') {
    const msg = [
      `**auto_moderation_enabled:** ${settings.auto_moderation_enabled}`,
      `**toxicity_threshold:** ${settings.toxicity_threshold}`,
      `**spam_detection:** ${settings.spam_detection}`,
      `**profanity_filter:** ${settings.profanity_filter}`,
      `**link_filtering:** ${settings.link_filtering}`,
      `**warn_threshold:** ${settings.warn_threshold}`,
      `**auto_timeout_duration:** ${settings.auto_timeout_duration} min`,
      `**auto_ban_enabled:** ${settings.auto_ban_enabled}`
    ].join('\n');
    return interaction.reply({ content: msg });
  }

  const key = interaction.options.getString('key', true);
  let value = interaction.options.getString('value', true);

  const boolKeys = ['auto_moderation_enabled','spam_detection','profanity_filter','link_filtering','auto_ban_enabled'];
  const intKeys = ['warn_threshold','auto_timeout_duration'];
  const numKeys = ['toxicity_threshold'];

  if (boolKeys.includes(key)) value = ['true','1','on','yes','oui'].includes(value.toLowerCase());
  else if (intKeys.includes(key)) value = parseInt(value, 10);
  else if (numKeys.includes(key)) value = parseFloat(value);

  const { error: updErr } = await supabase
    .from('moderation_settings')
    .update({ [key]: value })
    .eq('server_id', serverRow.id);

  if (updErr) return interaction.reply({ content: 'Erreur mise à jour.', ephemeral: true });
  return interaction.reply({ content: `Paramètre **${key}** mis à **${value}**` });
}
