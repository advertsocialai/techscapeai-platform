# GoGaga Analysis Report — the combined area scoreboard (both apps)

**Update rule: any commit that moves an area's completeness — up or down — must
update this file in the same commit.** This is the single combined view; the
narrative evidence behind each number lives in `PLATFORM_STATUS.md`, the
compliance detail in `COMPLIANCE_CHECKLIST.md`, and every blocker ID in
`BLOCKERS.md`.

Last updated: **2026-08-15** — full component-by-component re-validation pass corrected rows 2
(Backend), 3 (UI), 4 (Auth), and 6 (Backend testing): discovered `customer-app`'s traveller OTP
login is completely broken live (**BLK-14**, production-blocking) and that the "green" backend
test suite actually has 12/250 failing tests (same root cause as BLK-14). Earlier same day: a
13-agent full-repo validation audit corrected rows 1 (DB) and 9 (Deployment), both previously
overstated; `main` then fast-forwarded to `Klara-ai` and 2/3 Vercel projects moved to genuine
Production deploys, updating row 9 again same day. Prior update: 2026-08-10 at `cc58803`
(wave-2 push-to-100 run).

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
>
> **Correction, 2026-08-15 — the "traveller OTP login" leg of this claim no
> longer holds.** A full re-validation sweep found `customer-app` calls two
> endpoints (`/travel/v1/me/auth/request-otp`, `/travel/v1/me/auth/verify-otp`)
> that do not exist on the live-committed backend — only a single combined
> `POST /login` does. The seam proof above was evidently run against a
> frontend/backend pairing that has since drifted apart and was never
> reconciled with what's actually committed. See **BLK-14** — this is a real,
> currently-broken flow, not a stale doc.

## All areas — one table

