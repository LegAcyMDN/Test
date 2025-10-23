import { supabase } from '../supabase.js';

export async function ensureServerRow(guild) {
  const { data: existing, error } = await supabase
    .from('discord_servers')
    .select('*')
    .eq('discord_server_id', guild.id)
    .maybeSingle();

  if (error) throw error;

  let serverRow = existing;
  if (!serverRow) {
    const insert = {
      discord_server_id: guild.id,
      server_name: guild.name,
      server_icon: guild.iconURL?.() ?? null,
      is_active: true
    };
    const { data, error: insErr } = await supabase
      .from('discord_servers')
      .insert(insert)
      .select('*')
      .single();
    if (insErr) throw insErr;
    serverRow = data;
  }

  const { data: settings, error: setErr } = await supabase
    .from('moderation_settings')
    .select('*')
    .eq('server_id', serverRow.id)
    .maybeSingle();
  if (setErr) throw setErr;

  if (!settings) {
    const def = {
      server_id: serverRow.id,
      auto_moderation_enabled: true,
      toxicity_threshold: 0.7,
      spam_detection: true,
      profanity_filter: true,
      link_filtering: false,
      warn_threshold: 3,
      auto_timeout_duration: 60,
      auto_ban_enabled: false
    };
    const { error: createSetErr } = await supabase
      .from('moderation_settings')
      .insert(def);
    if (createSetErr) throw createSetErr;
  }

  return serverRow;
}
