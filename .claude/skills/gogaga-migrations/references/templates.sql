-- GoGaga migration templates — copy, rename placeholders, keep the structure.
-- File naming: migrations/YYYYMMDDHHMM_short_name.sql

-- ============================================================
-- TEMPLATE 1: New table with enum, FK, RLS, rollback
-- ============================================================

-- Migration: create <table_name>
-- Phase: <N> | Rollback-able: YES

-- 1) "Enums" in this repo = VARCHAR + CHECK (match travel_leads style)
--    status VARCHAR(20) DEFAULT 'value1' CHECK (status IN ('value1','value2','value3'))
--    To change values later: ALTER TABLE t DROP CONSTRAINT t_status_check; then re-ADD.

-- 2) Table
CREATE TABLE IF NOT EXISTS <table_name> (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  branch_id   uuid REFERENCES branches(id) ON DELETE RESTRICT,
  lead_id     uuid REFERENCES leads(id)    ON DELETE RESTRICT,
  status      VARCHAR(20) NOT NULL DEFAULT 'value1' CHECK (status IN ('value1','value2','value3')),
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- 3) RLS — SAME migration, always (THIS REPO: service-role-only pattern)
ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE <table_name> FROM anon, authenticated;
-- No auth.jwt() policies in this repo — FastAPI (_deps.py) is the gatekeeper.
-- If travel_schema.sql's DO $$ FOREACH revoke-block is the canonical list,
-- also append '<table_name>' there for consistency.

-- ROLLBACK:
-- DROP TABLE IF EXISTS <table_name>;



-- ============================================================
-- TEMPLATE 2: Vector column + deferred index note
-- ============================================================

-- pgvector is already enabled (wiki uses it). If ever needed:
-- CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE <table_name> ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Index: only when rows > ~10k. Until then leave a marker:
-- TODO(scale): CREATE INDEX CONCURRENTLY <table_name>_embedding_idx
--   ON <table_name> USING hnsw (embedding vector_cosine_ops);

-- ROLLBACK:
-- ALTER TABLE <table_name> DROP COLUMN IF EXISTS embedding;


-- ============================================================
-- TEMPLATE 3: updated_at trigger (only for user-editable tables)
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
  CREATE TRIGGER <table_name>_updated_at
    BEFORE UPDATE ON <table_name>
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ROLLBACK:
-- DROP TRIGGER IF EXISTS <table_name>_updated_at ON <table_name>;


-- ============================================================
-- TEMPLATE 4: Additive column change (the preferred kind)
-- ============================================================

ALTER TABLE <table_name> ADD COLUMN IF NOT EXISTS <col> <type>;
-- Backfill separately if needed, in batches for big tables:
-- UPDATE <table_name> SET <col> = <default_expr> WHERE <col> IS NULL;

-- ROLLBACK:
-- ALTER TABLE <table_name> DROP COLUMN IF EXISTS <col>;


-- ============================================================
-- VERIFICATION QUERIES (run after every apply)
-- ============================================================

-- Structure landed?
-- SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_name = '<table_name>' ORDER BY ordinal_position;

-- RLS on?
-- SELECT relname, relrowsecurity FROM pg_class WHERE relname = '<table_name>';

-- Policies present?
-- SELECT policyname, cmd, qual FROM pg_policies WHERE tablename = '<table_name>';

-- Then prove RLS blocks: with a non-super_admin token/role, attempt a
-- cross-branch SELECT — expect zero rows (see gogaga-verifier skill).
