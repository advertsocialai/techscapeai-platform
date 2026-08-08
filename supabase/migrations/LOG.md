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
<!-- Phase 2.5 agent appends: payment_links, follow_ups -->
<!-- Phase 2.5: payment_links, follow_ups (ai_config landed early as 0006, see above) -->
<!-- Phase 4: report_schedules -->
