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
- **Vector columns**: `embedding vector(384)` — NOT 1536 (this line used to say 1536 and contradicted the reality-check below; see "Vector columns are `vector(384)`"). pgvector is enabled, but it was **not** installed until `0000_travel_base_schema` ran `CREATE EXTENSION IF NOT EXISTS vector` — do not assume it on a fresh project. Add an ivfflat or hnsw index only when row count justifies it (>10k); note it as a follow-up otherwise.
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

---

## ⚠️ Reality check — verified against the repo 2026-08-09

Four things above are contradicted by what is actually on disk. The laws
themselves are sound; these are the details that will send you wrong.

### Filenames are SEQUENTIAL, not timestamped

Law 4 says `migrations/YYYYMMDDHHMM_short_name.sql`. **Every real file uses a
zero-padded sequence**: `0001_contact_submissions.sql` …
`0020_fixture_emails_valid_tld.sql`. Follow the repo, not the law — a
timestamped file dropped into that directory sorts unpredictably against the
existing twenty. **Next file is `0021_`.**

### The path is `supabase/migrations/`, not `migrations/`

Both the file location and `LOG.md` live under `supabase/`.

### Vector columns are `vector(384)`, not `vector(1536)`

Migration `0004` resized **every** embedding column — `travel_wiki`,
`travel_leads`, `travel_transcripts` — from 1536 to 384, because the embedder is
local fastembed `BAAI/bge-small-en-v1.5` (ONNX, no API key, 384 dims). A new
`vector(1536)` column will not work with `match_*` RPCs, which are typed to 384.

**Single-embedder rule:** one model, one dimension, repo-wide. Mixing dimensions
silently breaks similarity search rather than erroring.

### APPLIED STATE — RESOLVED 2026-08-09 (this section used to say the opposite)

> This block previously read *"APPLIED STATE IS NOT TRACKED — and 11 of 19 are
> unapplied"*. **That is no longer true, and leaving it would be exactly the
> staleness this skill exists to prevent.** It is rewritten rather than deleted
> because how it got fixed is the useful part.

**What was true until 2026-08-09:** not one `travel_*` table existed. The live
project reported **5** applied migrations, all the old techscape workflow
schema. Meanwhile the FastAPI app referenced **37 tables across 193 endpoints**.
Every DB-backed endpoint would have failed on a missing relation, and nothing in
the code could reveal it — the routers are wired correctly and only 500 once a
query actually runs.

**What is true now:** `database/travel_schema.sql` (12 base tables, applied as
`0000_travel_base_schema`) plus `0002`–`0020` are all applied, **through
Supabase `apply_migration`, so `supabase_migrations.schema_migrations` now
tracks them.** "Is production at 0020?" is finally answerable:

```
mcp__Supabase__list_migrations(project_id)     # authoritative applied list
```

**The ordering trap, if this is ever rebuilt:** the numbered migrations
FK-reference `travel_leads` and `travel_packages`, which only
`database/travel_schema.sql` creates. Starting at `0002` fails on a missing
relation. The base schema also carries `CREATE EXTENSION vector` — pgvector was
**not** installed, so starting anywhere else breaks every vector column too.

**Before trusting any DB-backed feature, verify the live schema rather than the
migration files:**

```sql
select table_name from information_schema.tables
where table_schema = 'public' order by table_name;
```

Diff that against `CREATE TABLE` statements in `supabase/migrations/`. A
migration file existing is not evidence that the table exists — this repo is
currently the clearest possible proof of that.

---

## ⚠️ Second reality check — learned by actually applying all 20, 2026-08-09

The first reality-check section was written by *reading*. This one was written by
*running*, and it caught things reading could not.

### A migration file is not evidence that it works

`0018_tenant_b_fixture.sql` had been in the repo, reviewed, and referenced by
other documents for days. Its first statement failed:

```
ERROR: 42703: column "slug" of relation "ts_businesses" does not exist
```

`ts_businesses` has no `slug`. The same INSERT also omitted `contact_email` and
`api_key_hash` — **both NOT NULL with no default**. Three defects in one
statement, in a file nobody doubted, because it had never been executed.

