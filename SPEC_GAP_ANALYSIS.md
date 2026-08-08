# Spec Gap Analysis — Blueprint & Dashboard vs. What Is Built

**Date:** 2026-08-08 · **Branch:** `Klara-ai`
**Sources:** `GoGaga_AI_Platform_Architecture_Blueprint.docx`, `GoGaga_Agency_Dashboard.docx`

---

## 0. Read this first — three findings that reframe the percentages

**1. The specs describe a different telecom stack than the one built.** The
blueprint names **Twilio** throughout — `/webhook/twilio/voice`,
`/webhook/twilio/stream`, "Twilio Conference Bridge", "twilio_sid" as a column.
The codebase is built on **Plivo**. This is not a naming detail: the webhook
signatures, the media-stream protocol, and the conference-bridge API are all
different. Every voice number below is against Plivo, not against the spec.

**2. The AI cannot speak on a call.** `ai_engine.run_turn()` and
`voice.synthesize_speech()` are both fully written and have **zero call sites**
— verified by grep across the whole `app/` tree. There is no turn loop. The
webhook does one batch STT at `stop`. So every "live intelligence" feature
(sentiment, whisper, per-turn scoring) runs **once per call, after hangup**.
This is the single largest gap in the build and it sits at the centre of Phase 2.

**3. Gemini is entirely absent.** The blueprint's multi-LLM routing strategy
assigns WhatsApp replies, lead summaries, morning briefs and follow-up drafts to
**Gemini Flash 1.5** — explicitly for cost. Zero references exist in the
codebase. Everything routes to Claude or to keyword stubs.

---

## 1. FRONTEND

### 1a. The 28 dashboard screens

The dashboard doc names 28 screens ("Screen 1 of 28"). Audited against routes
in `App.tsx` and files in `src/features/`:

| # | Screen | State | Where |
|---|---|---|---|
| 1 | Mission Control | ✅ | `/` |
| 2 | Journey Board | ✅ | `/journey-board` |
| 3 | Guest Story | ✅ | `/journey-board/:leadId` |
| 4 | AI Transcript | ✅ | `TranscriptStream` in S11 |
| 5 | Payment Link | ✅ | `/payment-links` |
| 6 | Dream Team | ✅ | `/team` |
| 7 | **Morning Brief** | ❌ **missing** | no screen, no backend route |
| 8 | Daily Report | ✅ | `/reports` |
| 9 | AI Playbook | ✅ | `/playbooks` + `/ai-config` |
| 10 | The Empire | ✅ | `/empire` |
| 11 | Live Call | ✅ | `/live-call` |
| 12 | Live Transcript | ✅ | `/live-call/:callId` |
| 13 | New Leads | ⚠️ partial | kanban column, not a dedicated screen |
| 14 | Hot Leads | ⚠️ partial | qualification filter, not a screen |
| 15 | Converted | ⚠️ partial | filter only |
| 16 | Lead Search | ⚠️ partial | search box on the board, not a screen |
| 17 | **Sentiment** | ⚠️ partial | panel in S11 + a report block; no analytics screen |
| 18 | Follow-up | ✅ | `/follow-ups` |
| 19 | Assign Agent | ✅ | `AssignAgent` |
| 20 | Send WhatsApp | ✅ | `/whatsapp` |
| 21 | **Agent Detail** | ❌ **missing** | no per-agent screen or stats |
| 22 | Activity Log | ✅ | `/activity` |
| 23 | Add Agent | ✅ | form on `/team` |
| 24 | Weekly Report | ✅ | `/reports` |
| 25 | Monthly Revenue | ✅ | `/reports` + `/cost` |
| 26 | Report WA | ⚠️ partial | schedules exist; `sendWhatsApp` not wired (B-P4-07) |
| 27 | Question Flow | ✅ | `/ai-config` |
| 28 | Follow-up Ladder | ✅ | `LadderEditor` |

**20 full · 6 partial · 2 missing → 23/28 = 82%**

