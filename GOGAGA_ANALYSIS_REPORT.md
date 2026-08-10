# GoGaga Analysis Report — the combined area scoreboard (both apps)

**Update rule: any commit that moves an area's completeness — up or down — must
update this file in the same commit.** This is the single combined view; the
narrative evidence behind each number lives in `PLATFORM_STATUS.md`, the
compliance detail in `COMPLIANCE_CHECKLIST.md`, and every blocker ID in
`BLOCKERS.md`.

Last updated: **2026-08-09** at `21d4775` (push-to-100% run).

> **The caveat that qualifies every row:** no data has ever travelled from
> Postgres to a screen (BLK-2 no service-role key, BLK-3 sandbox blocks
> supabase.co). Percentages mean **built and verified by construction** unless
> the Live column says otherwise.

## All areas — one table

| # | Area | Dashboard | Customer app | Live-verified? | What's missing / blocker |
|--:|---|---:|---:|:--:|---|
| 1 | DB | **100%** | **95%** | ✅ schema live, RLS probed as `anon` | −5 customer: `payment_links.customer_id` backfill only covers links whose lead implied a customer |
| 2 | Backend | **97%** | **85%** | ❌ 0 rows ever served | −3: audio produced, not transmitted (BLK-1). −15: traveller data path never proven live (BLK-2/3) |
| 3 | UI | **85%** | **95%** | ⚠️ customer app deploys Ready; dashboard deploy red | Dashboard: 2 real TODOs, 1 feature not on the API. Deploys: BLK-4 |
| 4 | Auth | **80%** | **90%** | ❌ no login against a real DB | Guards verified in Chromium; token separation proven both directions |
| 5 | Validation | **90%** | **90%** | — | Password rules mirror server exactly; 422 crash fixed at every auth call site |
| 6 | Backend testing | **80%** | **80%** | n/a (local) | 80 tests pass. No coverage metric yet |
| 7 | Frontend testing | **60%** | **60%** | n/a (local) | 13+13 tests (password mirror, 422 envelope). Missing: component/interaction tests |
| 8 | Rate limiting / abuse | **90%** | **90%** | ❌ | All 6 unauthenticated endpoints covered, 4 tests. −10: in-memory — Redis needed for multi-worker |
| 9 | Deployment | **0%** | **100%** | customer app ✅ Ready | Dashboard + API fail on Root Directory settings (BLK-4) |
| 10 | CI/CD | **70% code / 0% live** | same | ❌ no runners allocated | Workflow proven correct; failure = Actions billing (BLK-5) |
| 11 | Observability | **70% stubbed** | **65% stubbed** | ❌ stub transport only | Going live = `SENTRY_DSN` (BLK-6). No alerting/uptime |
| 12 | Accessibility | **70%** | **75%** | — | axe-core: all scanned pages 0 violations. Not claimed: full-app audit, focus/keyboard testing |
| 13 | Compliance | **60% assessed** | **60% assessed** | — | 6 ✅ · 3 gaps (consent event row, ToS/Privacy docs, erasure path) · 4 decisions (BLK-8 etc.) |
| 14 | Docs / secrets | **85%** | **85%** | — | CLAUDE.md reconciled; secrets audit clean; backup policy undecided (BLK-7) |

## Stubbed vs live — the seams

| Seam | Built | Live? | The one thing to go live |
|---|---|:--:|---|
| Voice turn loop (STT → AI → TTS) | ✅ wired, tested, latency-logged | ❌ audio never transmitted | Plivo creds (BLK-1) |
| Traveller data path (`/travel/v1/me/*`) | ✅ 5 endpoints, token separation proven | ❌ 0 rows, no DB reachability | Service-role key + network (BLK-2/3) |
| Error tracking | ✅ stub transport proven firing | ❌ | `SENTRY_DSN` (BLK-6) |
| Deployment | ✅ customer app **live-green** | dashboard/API ❌ | Two Vercel Root Directory settings (BLK-4) |
| CI | ✅ workflow correct (passed runs #15–21) | ❌ | GitHub Actions billing (BLK-5) |

## Blocker index (detail in BLOCKERS.md)

BLK-1 Plivo creds · BLK-2 service-role key · BLK-3 sandbox network policy ·
BLK-4 two Vercel Root Directory fields · BLK-5 Actions billing · BLK-6 Sentry
DSN · BLK-7 backup policy · BLK-8 consent wording legal review · BLK-9
marketing-site scope · B-FE7-08 agency resolution for the customer app.
