---
name: gogaga-backend
description: Conventions, real endpoint inventory, and verified patterns for the techscapeai-platform FastAPI backend (Option B — GoGaga is built by EXTENDING this repo, never a rewrite). ALWAYS use this skill when writing, editing, reviewing, or planning ANY backend code in api/app/ — routers, services, RBAC, Supabase access, voice pipeline, payments, dashboard endpoints. Trigger on any mention of GoGaga, Klara, dashboard screens, phases, leads, calls, transcripts, wiki, playbooks, franchisees, or businesses. Use even for one-line fixes.
---

# GoGaga Backend Skill (real-repo corrected)

FastAPI + Supabase (service-role client) backend. TWO product halves in one repo:
- `routers/techscape/` — marketing/automation platform (~80 endpoints). **OUT OF SCOPE — never modify** except: auth.py, _deps.py, admin.py, businesses.py (the extension points).
- `routers/travel/` — GoGaga travel product (~53 endpoints). This is where GoGaga work happens.

## Non-negotiable conventions
1. **DB access**: Supabase service-role client via the existing pattern (`app/database/connection.py`, services instantiate their table access). Never SQLAlchemy, never a second client pattern.
2. **JWT — real shape (do not assume otherwise)**:
   - Access claims: `sub` (user id), `biz` (business id), `role`, `type:"access"`, `iat`, `exp`, `jti` — signed with `settings.JWT_SECRET`, HS256, TTL 15 min
   - Refresh claims: `sub`, `biz`, `type:"refresh"`, `jti` — **separate secret** `settings.JWT_REFRESH_SECRET`, TTL 7 days
   - Helpers live in `core/security.py` (issue_access_token / issue_refresh_token / decode_*). Never duplicate signing.
