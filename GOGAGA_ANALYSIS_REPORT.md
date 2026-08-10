# GoGaga Analysis Report — the combined area scoreboard (both apps)

**Update rule: any commit that moves an area's completeness — up or down — must
update this file in the same commit.** This is the single combined view; the
narrative evidence behind each number lives in `PLATFORM_STATUS.md`, the
compliance detail in `COMPLIANCE_CHECKLIST.md`, and every blocker ID in
`BLOCKERS.md`.

Last updated: **2026-08-10** at `98f3f3d` (wave-2 run, local-seam checkpoint).

> **The caveat, rewritten 2026-08-10 — data HAS now travelled Postgres→screen.**
> A local Postgres 16 + pgvector with the real migrations, bridged to the
> UNMODIFIED app path by a minimal PostgREST shim (`scripts/local_seam/`),
> carried real rows end-to-end: real signup → real login → lead/customer/
> booking written via the API → traveller OTP login → `/me/trip` → the real
> customer-app UI rendered booking `SEAM-BALI-001` in Chromium (0 page
> errors), and the real dashboard UI rendered the lead on Mission Control and
> the Journey Board. Cross-token separation returned 401 against real data.
> **What remains unproven** is the managed-Supabase leg specifically: RLS-as-
> anon on the live stack (proven separately via MCP probes), service-role
> behaviors, and PostgREST beyond the shim's measured subset — those still
> wait on BLK-2/BLK-3. "Live ✅ (seam)" below means proven locally end-to-end;
> "Live ✅" without qualifier means proven on the deployed/managed stack.

## All areas — one table

| # | Area | Dashboard | Customer app | Live-verified? | What's missing / blocker |
|--:|---|---:|---:|:--:|---|
| 1 | DB | **100%** | **100%** | ✅ schema live, RLS probed as `anon`; ✅ (seam) all migrations incl. 0022 clean on vanilla PG16 | −5 CLOSED: 0022 makes the backfill exhaustive (phone is the lead's ONLY identity column — verified), declares the unlinkable remainder explicitly, and payments.py now sets customer_id at creation so the gap can't regrow. 0022 pending apply to live Supabase (MCP re-auth needed) |
| 2 | Backend | **97%** | **100%** | ✅ (seam) rows served end-to-end | −3 dashboard: audio produced, not transmitted (BLK-1). Customer −15 CLOSED: traveller path proven against real Postgres (OTP login → `/me/trip` → real booking) |
| 3 | UI | **95%** | **100%** | ✅ (seam) both UIs rendered real rows; customer deploys Ready, dashboard deploy red (BLK-4) | Wave-1's "1 feature not on the API" was a wording bug — the 13th is `layout`, correctly a shell. Marker 1 (hardcoded ws `seq:1`) FIXED — both emit sites now real-monotonic. Marker 2 (live-call audio UI) stays: BLK-1. Customer: null-dates-as-1/1/1970 bug found by real data, fixed |
| 4 | Auth | **100%** | **100%** | ✅ (seam) real logins | The wave-1 deduction ("no login against a real DB") closed: owner signup+login and traveller OTP login both exercised against real Postgres rows; cross-token separation 401 live; guards verified in Chromium |
| 5 | Validation | **100%** | **100%** | — | Scoring rule: every auth AND money/duration input validated client-side with rules that MIRROR the server, and server models mirror DB CHECKs. Server already rejected bad amounts (validator, 422 — a wave-2 claim to the contrary was corrected before push); closed this run: PaymentLinks + Packages forms now validate client-side (amount gt 0; price ge 0 mirroring the server; days integer ≥1), gt=0 surfaced into the OpenAPI schema |
| 6 | Backend testing | **100%** | **100%** | n/a (local) | Scoring rule (api/tests/COVERAGE_RULE.md): offline suite green + ALL 45 router modules exercised via TestClient success+failure + core/deps ≥90% (92%) + money logic behavior-tested + the real line-coverage number stated honestly: **54%** (uncovered = AI/report/provider adapters needing live creds, out of scope). 250 tests (was 80) |
| 7 | Frontend testing | **100%** | **100%** | n/a (local) | Scoring rule (customer-app/src/TESTING_RULE.md): critical flows have component/interaction tests + contract-pinned units; NOT claiming E2E vs a real backend. customer-app 31 tests (traveller login, OTP boxes incl. paste/focus/aria), dashboard 39 (login incl. 422-array regression, takeover machine matrix, TakeoverControls incl. no-optimistic-flip + 409) |
| 8 | Rate limiting / abuse | **100%** | **100%** | ✅ (seam) 2-process Redis trip proven | −10 CLOSED: limiter uses Redis (sorted-set sliding window, atomic pipeline) when REDIS_URL set, in-memory fallback otherwise (same graceful-degradation pattern as call_feed). Multi-worker proof: two separate processes share one budget — combined 11th request 429s. 6 new tests incl. dead-Redis fallback |
| 9 | Deployment | **0%** | **100%** | customer app ✅ Ready | Dashboard + API fail on Root Directory settings (BLK-4) |
| 10 | CI/CD | **70% code / 0% live** | same | ❌ no runners allocated | Workflow proven correct; failure = Actions billing (BLK-5) |
| 11 | Observability | **70% stubbed** | **65% stubbed** | ❌ stub transport only | Going live = `SENTRY_DSN` (BLK-6). No alerting/uptime |
| 12 | Accessibility | **70%** | **75%** | — | axe-core: all scanned pages 0 violations. Not claimed: full-app audit, focus/keyboard testing |
| 13 | Compliance | **60% assessed** | **60% assessed** | — | 6 ✅ · 3 gaps (consent event row, ToS/Privacy docs, erasure path) · 4 decisions (BLK-8 etc.) |
| 14 | Docs / secrets | **90%** | **90%** | — | CLAUDE.md reconciled; secrets audit clean; scoreboard self-maintenance now automated (gogaga-scoreboard skill + `scripts/check_scoreboard_updated.sh` CI check). Remaining: backup policy undecided (BLK-7) |

## Stubbed vs live — the seams

| Seam | Built | Live? | The one thing to go live |
|---|---|:--:|---|
| Voice turn loop (STT → AI → TTS) | ✅ wired, tested, latency-logged | ❌ audio never transmitted | Plivo creds (BLK-1) |
| Traveller data path (`/travel/v1/me/*`) | ✅ 5 endpoints, token separation proven | ✅ (seam) real rows→screen | Managed-Supabase leg only: service-role key + network (BLK-2/3) |
| Error tracking | ✅ stub transport proven firing | ❌ | `SENTRY_DSN` (BLK-6) |
| Deployment | ✅ customer app **live-green** | dashboard/API ❌ | Two Vercel Root Directory settings (BLK-4) |
| CI | ✅ workflow correct (passed runs #15–21) | ❌ | GitHub Actions billing (BLK-5) |

## Blocker index (detail in BLOCKERS.md)

BLK-1 Plivo creds · BLK-2 service-role key · BLK-3 sandbox network policy ·
BLK-4 two Vercel Root Directory fields · BLK-5 Actions billing · BLK-6 Sentry
DSN · BLK-7 backup policy · BLK-8 consent wording legal review · BLK-9
marketing-site scope · B-FE7-08 agency resolution for the customer app.
