# GoGaga Migration Log

Append one line per applied migration. Never delete lines.

| Date | File | What | Rollback-able | Applied by |
|---|---|---|---|---|
| (pre-existing) | — | ts_users/ts_businesses tables + RLS | — | initial setup |
| (pre-existing) | — | travel_wiki table + pgvector | — | initial setup |
| 2026-08-03 | 0002_branches_and_user_branch_scoping.sql | branches table (RLS+revoke), ts_users.branch_id FK, ts_users role CHECK widened (+super_admin,+agent), ts_users status CHECK widened (+inactive) | YES (see file's ROLLBACK section — branches DROP is destructive, column/constraint changes are not) | Phase 1 autonomous loop (T2) |
| 2026-08-03 | 0003_calls_transcripts_and_leads_assignment.sql | travel_calls + travel_transcripts tables (RLS+revoke), travel_leads gains phone/assigned_agent/language/embedding | YES (see file's ROLLBACK section — table DROPs are destructive, travel_leads column adds are not) | Phase 2 autonomous loop (T1) |
<!-- Phase 2.5 agent appends: payment_links, ai_config, follow_ups -->
<!-- Phase 2.5: payment_links, ai_config, follow_ups -->
<!-- Phase 4: report_schedules -->
