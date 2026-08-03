---
name: gogaga-migrations
description: Database migration discipline for the GoGaga/TechScapeAI Supabase (Postgres + RLS + pgvector) backend. ALWAYS use this skill before creating, altering, or dropping ANY table, column, index, policy, or extension — including "quick" schema tweaks, adding a column, enabling RLS, creating enums, or vector columns. Also trigger on words like migration, migrate, CREATE TABLE, ALTER, schema change, RLS policy, or supabase db. Never run DDL without following this skill.
---

# GoGaga Migrations

Rules for every schema change to the Supabase database. The database is production-shared (auth + wiki are live) — a bad migration hurts real users.

## The 7 laws

1. **Print every SQL statement before running it.** Never silent DDL. The user must be able to see exactly what will execute.
2. **RLS ships in the same migration as the table.** A table without policies in the same change is an incomplete migration. Enable RLS explicitly: `ALTER TABLE x ENABLE ROW LEVEL SECURITY;`
3. **Additive by default.** Prefer ADD COLUMN over ALTER TYPE; prefer new table over restructuring. Destructive ops (DROP, ALTER TYPE, data-loss changes) require explicitly telling the user what's destroyed and getting confirmation first.
4. **One migration file per change, timestamped**: `migrations/YYYYMMDDHHMM_short_name.sql`. Never edit an applied migration — write a new one.
5. **Every migration has a rollback section** — commented at the bottom of the same file (`-- ROLLBACK: DROP TABLE ...`). If it can't be rolled back (data loss), say so in the file header.
6. **Idempotency where possible**: `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `DO $$ ... $$` guards for enums and policies (Postgres has no CREATE POLICY IF NOT EXISTS — use the DO-block pattern in references/templates.sql).
7. **Verify after applying**: select from the new table, attempt a cross-branch read with a non-privileged role to prove RLS actually blocks (per gogaga-verifier patterns). A migration isn't done at "query succeeded" — it's done when RLS is proven.

## Project-specific patterns (read references/templates.sql for copy-paste versions)

- **RLS pattern — THIS REPO IS SERVICE-ROLE-ONLY**: every travel table does `ENABLE ROW LEVEL SECURITY` then `REVOKE ALL ... FROM anon, authenticated` (see the DO $$ FOREACH block at the end of database/travel_schema.sql). The FastAPI service-role client is the only reader/writer; authorization lives in _deps.py, NOT in policies. Never add auth.jwt()-based policies — they'd be dead code and imply a security model this repo doesn't use. New tables: append the table name to that REVOKE block (or replicate it) in the same migration.
- **Enums**: this repo uses VARCHAR + CHECK constraints, NOT Postgres enum types (see travel_leads.qualification/status/source). Follow that: `role VARCHAR(20) CHECK (role IN (...))`. Altering allowed values = drop+re-add the CHECK constraint in a migration (safer than enum ALTER TYPE).
- **Vector columns**: `embedding vector(1536)` — pgvector already enabled (wiki proves it). Add an ivfflat or hnsw index only when row count justifies it (>10k); note it as a follow-up otherwise.
- **Timestamps**: `created_at timestamptz default now()`; add `updated_at` with trigger only if the table is user-editable (ai_config, leads).
- **Foreign keys**: always explicit `references` with `on delete` behavior stated deliberately (usually `restrict`; `cascade` only for pure child rows like transcripts→calls).

## Workflow for any schema change

1. Read `references/schema.md` in the gogaga-backend skill — is this table/column already specified? Follow the spec; deviations get flagged to the user.
2. Check live state first: does the table/column/policy already exist? (`\d tablename` equivalent / information_schema query). Never assume.
3. Write the migration file from `references/templates.sql` patterns.
4. Show the full SQL to the user in the report.
5. Apply. 6. Run the RLS verification probe. 7. Record in the migration log (append one line to `migrations/LOG.md`: file, date, what, rollback-able Y/N).

## Phase migration map (Option B — real repo)
P1: ts_users role CHECK migration (add super_admin/agent; keep legacy valid) + branch linkage (branch_id → travel_franchisees OR new travel_branches per recon) · P2: travel_calls, travel_transcripts (+ extend travel_leads: phone, assigned_agent, embedding, language) · P2.5/P4: travel_payment_links, travel_ai_config; ladder rides on travel_playbook_runs (check before creating tables). Column specs: gogaga-backend/references/schema.md. File conventions to copy: IF NOT EXISTS, idx_/trg_ naming, set_updated_at() trigger, the REVOKE block.
