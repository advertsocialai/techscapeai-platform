# Real Database Schema (techscapeai-platform) + GoGaga Additions

Naming: platform tables `ts_*` (in techscape_schema.sql), travel tables `travel_*` (travel_schema.sql), site tables in schema.sql. RLS pattern everywhere: ENABLE RLS + REVOKE ALL FROM anon, authenticated → service-role-only via FastAPI. NO JWT-claim policies.

## Existing platform (do not restructure)
- ts_businesses — tenancy root: id, name, api_key_hash, status, subscription_tier, credentials...
- ts_users — id, business_id FK, email, password_hash, role (currently admin/manager/user/viewer → P1 migrates to super_admin/admin/agent/viewer), is_active-equivalent
- ts_* others: workflows, templates, executions, integrations, billing, audit... (OUT OF SCOPE)

## Existing travel tables (12) — extend these
- travel_wiki — entries + embedding column (vector) present, EMBEDDINGS NOT POPULATED yet; search=ilike
- travel_destinations, travel_packages, travel_suppliers — catalog
- travel_customer_profiles — customer memory
- travel_itineraries
- travel_franchisees — the branch-equivalent (P1 decides branch linkage)
- travel_leads — business_id FK CASCADE · customer_id · source(whatsapp/website/phone/franchisee/referral/sms/email/other) · raw_message · intent · destination_hint · pax_count · budget_inr · duration_days · score int · qualification(cold/warm/hot/converted/lost) · status(new/qualified/itinerary_sent/negotiating/booked/lost) · itinerary_id · franchisee_id · metadata jsonb · timestamps + updated_at trigger
  → P2 extends: phone (unique caller lookup), assigned_agent FK ts_users, embedding vector(1536), language
- travel_bookings, travel_booking_guarantees, travel_in_trip_incidents
- travel_playbook_runs — use_case_id, trigger_kind(manual/schedule/event/webhook), channels[], status, rendered/delivery jsonb + unique once-per-booking schedule index → FOLLOW-UP LADDER BUILDS ON THIS

## GoGaga additions by phase (create with gogaga-migrations discipline)
P1: role enum migration on ts_users + branch linkage (branch_id → travel_franchisees OR travel_branches — recon decides)
P2: travel_calls (id, lead_id FK, provider_sid, status active/completed/failed, mode ai/agent/conference, duration_sec, recording_url, sentiment_score, stt_engine, language, started_at/ended_at)
    travel_transcripts (id, call_id FK CASCADE, speaker ai/customer/agent, text_original, text_translated, timestamp_ms, sentiment jsonb{excitement,intent,price_sensitivity,urgency}, embedding vector(1536))
P2.5/P4: travel_payment_links (lead_id, package, amounts base/transfers/gst/total, gateway, expiry, send_via, status, gateway_link_id)
    travel_ai_config (business_id/branch scope, question_flow/language_settings/escalation_rules/working_hours/follow_up_ladder jsonb)
    report scheduling — check if playbooks cover before adding a table

## Migration rules (see gogaga-migrations skill)
- Follow existing file style: IF NOT EXISTS, CHECK constraints for enums (this repo uses VARCHAR+CHECK, not Postgres enums), idx_ naming, trg_ triggers with set_updated_at()
- Same-file RLS: ENABLE + REVOKE block appended (copy the DO $$ FOREACH pattern at travel_schema.sql end)
- pgvector: extension available; embedding vector(1536); index only >10k rows
