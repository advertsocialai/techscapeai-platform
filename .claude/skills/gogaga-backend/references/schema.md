# Real Database Schema (techscapeai-platform) + GoGaga Additions

Naming: platform tables `ts_*` (in techscape_schema.sql), travel tables `travel_*` (travel_schema.sql), site tables in schema.sql. RLS pattern everywhere: ENABLE RLS + REVOKE ALL FROM anon, authenticated → service-role-only via FastAPI. NO JWT-claim policies.

## Existing platform (do not restructure)
- ts_businesses — tenancy root: id, name, api_key_hash, status, subscription_tier, credentials...
- ts_users — id, business_id FK, email, password_hash, role, status, branch_id FK → branches (added P1), is_active-equivalent
  - **role CHECK (post-P1)**: `admin, manager, user, viewer, super_admin, agent` — additive, not a rename.
    `admin`/`user` are LEGACY-ONLY (pre-migration rows); do not use them for new
    users. New rows use `super_admin` (top rank, == legacy `admin`), `manager`
    (branch-admin rank, == spec's "admin" tier — `admin` itself was already
    claimed by the legacy top rank so the spec's second tier is stored as
    `manager`), `agent` (== legacy `user`), `viewer` (unchanged). Full rank
    table + rationale: `api/app/core/deps.py` docstring.
  - **status CHECK (post-P1)**: `active, disabled, inactive` — `inactive` is
    what `DELETE /users/{id}` (soft-delete) writes; `disabled` is legacy/other.
- ts_* others: workflows, templates, executions, integrations, billing, audit... (OUT OF SCOPE)

## branches (new, P1) — dedicated table, NOT travel_franchisees
`id, business_id FK → ts_businesses (CASCADE), name, city, status ('active'|'inactive'),
created_at`. RLS enabled + `REVOKE ALL FROM anon, authenticated` (service-role-only,
same as every other table here). `ts_users.branch_id` (nullable — NULL = unscoped,
i.e. sees the whole business) FKs to this table, `ON DELETE SET NULL`.
Migration: `supabase/migrations/0002_branches_and_user_branch_scoping.sql`.

Reused `travel_franchisees` was the originally suggested default (see below) but
P1 recon found a pre-existing unapplied migration draft that had already decided
on a dedicated table, matching what `matrix-spec.json` expected. `travel_franchisees`
is kept as its own, separate franchise-partner concept (owner_name, onboarding,
metadata) — do not conflate the two.

## Existing travel tables (12) — extend these
- **travel_wiki** — entries + `embedding vector(384)` ✅ (resized from 1536 in migration 0004). **All rows backfilled** with bge-small embeddings. Search: `WikiService.search()` tries cosine similarity via `match_travel_wiki()` RPC first, falls back to keyword ilike. Do NOT assume vector(1536) anywhere.
- travel_destinations, travel_packages, travel_suppliers — catalog
- travel_customer_profiles — customer memory
- travel_itineraries
- travel_franchisees — a separate franchise-partner concept (owner_name,
  onboarding, metadata). NOT the branch model — P1 built a dedicated
  `branches` table instead (see above). Do not link branch_id here.
- **travel_leads** — business_id FK CASCADE · customer_id · source(whatsapp/website/phone/franchisee/referral/sms/email/other) · raw_message · intent · destination_hint · pax_count · budget_inr · duration_days · score int · qualification(cold/warm/hot/converted/lost) · status(new/qualified/itinerary_sent/negotiating/booked/lost) · itinerary_id · franchisee_id · metadata jsonb · timestamps + updated_at trigger
  **P2 additions (migration 0003, DONE)**: `phone VARCHAR(20)` (idx), `assigned_agent UUID FK ts_users ON DELETE SET NULL` (idx), `language VARCHAR(10) DEFAULT 'en'`, `embedding vector(384)` (resized from 1536 in migration 0004). Agent-tier sees only rows where assigned_agent = self.
- travel_bookings, travel_booking_guarantees, travel_in_trip_incidents
- travel_playbook_runs — use_case_id, trigger_kind(manual/schedule/event/webhook), channels[], status, rendered/delivery jsonb + unique once-per-booking schedule index → FOLLOW-UP LADDER BUILDS ON THIS

## GoGaga additions — DONE (migrations applied)

### migration 0002 — branches + user branch scoping (P1 DONE)
role CHECK widened on ts_users (+super_admin,+agent, additive); `branches` table created; `ts_users.branch_id` FK added.

### migration 0003 — travel_calls + travel_transcripts + leads assignment (P2 DONE)
```
travel_calls (
  id UUID PK, business_id FK ts_businesses CASCADE,
  lead_id FK travel_leads SET NULL, provider_sid VARCHAR(255),
  status VARCHAR(20) CHECK('active','completed','failed') DEFAULT 'active',
  mode VARCHAR(20) CHECK('ai','agent','conference') DEFAULT 'ai',
  duration_sec INTEGER, recording_url TEXT, sentiment_score NUMERIC(4,3),
  stt_engine VARCHAR(20), language VARCHAR(10) DEFAULT 'en',
  started_at TIMESTAMPTZ, ended_at TIMESTAMPTZ,
  created_at/updated_at TIMESTAMPTZ, updated_at trigger
)
RLS ENABLED + REVOKE ALL FROM anon, authenticated

travel_transcripts (
  id UUID PK, call_id FK travel_calls CASCADE NOT NULL,
  speaker VARCHAR(20) CHECK('ai','customer','agent') NOT NULL,
  text_original TEXT NOT NULL, text_translated TEXT,
  timestamp_ms BIGINT NOT NULL, sentiment JSONB DEFAULT '{}',
  embedding vector(384),  ← resized to 384 in migration 0004
  created_at TIMESTAMPTZ  ← append-only, no updated_at trigger
)
RLS ENABLED + REVOKE ALL FROM anon, authenticated
```

### migration 0004 — wiki embeddings + vector resize to 384-dim (P2 DONE)
- `travel_wiki.embedding`, `travel_leads.embedding`, `travel_transcripts.embedding` all resized from vector(1536) → **vector(384)**
- Lossless: zero rows had populated embeddings before this migration
- `match_travel_wiki(p_business_id, p_query_embedding vector(384), p_match_count, p_category)` RPC created (cosine, business-scoped)
- Embedder: BAAI/bge-small-en-v1.5 via fastembed (ONNX, no API key, ~67MB, 384-dim). Lives in `services/travel/embeddings.py`.

## GoGaga additions — PLANNED (not yet migrated)
P2B: `travel_calls.mpc_uuid VARCHAR(255)` — needed when MPC migration (B2) lands; migration 0005
P2.5/P4: travel_payment_links · travel_ai_config · report scheduling (check if playbooks cover before adding a table)

## Migration rules (see gogaga-migrations skill)
- Follow existing file style: IF NOT EXISTS, CHECK constraints for enums (this repo uses VARCHAR+CHECK, not Postgres enums), idx_ naming, trg_ triggers with set_updated_at()
- Same-file RLS: ENABLE + REVOKE block appended (copy the DO $$ FOREACH pattern at travel_schema.sql end)
- pgvector: extension available; **embedding vector(384)** (NOT 1536 — resized in migration 0004); index only >10k rows
- Next migration number: **0005**
