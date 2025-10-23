import { supabase } from '../supabase.js';

export async function incrementStat(serverId, field) {
  const today = new Date().toISOString().slice(0,10);

  const { data: row, error } = await supabase
    .from('bot_statistics')
    .select('*')
    .eq('server_id', serverId)
    .eq('date', today)
    .maybeSingle();
  if (error) throw error;

  if (!row) {
    const fresh = { server_id: serverId, date: today, [field]: 1 };
    const { error: insErr } = await supabase.from('bot_statistics').insert(fresh);
    if (insErr) throw insErr;
  } else {
    const { error: updErr } = await supabase
      .from('bot_statistics')
      .update({ [field]: (row[field] ?? 0) + 1 })
      .eq('id', row.id);
    if (updErr) throw updErr;
  }
}