**Before applying any migration that writes to a pre-existing table, read the
real column list.** Not the schema doc, not another migration — the database:

```sql
select column_name, is_nullable, column_default
from information_schema.columns
where table_schema='public' and table_name='<table>'
order by ordinal_position;
```

Pay attention to `is_nullable='NO' AND column_default IS NULL` — every one of
those is a column your INSERT must supply or it fails.

### Seed data must satisfy the application's OWN validators

`0018` seeded four fixture logins at `@regression-fixture-tenant-b.test`.
`LoginIn.email` is a Pydantic `EmailStr`, and email-validator rejects RFC 2606
special-use names outright:

```
422 -> "value is not a valid email address: The part after the @-sign is a
        special-use or reserved name that cannot be used with email"
```

The fixture whose entire purpose is making the access matrix and cross-tenant
isolation runnable **could not clear step one of any of them.** A row that the
database accepts can still be unusable by the application. Fixed in `0020`.

Verified rather than assumed, and the result is not the intuitive one:

| domain | verdict |
|---|---|
| `.test`, `.invalid`, `.localhost` | **rejected** |
| `.example` | accepted |
| `.example.com` | accepted |

`.example` passes only because it is missing from email-validator's special-use
list, alongside its three RFC 2606 siblings that are on it. **Use
`example.com`** — IANA-reserved for documentation so it can never be a
deliverable mailbox (the safety property `.test` was chosen for), while being an
ordinary registered domain no validator special-cases. Robust for the right
reason rather than by luck.

**Generalised rule: a fixture is not done when the INSERT succeeds. It is done
when the application can USE the row** — log in as it, scope a query by it,
render it. Round-trip a fixture through the API before trusting it.

### `CREATE TRIGGER` has no `IF NOT EXISTS`

Law 6 asks for idempotency, but Postgres offers no `CREATE TRIGGER IF NOT
EXISTS`. `database/travel_schema.sql` had 11 bare `CREATE TRIGGER`s, so any
retry after a partial failure would fail on the first one. Two working patterns,
both already used in this repo — pick either, but use one:

```sql
DROP TRIGGER IF EXISTS trg_x ON public.t;          -- 0006/0010/0013/0016
CREATE TRIGGER trg_x ...;

DO $$ BEGIN                                        -- 0003/0012/0019
  CREATE TRIGGER trg_x ...;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
```

### Prefer `apply_migration` over `execute_sql`

Both run SQL. Only `apply_migration` records the migration in
`supabase_migrations.schema_migrations`, which is the thing whose absence made
the 19-migration gap invisible for weeks. Use `execute_sql` for probes and
verification; use `apply_migration` for anything that changes the schema.

### Verification that actually proves something (law 7, concretely)

Not "the query succeeded". These four, run after every schema batch:

```sql
-- 1. RLS on EVERY table, no exceptions
select count(*) filter (where not relrowsecurity) as rls_missing
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relkind='r';            -- expect 0

-- 2. No anon/authenticated grants leaked in
select table_name, grantee from information_schema.role_table_grants
where table_schema='public' and grantee in ('anon','authenticated');

-- 3. RLS PROVEN, not assumed — a temp function returns the verdict as data
--    (a DO block's RAISE NOTICE is invisible through the MCP)
create or replace function pg_temp.probe(tbl text) returns text
language plpgsql as $$
begin execute format('select 1 from public.%I limit 1', tbl);
      return 'LEAK — anon could read';
exception when insufficient_privilege then return 'BLOCKED';
          when others then return 'BLOCKED (' || sqlerrm || ')'; end $$;
set local role anon;
select t, pg_temp.probe(t) from unnest(array['travel_leads','payment_links']) t;

-- 4. Every table the CODE queries exists — the check that matters most
--    Build the list with:
--    grep -rhoE '\.table\("[a-z_]+"' api/app | sed -E 's/.*"([a-z_]+)"/\1/' | sort -u
```

Step 4 is the one that would have caught the whole gap on day one.
