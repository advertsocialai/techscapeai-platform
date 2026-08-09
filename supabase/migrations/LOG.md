# GoGaga Migration Log

Append one line per applied migration. Never delete lines.

| Date | File | What | Rollback-able | Applied by |
|---|---|---|---|---|
| (pre-existing) | — | ts_users/ts_businesses tables + RLS | — | initial setup |
| (pre-existing) | — | travel_wiki table + pgvector | — | initial setup |
| 2026-08-03 | 0002_branches_and_user_branch_scoping.sql | branches table (RLS+revoke), ts_users.branch_id FK, ts_users role CHECK widened (+super_admin,+agent), ts_users status CHECK widened (+inactive) | YES (see file's ROLLBACK section — branches DROP is destructive, column/constraint changes are not) | Phase 1 autonomous loop (T2) |
| 2026-08-03 | 0003_calls_transcripts_and_leads_assignment.sql | travel_calls + travel_transcripts tables (RLS+revoke), travel_leads gains phone/assigned_agent/language/embedding | YES (see file's ROLLBACK section — table DROPs are destructive, travel_leads column adds are not) | Phase 2 autonomous loop (T1) |
| 2026-08-03 | 0004_wiki_embeddings_384dim.sql | Resize travel_wiki/travel_leads/travel_transcripts.embedding vector(1536)→vector(384) (bge-small/fastembed, no cloud key), match_travel_wiki() cosine RPC | YES (see file's ROLLBACK — resize back to 1536; lossless, zero rows had data at time of change) | Phase 2 autonomous loop (T8) |
| 2026-08-05 (retro-logged 2026-08-07) | 0005_phase3_takeover_events_summary.sql | travel_calls gains mpc_uuid/takeover_state/summary; travel_call_events table (RLS+revoke) for takeover state-machine + notable-event log | YES (see file's ROLLBACK — table DROP destructive, column adds are not) | Phase 3 loop (T1) — retro-logged this sprint, file predates this entry |
| 2026-08-05 (retro-logged 2026-08-07) | 0006_ai_config.sql | travel_ai_config table (RLS+revoke): per-business/branch question_flow, languages, escalation_rules, working_hours, voice_persona; updated_at trigger | YES (see file's ROLLBACK — DROP TABLE/TRIGGER/FUNCTION, no data loss on fresh table) | Phase 3 loop (T2) — retro-logged this sprint, file predates this entry |
| 2026-08-05 (retro-logged 2026-08-07) | 0007_business_phone_numbers.sql | business_phone_numbers table (RLS+revoke): DID→business_id routing, replaces single-tenant PLIVO_BUSINESS_ID | YES (see file's ROLLBACK — DROP TABLE, no data loss on fresh table) | Phase 3 loop (T7) — retro-logged this sprint, file predates this entry |
| 2026-08-05 (retro-logged 2026-08-07) | 0008_match_transcripts_rpc.sql | match_travel_transcripts() cosine-similarity RPC over travel_transcripts.embedding, mirrors match_travel_wiki() | YES (see file's ROLLBACK — DROP FUNCTION, no table/data touched) | Phase 3 loop (T6) — retro-logged this sprint, file predates this entry |
| 2026-08-08 | 0009_packages_extension.sql | travel_packages (PRE-EXISTING table) gains category VARCHAR+CHECK / currency CHAR(3) NOT NULL DEFAULT 'INR' / branch_id FK→branches / nights (+backfill from duration_days), 3 indexes, RLS enable + service_role_only policy guard + REVOKE restated. base_price_inr & duration_days untouched (catalog_service + ai_engine.get_packages depend on them) | YES (see file's ROLLBACK — column/constraint/index drops only, no data loss to pre-existing columns) | Phase 4 loop (T1) |
| 2026-08-08 | 0011_whatsapp_outbox.sql | whatsapp_outbox table (RLS enable + service_role_only policy guard + REVOKE from anon/authenticated): business_id FK→ts_businesses CASCADE, to_number, message_type VARCHAR+CHECK(template/freeform), template_name, language, payload JSONB (exact Meta Cloud API request body), status VARCHAR+CHECK(queued/sent/failed/stubbed), provider, provider_message_id, error, created_at, sent_at; 2 CHECK constraints tying template_name to message_type; 3 indexes. NOT APPLIED — no live DB in this sandbox | YES (see file's ROLLBACK — DROP TABLE/POLICY/INDEX; destructive, drops the send audit trail, export command included in the file) | Phase 4 loop (T3) |
| 2026-08-08 | 0010_payment_links.sql | payment_links table (RLS + service_role_only policy + REVOKE): business/lead/package FKs, NUMERIC(12,2) amount + CHAR(3) currency, gateway CHECK (razorpay/stripe/stub), status CHECK (created/sent/viewed/paid/expired), partial-UNIQUE gateway_link_id for webhook resolution, created_by FK ts_users, updated_at trigger | YES (see file's ROLLBACK — DROP TABLE is destructive, no data loss on fresh table) | Phase 4 loop (T2) — **WRITTEN, NOT APPLIED** (no live DB in sandbox) |
| 2026-08-08 | 0015_currency_and_fx.sql | branches gains currency CHAR(3) NOT NULL DEFAULT 'INR' (spec wrongly assumed it existed — 0002 has no such column); fx_rate_snapshots append-only table (RLS + REVOKE) with UNIQUE (base,quote,captured_at); public.fx_rate_at(base,quote,at) STABLE point-in-time resolver — historical rollups MUST use the stored snapshot rate, never a live rate, so re-runs are deterministic | YES (see file's ROLLBACK — fx_rate_snapshots DROP loses rate history and with it deterministic re-runs; branches.currency drop is non-destructive) | Phase 4 loop (T8) — **WRITTEN, NOT APPLIED** (no live DB in sandbox) |
| 2026-08-08 | 0013_follow_ups.sql | follow_up_rules + follow_ups tables (RLS enable + service_role_only policy guard + REVOKE from anon/authenticated, both tables). follow_up_rules = ladder config: business-wide (branch_id NULL) or branch-scoped override, ladder_day INTEGER CHECK IN (1,3,7), type/channel VARCHAR+CHECK, due_offset_hours (NULL ⇒ ladder_day*24), is_active; two PARTIAL unique indexes (plain UNIQUE would let NULL branch_id duplicate). follow_ups = scheduled rows: business/lead/branch/rule FKs, ladder_day, type, due_at, status VARCHAR+CHECK(due/overdue/in_progress/done), assigned_to FK ts_users, channel, completed_at, metadata; UNIQUE (lead_id, ladder_day) makes auto-scheduling idempotent; updated_at triggers on both. `overdue` is DERIVED at read time — no cron required. NOT APPLIED — no live DB in this sandbox | YES (see file's ROLLBACK — DROP TABLE is destructive; drop follow_ups before follow_up_rules due to the FK. set_updated_at() deliberately not dropped) | Phase 4 loop (T6) — **WRITTEN, NOT APPLIED** (no live DB in sandbox) |
| 2026-08-08 | 0014_activity_log.sql | activity_log table (RLS enable + service_role_only policy guard + REVOKE from anon/authenticated): business_id FK CASCADE, actor_id FK ts_users SET NULL (audit row survives the user), action VARCHAR(100) intentionally un-CHECKed (a rejected audit INSERT is worse than an unknown verb), entity_type VARCHAR(50)+CHECK over 13 values, entity_id UUID deliberately NOT an FK (polymorphic, and an FK would make audit rows cascade-deletable), branch_id FK, metadata JSONB, at timestamptz; 5 indexes. NO updated_at column and NO trigger — append-only by construction; the only write path in the codebase is activity_log.record() (INSERT), the only router surface is GET. NOT APPLIED — no live DB in this sandbox | YES (see file's ROLLBACK — DROP TABLE is destructive, it drops the audit trail itself) | Phase 4 loop (T7) — **WRITTEN, NOT APPLIED** (no live DB in sandbox) |
| 2026-08-08 | 0016_usage_metrics.sql | usage_metrics table (RLS enable + service_role_only policy guard + REVOKE from anon/authenticated): business_id FK CASCADE, call_id FK travel_calls SET NULL (deleting a call must not erase the cost it incurred), branch_id FK (travel_calls has none, so ?branch= needs it here), stt_engine/tts_engine/telephony_provider/llm_model VARCHAR+CHECK, stt_seconds + telephony_seconds NUMERIC(12,3), llm_input/output_tokens, tts_characters, cost_usd NUMERIC(10,6), cost_breakdown JSONB, rate_card_version. **is_estimated BOOLEAN NOT NULL with NO DEFAULT — load-bearing: every writer must state explicitly whether the number was measured**, plus a CHECK that an estimated row must name the rate card that produced it. Every row today is is_estimated=TRUE (Phase 2B never ran ⇒ no provider usage data exists anywhere); updated_at trigger; 4 indexes. NOT APPLIED — no live DB in this sandbox | YES (see file's ROLLBACK — DROP TABLE is destructive, drops all recorded usage/cost rows) | Phase 4 loop (T9) — **WRITTEN, NOT APPLIED** (no live DB in sandbox) |
| 2026-08-08 | 0012_report_schedules.sql | report_schedules table (RLS enable + service_role_only policy guard + REVOKE from anon/authenticated): business_id FK→ts_businesses CASCADE, report_type VARCHAR(20)+CHECK(daily/weekly/monthly), branch_id FK→branches SET NULL (NULL = whole business), delivery_channel VARCHAR(20)+CHECK(whatsapp/email), recipients JSONB NOT NULL DEFAULT '[]' (shape is channel-dependent so it is validated in Pydantic, not by a CHECK), send_time TIME (local wall clock — TIME not TIMETZ so a fixed offset can't break across DST), timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata', is_active, last_run_at timestamptz (the scheduler's per-period de-dup key — persisted, not in-process, so restarts never double-send), created_at/updated_at + shared set_updated_at() trigger via DO-block duplicate_object guard; 4 indexes incl. an is_active-leading due-scan index. NOT APPLIED — no live DB in this sandbox | YES (see file's ROLLBACK — DROP TRIGGER/INDEX/TABLE; destructive only for rows created after this migration, no pre-existing table or column is touched) | Phase 4 loop (T4/T5) — **WRITTEN, NOT APPLIED** (no live DB in sandbox) |
<!-- Phase 2.5 agent appends: payment_links, follow_ups -->
<!-- Phase 2.5: payment_links, follow_ups (ai_config landed early as 0006, see above) -->
<!-- Phase 4: report_schedules -->

## 2026-08-09 — FIRST ACTUAL APPLICATION to the live database

Every row above this line described what a migration *does*. None of them had
ever been run against a real database — the rows saying "NOT APPLIED — no live
DB in this sandbox" were literally true, and the ones that said nothing were
silently in the same state. Verified before starting: the live project
(`xhrrkwojitchaaghohvr`, "Techscape AI") reported **5** applied migrations, all
of them the old techscape workflow schema, and **not one `travel_*` table
existed**. The FastAPI app's 37 table references and 193 endpoints were sitting
on top of a schema that was not there.

Applied in order, each via Supabase `apply_migration` so the applied state is
now **tracked** in `supabase_migrations.schema_migrations` — which is what
makes "is production at 0019?" answerable for the first time.

| Date | File | What | Rollback-able | Applied by |
|---|---|---|---|---|
| 2026-08-09 | database/travel_schema.sql (as `0000_travel_base_schema`) | 12 base travel tables + pg_trgm/vector extensions + RLS + REVOKE. `CREATE TRIGGER` has no `IF NOT EXISTS` in Postgres, so each was preceded by `DROP TRIGGER IF EXISTS` (the pattern 0006/0010/0013/0016 already use) to make a retry safe | YES | Claude Code |
| 2026-08-09 | 0002_branches_and_user_branch_scoping.sql | branches + ts_users.branch_id + CHECK widening | YES | Claude Code |
| 2026-08-09 | 0003_calls_transcripts_and_leads_assignment.sql | travel_calls, travel_transcripts, travel_leads columns | YES | Claude Code |
| 2026-08-09 | 0004_wiki_embeddings_384dim.sql | embeddings 1536→384 + match_travel_wiki | YES | Claude Code |
| 2026-08-09 | 0005_phase3_takeover_events_summary.sql | travel_call_events + takeover columns | YES | Claude Code |
| 2026-08-09 | 0006_ai_config.sql | travel_ai_config | YES | Claude Code |
| 2026-08-09 | 0007_business_phone_numbers.sql | business_phone_numbers | YES | Claude Code |
| 2026-08-09 | 0008_match_transcripts_rpc.sql | match_travel_transcripts | YES | Claude Code |
| 2026-08-09 | 0009_packages_extension.sql | travel_packages: category/currency/branch_id/nights | YES | Claude Code |
| 2026-08-09 | 0010_payment_links.sql | payment_links | YES | Claude Code |
| 2026-08-09 | 0011_whatsapp_outbox.sql | whatsapp_outbox | YES | Claude Code |
| 2026-08-09 | 0012_report_schedules.sql | report_schedules | YES | Claude Code |
| 2026-08-09 | 0013_follow_ups.sql | follow_up_rules + follow_ups | YES | Claude Code |
| 2026-08-09 | 0014_activity_log.sql | activity_log | YES | Claude Code |
| 2026-08-09 | 0015_currency_and_fx.sql | branches.currency + fx_rate_snapshots + fx_rate_at() | YES | Claude Code |
| 2026-08-09 | 0016_usage_metrics.sql | usage_metrics | YES | Claude Code |
| 2026-08-09 | 0017_rpc_tenant_isolation.sql | RPC EXECUTE revoked from PUBLIC/anon/authenticated | YES | Claude Code |
| 2026-08-09 | 0018_tenant_b_fixture.sql | Synthetic tenant B: business + branch + 4 users (manager/manager/agent/viewer) + phone +919999900002 + a deliberately different ai_config. **Applied on explicit instruction after being held back once.** The file as committed FAILED — it wrote a `slug` column that ts_businesses does not have, and omitted contact_email/api_key_hash (both NOT NULL, no default). Corrected at apply time and the file was fixed to match; api_key_hash is a non-hash sentinel so the fixture tenant has no usable API key | YES (see file's ROLLBACK — deletes only these rows) | Claude Code |
| 2026-08-09 | 0019_tenant_billing.sql | tenant_billing_accounts + usage_invoices + freeze trigger | YES | Claude Code |

### Pre-flight checks that gated this (none were assumed)

* Scanned all 18 files for destructive operations: **no `DROP TABLE`, no
  `ALTER TYPE`, no `DELETE`, no `TRUNCATE`**. The only `DROP`s are
  `DROP TRIGGER IF EXISTS` guards on triggers the same migration creates.
* `0002` is the only migration touching a live table. Its two CHECK rewrites are
  strict supersets, but that was **verified against the live rows** rather than
  reasoned about: all 12 `ts_users` were `role='admin'`, `status='active'`, both
  inside the new lists.
* `pgvector` was **not installed** (`installed_version: null`); the base schema's
  `CREATE EXTENSION IF NOT EXISTS vector` supplied it.
* `public.set_updated_at()` confirmed to exist before applying anything that
  attaches a trigger to it.

### Verification after applying (law 7)

* **44 tables, 44 with RLS enabled, 0 without.**
* **All 37 tables the API code queries now exist** — diffed
  `grep -rhoE '\.table\("[a-z_]+"' api/app` against `information_schema.tables`;
  the missing-set is empty. All 5 functions present (`match_travel_wiki`,
  `match_travel_transcripts`, `fx_rate_at`, `set_updated_at`,
  `freeze_issued_invoice`).
* **RLS proven, not assumed** — probed as `SET ROLE anon` against
  travel_leads, travel_calls, travel_transcripts, payment_links, usage_invoices,
  activity_log, branches, travel_ai_config: every one returned
  `BLOCKED (permission denied)`.
* **Live data intact**: ts_users still 12 rows, ts_businesses 13, ts_audit_logs 38.

### Pre-existing finding, NOT introduced here and NOT changed

`contact_submissions`, `gogaga_leads` and `gogaga_sessions` grant full
`SELECT/INSERT/UPDATE/DELETE` to `anon` and `authenticated` (42 grants). Every
one of the 29 tables created today has **zero** such grants. These three predate
this work and were left alone deliberately: the public marketing site plausibly
posts contact forms and captures leads through them, so revoking would be a
functional change disguised as a security fix. RLS is enabled on all three, so
row access is still policy-gated. Flagging for a decision rather than acting.
