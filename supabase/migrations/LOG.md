# GoGaga Migration Log

Append one line per applied migration. Never delete lines.

| Date | File | What | Rollback-able | Applied by |
|---|---|---|---|---|
| (pre-existing) | — | ts_users/ts_businesses tables + RLS | — | initial setup |
| (pre-existing) | — | travel_wiki table + pgvector | — | initial setup |
| 2026-08-03 | 0002_branches_and_user_branch_scoping.sql | branches table (RLS+revoke), ts_users.branch_id FK, ts_users role CHECK widened (+super_admin,+agent), ts_users status CHECK widened (+inactive) | YES (see file's ROLLBACK section — branches DROP is destructive, column/constraint changes are not) | Phase 1 autonomous loop (T2) |
<!-- Phase 2 agent appends: leads, calls, transcripts -->
<!-- Phase 2.5: payment_links, ai_config, follow_ups -->
<!-- Phase 4: report_schedules -->