3. **Auth/RBAC**: dual auth in `routers/techscape/_deps.py` — Bearer JWT (ts_users) OR X-API-Key (ts_businesses). `require_business` resolves a principal dict `{**business_row, "_user": user}`; `require_role()` gates on top. Roles (post-migration): super_admin > admin > agent > viewer (legacy: manager→admin, user→agent during transition). "Assigned only" scoping for agents on leads/calls per the blueprint matrix.
4. **Multi-tenancy**: everything scopes by `business_id` → `ts_businesses`. Branch concept maps onto `travel_franchisees` (or a branch linkage added in Phase 1 — follow the migration, check before assuming).
5. **RLS pattern — service-role-only**: travel tables `ENABLE ROW LEVEL SECURITY` + `REVOKE ALL FROM anon, authenticated`. The FastAPI layer is the gatekeeper; there are NO JWT-claim policies. Never add Supabase-Auth-style policies here.
6. **Deletes**: soft only (`is_active=false` / status flip). Out-of-scope resources → 404 (never 403 — don't leak existence).
7. **Responses**: Pydantic models; never leak password_hash / api_key_hash / credentials_encrypted. Errors: `{"detail": "..."}` clean JSON.
8. **Verification**: done = gogaga-verifier checks pass, incl. failure paths. Regression floor: POST /api/techscape/auth/login + GET /api/travel/wiki stay green.

## Real endpoint inventory — status legend ✅ built · 🔧 extend · ❌ missing
Read `references/api-contract.md` for the full 133-endpoint map. Headlines:
- auth: login ✅ refresh ✅ me ✅ logout ✅ otp ✅ oauth ✅ · password strength validated ✅
- RBAC: require_role ✅ fixed (core/deps.py) · role migration done (migration 0002) · logout JTI blacklist ✅ (in-memory, see DEBT)
- users mgmt: CRUD ✅ (users.py) · branches ✅ (branches.py) · assigned-only leads scoping ✅ (agents see only their rows)
- travel_leads ✅ + phone/assigned_agent/language/embedding(384) columns ✅ (migration 0003) · assigned-only for agent-role ✅
- wiki ✅ CRUD + semantic search ✅ (bge-small/fastembed, cosine via match_travel_wiki() RPC, keyword fallback) · embeddings populated ✅ (all rows backfilled)
- playbooks ✅ executor+scheduler → follow-up ladder maps onto this (P4, extend not rebuild)
- WhatsApp: wapi provider + inbound dispatcher ✅ → 🔧 extend (P4)
- voice (Phase 2 built): Plivo answer webhook ✅ · media-stream WS ✅ · travel_calls/travel_transcripts tables ✅ · STT routing (batch-on-stop) ✅ · AI engine (Claude tool-calling) ✅ · TTS client skeleton ✅ · VOICE_TURN log format ✅ · live calls REST API ✅ · call feed WS ✅ · outbound-hours guard (compliance.py) ✅ built but NOT wired · **streaming turn loop ❌ (P2B)**
- payments/razorpay ❌ · dashboard aggregates ❌ (P4)

## Domain rules
- **Telephony**: Plivo/Exotel for +91 domestic voice (Twilio CANNOT legally carry India↔India; keep Twilio for WhatsApp/intl). Column name: use provider_sid (twilio_sid only if extending blueprint naming).
- **India media anchoring**: NEVER bridge a domestic (+91 PSTN) leg to an international relay — this is a Plivo/TRAI compliance rule. Foreign supervisors must join via browser SIP on an India Plivo account, or receive transcript-only. Any code mixing domestic and international legs is a hard reject.
- **STT/TTS routing**: Deepgram Nova-2 (English/Hindi, default) | Sarvam Saarika v2 (Telugu/code-mix); ElevenLabs Flash TTS (en/hi) | Sarvam Bulbul (te). Engine-agnostic transcript rows (stt_engine, language cols).
- **In-call LLM**: Claude via `services/travel/ai_engine.py` (the travel-scoped version — do NOT modify `services/techscape/ai_service.py`). Tool-calling ONLY for extraction; dynamic data behind tools, never in prompt.
- **Cost routing (blueprint §7)**: Claude = voice/sentiment/whisper only; Gemini = chat/summaries/briefs.
- **Payments**: verify X-Razorpay-Signature AND lookup-confirm before status=paid; explicit expiry.
- **Compliance**: outbound 09:00–21:00 IST (`compliance.py:is_within_outbound_hours()`), DND scrub, 140-series CLI.
- Latency: ≤1.1s median mouth-to-ear; log VOICE_TURN per turn (see api-conventions.md and voice-pipeline.md for exact log format).

## Before writing code
- Endpoints → references/api-contract.md + api-conventions.md
- Tables/DDL → references/schema.md (real tables) + gogaga-migrations skill
- Voice work → references/voice-pipeline.md
- New env var → references/env-vars.md (real names: SUPABASE_SERVICE_ROLE_KEY, JWT_SECRET, JWT_REFRESH_SECRET...)

## Phase gates (Option B) — current state
- **P1 DONE**: require_role fixed · logout ✅ · role migration (0002) · users CRUD · branches · assigned-only leads RBAC
- **P2 DONE**: travel_calls/travel_transcripts (migration 0003) · Plivo webhook + media-stream WS · batch STT routing · Claude tool-calling AI engine (ai_engine.py) · TTS client + VOICE_TURN log · live calls API + call feed WS (call_feed.py) · wiki semantic search + embeddings (migration 0004, bge-small/fastembed 384-dim) · compliance outbound-hours guard (unwired)
- **P2B IN PROGRESS**: MPC migration (bare-Stream → Plivo Multiparty Call) · streaming STT (Deepgram live WS + Sarvam WS) · real-time turn loop + streaming TTS + barge-in · the actual C6 deliverable (two-way phone conversation)
- **P3 NEXT**: sentiment scoring · supervisor takeover (audio) · follow-up ladder
- **P4**: WhatsApp/Razorpay/dashboard aggregates

Never build ahead of the current phase gate.
