# GoGaga / Klara — Go-Live Roadmap
**Branch:** `Klara-ai`  
**Last updated:** 2026-08-10  
**Legend:** ✅ Done · 🔧 In progress · 🔑 Needs credential · 🚦 Needs decision · ❌ Blocked

---

## Phase 0 — Local Environment

| # | Item | Status | Notes |
|---|------|--------|-------|
| 0.1 | Supabase local stack (colima + supabase CLI) | ✅ Done | Ports shifted +1000 to avoid AquaAI conflict |
| 0.2 | FastAPI backend runs (`api/venv/`) | ✅ Done | `api/run.sh` (needs venv fix — see fix.md M5) |
| 0.3 | Agency dashboard dev server | ✅ Done | `http://localhost:5174`, proxies `/api` to :8000 |
| 0.4 | Customer app dev server | ✅ Done | Onboarding flow complete |
| 0.5 | Seed data (`POST /travel/v1/demo/seed-gogaga`) | ✅ Done | Test account: `advertsocialai+gogaga@gmail.com` / `TestPass123!` |

**Restart procedure:**
```bash
colima start
cd techscapeai-platform && supabase start -x vector,logflare
cd api && venv/bin/uvicorn app.main:app --reload --port 8000
cd agency-dashboard && npm run dev
```

---

## Phase 1 — Credentials (all 🔑 owner-action required)

| # | Credential | Env Var(s) | Unblocks | Status |
|---|-----------|-----------|---------|--------|
| 1.1 | Plivo voice | `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_PHONE_NUMBER`, `PUBLIC_BASE_URL` | Inbound voice webhook, live call pipeline | 🔑 Creds in `.env` — need Vercel env vars + ngrok URL |
| 1.2 | Deepgram STT | `DEEPGRAM_API_KEY` | English/Hindi speech-to-text | 🔑 Not set |
| 1.3 | Sarvam STT/TTS | `SARVAM_API_KEY` | Telugu STT (Saarika) + TTS (Bulbul) | 🔑 Not set |
| 1.4 | Anthropic Claude | `ANTHROPIC_API_KEY` | AI agent, real-time suggestions, post-call summaries | 🔑 Not set |
| 1.5 | ElevenLabs TTS | `ELEVENLABS_API_KEY` | Voice synthesis, barge-in | 🔑 Not set |
| 1.6 | Redis | `REDIS_URL` | Multi-worker JTI blacklist, call_feed pub/sub | 🔑 Not provisioned |
| 1.7 | Resend email | `RESEND_API_KEY` | Password reset emails, OTP delivery | 🔑 Not set |
| 1.8 | Supabase hosted | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Production DB (not local) | 🔑 Needs hosted project creds |

---

## Phase 2 — Code Fixes (from fix.md — can be done now)

### Critical
| # | Issue | File | Fix | Status |
|---|-------|------|-----|--------|
| C1 | Default JWT secrets accepted in prod | `api/app/core/config.py:71` | Add startup validator | 🔧 Planned |
| C2 | Password stored in localStorage | `customer-app/.../OnboardingContext.tsx:71` | Exclude from persist | 🔧 Planned |
| C3 | OTP/reset tokens lost on restart | `api/app/routers/techscape/auth.py:99` | Move to Supabase table | ❌ Needs DB migration on hosted Supabase |

### High
| # | Issue | File | Fix | Status |
|---|-------|------|-----|--------|
| H1 | Logout doesn't blacklist JWT | `agency-dashboard/src/lib/auth.tsx:74` | Call `POST /auth/logout` | 🔧 Planned |
| H2 | Supabase admin client recreated each request | `api/app/database/connection.py:22` | Singleton pattern | 🔧 Planned |
| H3 | Message count race condition | `api/.../business_service.py:200` | Atomic DB increment | ❌ Needs DB migration |
| H4 | WebSocket `/ws` not proxied in dev | `agency-dashboard/vite.config.ts:8` | Add `/ws` proxy entry | 🔧 Planned |
| H5 | `super_admin`/`agent` missing from `_VALID_ROLES` | `api/.../techscape/_deps.py:29` | Add missing roles | 🔧 Planned |

### Medium
| # | Issue | File | Fix | Status |
|---|-------|------|-----|--------|
| M1 | PATCH can't unset nullable fields | `api/.../business_service.py:174` | Remove None filter | 🔧 Planned |
| M2 | DashboardLayout crashes on empty user | `agency-dashboard/.../DashboardLayout.tsx:60` | Optional chaining | 🔧 Planned |
| M3 | Dual `require_role` implementations | `api/.../techscape/_deps.py:125` | Remove duplicate, re-export | 🔧 Planned |
| M4 | Google + Forgot-pw buttons broken | `customer-app/.../LoginPage.tsx:184,217` | Wire handlers | 🔧 Planned |
| M5 | `run.sh` missing venv activation | `api/run.sh` | Add `source venv/bin/activate` | 🔧 Planned |
| M6 | No onboarding step guards | `customer-app/src/App.tsx` | Add `RequireStep` guard | 🔧 Planned |