| # | Area | Dashboard | Customer app | Live-verified? | What's missing / blocker |
|--:|---|---:|---:|:--:|---|
| 1 | DB | **100%** | **100%** | ✅ Supabase re-authorized 2026-08-15; live-verified directly | 2026-08-15: confirmed on the LIVE project (not just the repo schema) that `travel_leads` has no `email` column, and that `0022` is recorded as applied in `supabase_migrations.schema_migrations` despite the committed file being provably unable to succeed against this schema — the "applied clean" claim was false from the start (both `travel_leads` and `payment_links` were empty at the time, which is why no error was ever noticed). Applied `0023` (whatsapp_sessions — also never actually live despite being marked RESOLVED), `0024` (index), and `0025` (corrective phone backfill) directly via Supabase MCP; all three verified: RLS enabled + zero anon/authenticated grants on `whatsapp_sessions` (proven via an `anon`-role probe, not assumed), the new index has the exact intended definition, the backfill correctly matched/skipped test rows and is idempotent. Full-schema RLS sweep: 45/45 public tables have RLS enabled, 0 missing. Also found (see BLOCKERS.md BLK-13): `gogaga_leads`/`gogaga_sessions`/`contact_submissions` carry overly-broad anon/authenticated grants (undocumented tables with no migration file, PII-shaped columns) — currently harmless (proven: 0 rows visible to `anon`, RLS's zero-policy default-deny is holding), but fragile hygiene worth tightening |
| 2 | Backend | **97%** | **70%** | ✅ (seam) dashboard rows served end-to-end; ❌ customer-app traveller login path currently 404s live | −3 dashboard: audio produced, not transmitted (BLK-1). **Corrected 2026-08-15, customer −30**: the earlier "traveller path proven against real Postgres" claim no longer holds — `customer-app` calls two OTP endpoints (`/travel/v1/me/auth/request-otp`, `/verify-otp`) that don't exist on the committed backend; only a single combined `POST /login` does. Every real traveller login 404s. See **BLK-14** |
| 3 | UI | **95%** | **100%** | ✅ (seam) both UIs rendered real rows; both deploy Ready (BLK-4 resolved), but agency-dashboard's Production Branch setting isn't `main` (BLK-12) | **Corrected 2026-08-15**: this row's "dashboard deploy red (BLK-4)" was stale — BLK-4 (Root Directory misconfig) resolved 2026-08-10, agency-dashboard deploys Ready same as everything else; the row 9/seam-table's current BLK-12 (Production Branch not set to `main`) is the real live issue. Wave-1's "1 feature not on the API" was a wording bug — the 13th is `layout`, correctly a shell. Marker 1 (hardcoded ws `seq:1`) FIXED — both backend emit sites verified real-monotonic (frontend still carries a couple of stale explanatory comments describing the old behavior, harmless but worth a pass). Marker 2 (live-call audio UI) stays: BLK-1. Customer: null-dates-as-1/1/1970 bug found by real data, fixed |
| 4 | Auth | **100%** | **70%** | ✅ (seam) dashboard real logins; ❌ customer-app traveller OTP login broken | Dashboard: owner signup+login exercised against real Postgres rows, cross-token separation 401 live, guards verified in Chromium. **Corrected 2026-08-15, customer −30**: the earlier "traveller OTP login...exercised against real Postgres" claim was against a frontend/backend pairing that has since drifted — the frontend's two-step OTP calls hit endpoints that don't exist on the committed backend. See **BLK-14**, production-blocking, needs Gowtham's decision |
| 5 | Validation | **100%** | **100%** | — | Scoring rule: every auth AND money/duration input validated client-side with rules that MIRROR the server, and server models mirror DB CHECKs. Server already rejected bad amounts (validator, 422 — a wave-2 claim to the contrary was corrected before push); closed this run: PaymentLinks + Packages forms now validate client-side (amount gt 0; price ge 0 mirroring the server; days integer ≥1), gt=0 surfaced into the OpenAPI schema |
| 6 | Backend testing | **95%** | **95%** | n/a (local) | **Corrected 2026-08-15**: the "offline suite green" claim was false — actually running `pytest tests/` shows **12 of 250 tests failing** (238 passing), not the claimed full green. All 12 share one root cause: `test_router_surface.py`'s and `test_public_rate_limit.py`'s traveller-OTP tests target `/travel/v1/me/auth/request-otp`, the same nonexistent endpoint behind **BLK-14** — this is a real product bug the suite correctly caught, not test staleness. Scoring rule (api/tests/COVERAGE_RULE.md) otherwise holds: ALL 45 router modules exercised via TestClient success+failure + core/deps ≥90% (92%) + money logic behavior-tested + line coverage **54%** (uncovered = AI/report/provider adapters needing live creds, out of scope). 250 tests (was 80); −5 until the suite is actually green |
| 7 | Frontend testing | **100%** | **100%** | n/a (local) | Scoring rule (customer-app/src/TESTING_RULE.md): critical flows have component/interaction tests + contract-pinned units; NOT claiming E2E vs a real backend. customer-app 31 tests (traveller login, OTP boxes incl. paste/focus/aria), dashboard 39 (login incl. 422-array regression, takeover machine matrix, TakeoverControls incl. no-optimistic-flip + 409) |
| 8 | Rate limiting / abuse | **100%** | **100%** | ✅ (seam) 2-process Redis trip proven | −10 CLOSED: limiter uses Redis (sorted-set sliding window, atomic pipeline) when REDIS_URL set, in-memory fallback otherwise (same graceful-degradation pattern as call_feed). Multi-worker proof: two separate processes share one budget — combined 11th request 429s. 6 new tests incl. dead-Redis fallback |
| 9 | Deployment | **90% — 2/3 live on Production** | same | ✅ `techscapeai-platform` + `klara-customer-app` confirmed `Ready` on `target: "production"`, real domains; ⚠️ `agency-dashboard` still preview-only | 2026-08-15: `main` fast-forwarded to `Klara-ai` (113 commits) per Gowtham's go-ahead. `techscapeai-platform` and `klara-customer-app` immediately picked this up as a real Production deploy — `techscapeai-platform.vercel.app` and `stagingklara.techscapeai.in` now serve current code. `agency-dashboard`'s latest deployment from the same push still shows `target: null` — its Vercel Production Branch setting is not `main` (BLK-12), a dashboard-only fix; no API/MCP tool this session can read or set it |
| 10 | CI/CD | **manual (Actions removed)** | same | ⚠️ GitHub Actions CI removed, not fixed | BLK-5 RESOLVED 2026-08-10 by removal, not billing fix: `.github/workflows/ci.yml` moved to `.github.backup/` (commit 00c19d8) — Vercel's build step gates deploys instead. `pytest tests/` (250 tests) + scoreboard/roadmap checks still exist in `scripts/`, run manually. Restore `.github.backup/` to re-enable gating CI if Actions billing resolves later |
| 11 | Observability | **100% stubbed-complete** | **100% stubbed-complete** | ❌ stub transport only | Alerting-as-code: 3 rules (error-rate spike, voice-turn median budget, payment-signature burst) with real producer hooks, cooldowns, opt-in asyncio loop; uptime checks defined (scripts/uptime_checks.yaml + runner); ErrorBoundary components in both apps reporting into the stub (dashboard's errorReporting was never initialized — now wired). 20 tests. Live = `SENTRY_DSN` (BLK-6) + real deploy URLs |
| 12 | Accessibility | **100%** | **100%** | ✅ (seam) scanned with real data, authed | Scoring rule: full-app axe-core WCAG 2 A/AA — **all 34 routes of both apps, 0 violations** (fixed this run: unnamed password-eye button, 15 unlabeled dashboard selects, --text-xs/--text-dim/blue-as-text contrast tokens) + keyboard pass on the 5 interactive-heavy screens (18-19 focusables reachable each). NOT claimed: manual screen-reader certification |
| 13 | Compliance | **90% (mechanisms 100%)** | **90% (mechanisms 100%)** | — | All 3 buildable gaps CLOSED: consent event row written when answer XML is served; DPDP erasure endpoint anonymizes 10 tables (money kept, activity_log'd, 409 on edge cases); ToS/Privacy DRAFT skeletons with schema-derived facts. The remaining 10 is not code: legal wording + 4 decisions (BLK-8, C-4, D-6) |
| 14 | Docs / secrets | **95% (mechanism 100%)** | **95% (mechanism 100%)** | — | CLAUDE.md reconciled; secrets audit clean; scoreboard self-maintenance automated. Backup MECHANISM built (`scripts/backup_db.sh` + BACKUP_OPTIONS.md) — BLK-7 is now a one-line A/B/C choice plus one restore drill, the only remaining 5 |

## Stubbed vs live — the seams

| Seam | Built | Live? | The one thing to go live |
|---|---|:--:|---|
| Voice turn loop (STT → AI → TTS) | ✅ wired, tested, latency-logged | ❌ audio never transmitted | Plivo creds (BLK-1) |
| Traveller data path (`/travel/v1/me/*`) | ✅ 5 endpoints, token separation proven | ✅ (seam) real rows→screen | Managed-Supabase leg only: service-role key + network (BLK-2/3) |
| Error tracking + alerting | ✅ stub transport + 3 alert rules with real producer hooks + error boundaries both apps | ❌ | `SENTRY_DSN` (BLK-6) |
| Deployment | ✅ all three projects committed + configured | ✅ 2/3 **live on Production** (techscapeai-platform, klara-customer-app); agency-dashboard preview-only | Build-failure part RESOLVED (BLK-4); production-targeting done for 2/3 — agency-dashboard needs its Vercel Production Branch setting fixed (BLK-12, dashboard-only) |
| CI | ✅ complete: gating pytest (250 tests), coverage step, scoreboard check | ⚠️ removed, not live | RESOLVED-by-removal (BLK-5) — Vercel gates deploys instead; scripts remain for manual runs |
| Backups | ✅ pg_dump mechanism + retention (scripts/backup_db.sh) | ❌ | Policy choice A/B/C (BLK-7) + one restore drill |
| Erasure / consent | ✅ endpoint + event row live in code, tested | ✅ (seam) | Wording only (BLK-8) |

## Blocker index (detail in BLOCKERS.md)

BLK-1 Plivo creds · BLK-2 service-role key · BLK-3 sandbox network policy ·
BLK-4 two Vercel Root Directory fields · BLK-5 Actions billing · BLK-6 Sentry
DSN · BLK-7 backup policy · BLK-8 consent wording legal review · BLK-9
marketing-site scope · B-FE7-08 agency resolution for the customer app.
