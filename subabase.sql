-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.admin_activity_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  admin_id uuid NOT NULL,
  action_type text NOT NULL,
  action_details jsonb,
  target_user_id uuid,
  target_server_id uuid,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT admin_activity_logs_pkey PRIMARY KEY (id),
  CONSTRAINT admin_activity_logs_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES public.users(id),
  CONSTRAINT admin_activity_logs_target_user_id_fkey FOREIGN KEY (target_user_id) REFERENCES public.users(id),
  CONSTRAINT admin_activity_logs_target_server_id_fkey FOREIGN KEY (target_server_id) REFERENCES public.discord_servers(id)
);
CREATE TABLE public.bot_statistics (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  server_id uuid NOT NULL,
  date date NOT NULL DEFAULT CURRENT_DATE,
  messages_analyzed integer NOT NULL DEFAULT 0,
  warnings_issued integer NOT NULL DEFAULT 0,
  timeouts_applied integer NOT NULL DEFAULT 0,
  bans_executed integer NOT NULL DEFAULT 0,
  toxicity_detections integer NOT NULL DEFAULT 0,
  spam_detections integer NOT NULL DEFAULT 0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_statistics_pkey PRIMARY KEY (id),
  CONSTRAINT bot_statistics_server_id_fkey FOREIGN KEY (server_id) REFERENCES public.discord_servers(id)
);
CREATE TABLE public.discord_servers (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  discord_server_id text NOT NULL UNIQUE,
  server_name text NOT NULL,
  server_icon text,
  owner_id uuid,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT discord_servers_pkey PRIMARY KEY (id),
  CONSTRAINT discord_servers_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id)
);
CREATE TABLE public.global_bot_settings (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  setting_key text NOT NULL UNIQUE,
  setting_value jsonb NOT NULL,
  updated_by uuid,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT global_bot_settings_pkey PRIMARY KEY (id),
  CONSTRAINT global_bot_settings_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id)
);
CREATE TABLE public.moderation_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  server_id uuid NOT NULL,
  user_discord_id text NOT NULL,
  username text NOT NULL,
  action_type text NOT NULL,
  reason text NOT NULL,
  ai_confidence numeric,
  is_automatic boolean NOT NULL DEFAULT false,
  moderator_id uuid,
  message_content text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT moderation_logs_pkey PRIMARY KEY (id),
  CONSTRAINT moderation_logs_server_id_fkey FOREIGN KEY (server_id) REFERENCES public.discord_servers(id),
  CONSTRAINT moderation_logs_moderator_id_fkey FOREIGN KEY (moderator_id) REFERENCES public.users(id)
);
CREATE TABLE public.moderation_settings (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  server_id uuid NOT NULL UNIQUE,
  auto_moderation_enabled boolean NOT NULL DEFAULT true,
  toxicity_threshold numeric NOT NULL DEFAULT 0.7,
  spam_detection boolean NOT NULL DEFAULT true,
  profanity_filter boolean NOT NULL DEFAULT true,
  link_filtering boolean NOT NULL DEFAULT false,
  warn_threshold integer NOT NULL DEFAULT 3,
  auto_timeout_duration integer NOT NULL DEFAULT 60,
  auto_ban_enabled boolean NOT NULL DEFAULT false,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT moderation_settings_pkey PRIMARY KEY (id),
  CONSTRAINT moderation_settings_server_id_fkey FOREIGN KEY (server_id) REFERENCES public.discord_servers(id)
);
CREATE TABLE public.server_members (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  server_id uuid NOT NULL,
  is_admin boolean NOT NULL DEFAULT false,
  joined_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT server_members_pkey PRIMARY KEY (id),
  CONSTRAINT server_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id),
  CONSTRAINT server_members_server_id_fkey FOREIGN KEY (server_id) REFERENCES public.discord_servers(id)
);
CREATE TABLE public.users (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  discord_id text NOT NULL UNIQUE,
  discord_username text NOT NULL,
  discord_avatar text,
  email text,
  role text NOT NULL DEFAULT 'user'::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  last_login timestamp with time zone NOT NULL DEFAULT now(),
  is_bot_admin boolean NOT NULL DEFAULT false,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT users_pkey PRIMARY KEY (id)
);