---

## Phase 3 — Voice Pipeline (blocked on Phase 1 credentials)

| # | Item | Blocked by | Status |
|---|------|-----------|--------|
| 3.1 | Plivo inbound webhook live test | 1.1 (Plivo creds + ngrok) | ❌ B-P2-01 |
| 3.2 | Live media stream + WS handler | 3.1 + Phase 2B code | ❌ B-P2-02, B-P2B-01 |
| 3.3 | English STT (Deepgram) integration | 1.2 | ❌ B-P2-03 |
| 3.4 | Telugu STT/TTS (Sarvam) integration | 1.3 | ❌ B-P3-05 |
| 3.5 | Claude AI agent in voice turn loop | 1.4 | ❌ B-P2-04 |
| 3.6 | ElevenLabs TTS synthesis | 1.5 | ❌ B-P2-05 |
| 3.7 | Real-time supervisor suggestions | 1.4 + 3.2 | ❌ B-P3-02 |
| 3.8 | Post-call AI summary | 1.4 | ❌ B-P3-03 |
| 3.9 | Per-participant recording URL | 1.1 | ❌ B-P3-06 |

---

## Phase 4 — Production Hardening

| # | Item | Status | Notes |
|---|------|--------|-------|
| 4.1 | Redis for JTI blacklist + call_feed | ❌ B-P3-04 | Needs REDIS_URL provisioned |
| 4.2 | OTP/reset tokens in DB | ❌ C3 | Needs migration on hosted Supabase |
| 4.3 | Atomic message counter | ❌ H3 | Needs `increment_monthly_messages` DB function |
| 4.4 | CORS: lock `ALLOWED_ORIGINS` to production domains | 🚦 Decision | Add production URLs to config |
| 4.5 | `DEBUG=False` enforced in production | 🔧 Planned | Blocked by C1 fix |
| 4.6 | Supabase RLS audit — all tables locked to service_role | 🚦 Needs review | travel_* tables need verification |

---

## Phase 5 — Deploys

| # | Item | Status | Notes |
|---|------|--------|-------|
| 5.1 | Vercel — `agency-dashboard` | ✅ Ready | Deploys on push to `Klara-ai` |
| 5.2 | Vercel — `customer-app` | ✅ Ready | Deploys on push to `Klara-ai` |
| 5.3 | Vercel — `techscapeai-platform` (marketing site) | ✅ Ready | Deploys on push to `Klara-ai` |
| 5.4 | Backend hosting (FastAPI) | 🚦 Decision | Not on Vercel — needs Railway/Render/Fly.io or Docker |
| 5.5 | Hosted Supabase project wired to prod backend | 🔑 Needs creds | Ref: `xhrrkwojitchaaghohvr` |

---

## Phase 6 — Legal / Compliance

| # | Item | Status |
|---|------|--------|
| 6.1 | Terms of Service text | 🚦 Decision |
| 6.2 | Privacy Policy text | 🚦 Decision |
| 6.3 | Marketing opt-in consent wording | 🚦 Decision |
| 6.4 | Data retention / backup policy | 🚦 Decision |

---

## Go-Live Checklist

Before flipping to production traffic:

- [ ] All Phase 1 credentials in Vercel environment variables
- [ ] Phase 2 code fixes merged to `main`
- [ ] C1: JWT secret validator passing (confirms prod secrets are real)
- [ ] Backend deployed to production host (Phase 5.4)
- [ ] Hosted Supabase wired (Phase 5.5)
- [ ] Redis provisioned (Phase 4.1)
- [ ] `DEBUG=False` in production env
- [ ] CORS locked to production domains
- [ ] Legal pages live (Phase 6)
- [ ] End-to-end smoke test: register → login → seed → journey board → logout

---

## Open Blockers Summary (from BLOCKERS.md)

| ID | Blocker | Owner | Unblock |
|----|---------|-------|---------|
| B-P2-01 | Plivo creds absent | Gowtham | Add to Vercel env vars |
| B-P2-03 | Deepgram + Sarvam keys absent | Gowtham | Add to Vercel env vars |
| B-P2-04 | ANTHROPIC_API_KEY absent | Gowtham | Add to Vercel env vars |
| B-P2-05 | ElevenLabs key absent | Gowtham | Add to Vercel env vars |
| B-P2B-01 | Phase 2B voice loop never ran | Gowtham | Needs all voice creds first |
| B-P3-04 | Redis not provisioned | Gowtham | Provision + set REDIS_URL |
| B-P3-07 | Local Supabase/colima not running at loop start | Gowtham | `colima start && supabase start` |
| DEBT-01 | No mouth-to-ear latency baseline | Gowtham | Run Phase 2B after creds |
| DEBT-02 | In-memory JTI doesn't survive restart | Gowtham | Redis (B-P3-04) |