### 1b. The 7 RBAC screens ("first screens to build")

The blueprint calls these the foundation of the whole app.

| # | Screen | State |
|---|---|---|
| 1 | Login | ✅ |
| 2 | User List | ✅ `/team` |
| 3 | Create / Invite User | ⚠️ form exists; **no invite email** is sent |
| 4 | **User Detail / Edit** | ❌ no detail screen — only activate/deactivate |
| 5 | **My Profile** | ❌ missing entirely (spec: "every role sees this") |
| 6 | **Role & Permissions matrix** | ❌ missing — spec wants a visual matrix that writes RLS |
| 7 | Branch Management | ✅ `/empire` |

**3 full · 1 partial · 3 missing → 3.5/7 = 50%**

### 1c. Stack conformance

| Spec | Built | Match |
|---|---|---|
| React 18 | React **19** | ⚠️ newer |
| TypeScript · Vite | same | ✅ |
| **TailwindCSS** | hand-written CSS | ❌ |
| **shadcn/ui** | none | ❌ |
| React Query | ✅ TanStack 5 | ✅ |
| **Zustand** | none (Query + local state) | ❌ |
| React Router v6 | v7 | ⚠️ |
| **Recharts** | none — no charting at all | ❌ |
| **Socket.io Client** | native WebSocket | ❌ |

