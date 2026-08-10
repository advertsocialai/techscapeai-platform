-- Local verification seam bootstrap (TEST ONLY — never run against Supabase).
-- Creates the roles the migrations GRANT/REVOKE against, the seam database,
-- and a minimal stub of Supabase's managed `auth` schema that
-- database/schema.sql references (auth.users FK + auth.uid() in RLS policies).
-- On real Supabase these are managed objects; locally they only need to exist.

DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN CREATE ROLE service_role NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gogaga') THEN CREATE ROLE gogaga LOGIN PASSWORD 'gogaga_local' SUPERUSER; END IF;
END $$;

SELECT 'CREATE DATABASE gogaga_local OWNER gogaga'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'gogaga_local') \gexec

\connect gogaga_local

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE SCHEMA IF NOT EXISTS auth;
CREATE TABLE IF NOT EXISTS auth.users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text,
  raw_user_meta_data jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now()
);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
