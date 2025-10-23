import 'dotenv/config';
import { createClient } from '@supabase/supabase-js';

function requireEnv(name) {
  const v = process.env[name];
  if (!v) throw new Error(`[env] Variable manquante: ${name}`);
  return v;
}

export const SUPABASE_URL = requireEnv('SUPABASE_URL');
export const SUPABASE_KEY = requireEnv('SUPABASE_KEY'); // ou SERVICE ROLE KEY côté serveur

export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