**Stack conformance: 4 clean / 9 = ~44%.** Most are defensible substitutions,
but **Recharts matters**: the Sentiment screen (#17) and Monthly Revenue (#25)
are chart screens in the spec and there is no charting library in the project.

### **FRONTEND TOTAL: ~70%**
*(screens 82% × 0.6 + RBAC 50% × 0.25 + stack 44% × 0.15)*

---

## 2. BACKEND

### 2a. Spec REST endpoints — 14 named

| Endpoint | State |
|---|---|
| `POST /auth/login` · `/refresh` · `/logout` | ✅ all three |
| `GET/POST /users`, `GET/PATCH/DELETE /users/{id}` | ✅ all five |
| `GET /leads` | ✅ |
| `GET /calls/live` | ✅ |
| `POST /calls/{id}/takeover` | ✅ (4 variants) |
| `POST /webhook/twilio/voice` | ❌ **Plivo, not Twilio** |
| `POST /webhook/twilio/stream` | ❌ **Plivo, not Twilio** |
| `GET /ws/calls/{call_id}` | ✅ (browser auth fixed this sprint) |

**12/14 = 86%** by function; **0/2 Twilio webhooks** as specified.

Live-verified this session: 60 client calls → **0 path mismatches, 0 verb
mismatches** against the running server's OpenAPI; 48 correctly return 401.

### 2b. The blueprint's four build phases

**Phase 1 — Foundation: ~80%**
- Repos ✅ (monorepo, not the two repos specified)
- **`docker-compose.yml` ❌ MISSING** — spec requires backend + Redis + NGROK
- Supabase users/branches + RLS ✅ written
- JWT login/refresh/logout ✅ · RBAC middleware ✅
- 7 RBAC screens — 50% (above)
- GitHub Actions CI ✅ (`ci.yml`); **`deploy.yml` ❌ missing**
- **Postman collection ❌ absent** (spec names it in every phase)

**Phase 2 — Voice Core: ~40%** ← *the weakest layer*
- Twilio webhook → TwiML ❌ (Plivo)
- Deepgram STT ⚠️ present but **batch, not the streaming WebSocket** specified
- Claude personality prompt ✅
- **ElevenLabs TTS → stream back to caller ❌ `synthesize_speech` has ZERO call sites**
- Call records to Supabase ✅ · WS broadcast ✅ · live screen wired ✅
- **`run_turn()` has ZERO call sites — there is no turn loop, so the AI never replies during a call**

**Phase 3 — Intelligence: ~65%**
- Sentiment per chunk ✅ (keyword mode; no API key)
- Lead scoring ⚠️ writes a **constant 40** without an Anthropic key
- Agent takeover ⚠️ state machine + DB + WS all work; **audio bridging not provisioned** (B-P3-01)
- AI Whisper ✅ · Sarvam Telugu ⚠️ present, never exercised
- pgvector semantic search ✅ written; model download proxy-blocked

**Phase 4 — Automation: ~60%**
- WhatsApp summary ⚠️ send path built (stub mode) but **via Claude/keyword — Gemini absent**
- Razorpay ✅ (stub mode, full status machine)
- Follow-up ladder ✅ (scheduler + editor)
- **Morning Brief ❌ missing** — no screen and no generation route
- All screens wired ⚠️ 82%
- **Newman/Postman CI ❌ absent**

### **BACKEND TOTAL: ~62%**

---

## 3. DATABASE

### 3a. Spec's four core tables

| Spec | Built as | Columns |
|---|---|---|
| `users` | `ts_users` | ✅ role, branch_id, is_active all present |
| `leads` | `travel_leads` | ✅ **all 9 spec'd columns present** |
| `calls` | `travel_calls` | ✅ (`provider_sid`, not `twilio_sid`) |
| `transcripts` | `travel_transcripts` | ✅ incl. `sentiment` jsonb + embedding |

Plus **34 further tables** the spec never asked for (packages, payment_links,
whatsapp_outbox, fx_rate_snapshots, usage_metrics, tenant_billing…). Schema
design is **ahead** of the blueprint, not behind.

### 3b. Deliberate divergences

| Spec | Built | Verdict |
|---|---|---|
| `vector(1536)` | **`vector(384)`** | Correct — fastembed `bge-small` is local + free; spec's own note allows Sentence Transformers |
| Postgres `enum` types | `VARCHAR` + `CHECK` | Correct — enums can't be altered without a table rewrite |
| SQLAlchemy + Alembic | Supabase client + raw SQL | Divergence — no ORM, no Alembic anywhere |
| python-jose | PyJWT | Harmless |
| RLS on every table | ✅ written | Matches |

### 3c. The number that matters

**Schema designed: ~95%. Schema APPLIED: 0% — and unverifiable.**

Migrations `0009`–`0019` (11 of 19) have never been run. There is no database in
this environment and the Supabase connector is unauthenticated. I cannot confirm
that *any* migration is applied, including `0001`–`0008`.

### **DATABASE TOTAL: 95% designed / 0% verified**

---

## 4. Summary

| Layer | Complete | Blocking gap |
|---|---|---|
| **Frontend** | **~70%** | Morning Brief, Agent Detail, My Profile, Permissions matrix; no charting library |
| **Backend** | **~62%** | **No turn loop — the AI never speaks.** No Gemini. Twilio↔Plivo. No docker-compose, no Postman |
| **Database** | **95% designed / 0% verified** | 11 migrations unapplied; no DB access at all |
| **Overall vs spec** | **~65%** | |

### The five things that would move these numbers most

1. **Build the voice turn loop** — wire `run_turn()` and `synthesize_speech()`.
   Phase 2 jumps 40% → 85%, and it retroactively makes Phase 3's sentiment,
   whisper and scoring actually *live* rather than post-hangup. This is one
   change that lifts two phases.
2. **Apply the migrations.** Nothing below the API can be trusted until then.
3. **Decide Twilio vs Plivo, in writing.** Right now the spec and the code
   disagree and every future reader will re-litigate it.
4. **Add Gemini Flash** for WhatsApp/summaries/brief — the spec chose it for
   cost, and routing that volume to Claude is the expensive default.
5. **Build the 4 missing screens** — Morning Brief, Agent Detail, My Profile,
   Role & Permissions. That takes frontend 70% → ~88%.

### What is genuinely ahead of spec

Multi-currency with point-in-time FX snapshots, cost/usage metering with an
explicit estimated-vs-metered flag, tenant billing scaffolding, an append-only
activity log, and a synthetic second-tenant isolation fixture. None of this is
in either document.
