# GoGaga — Go-Live Roadmap: every stub, every blocker, one step-by-step path to real

**Purpose of this document:** `GOGAGA_ANALYSIS_REPORT.md` tells you the score. `BLOCKERS.md` is a flat
ledger of 60+ IDs with no order. Neither tells you **what to do, in what order, to turn the last
stub into a live system.** This file does that — every pending item, grouped into dependency-ordered
phases, each with the exact steps to close it and what closing it unlocks next.

**How to read it:** work top to bottom. Phase 0 unblocks the environment itself; nothing in later
phases is testable without it. Phases 1–8 are mostly gated on **credentials** or **decisions only
Gowtham can make** — no more code is needed for the large majority of them (that was the point of
the wave-1/wave-2 runs: get every seam stub-complete so the remaining work is procurement and
policy, not engineering). Phase 9 is the opposite: zero-credential code fixes that can happen any
time, by anyone, right now. Phase 10 is the non-blocking debt backlog — real, tracked, not urgent.

**Source of truth cross-references** — this file doesn't duplicate their numbers, it sequences them:
| File | What it holds |
|---|---|
| `GOGAGA_ANALYSIS_REPORT.md` | The scoreboard — 14 areas × 2 apps, Live-verified column, stubbed-vs-live seams |
| `BLOCKERS.md` | The flat ID ledger (BLK-*, B-P*-*, B-FE*-*, DEBT-*) — this file's raw material |
| `COMPLIANCE_CHECKLIST.md` | Legal/compliance detail behind Phase 6 |
| `PLATFORM_STATUS.md` | Narrative evidence — how each score was measured |
| `.claude/skills/gogaga-scoreboard/SKILL.md` | The rule keeping all of the above in sync |

---

## Legend

| Symbol | Meaning |
|---|---|
| 🔑 | Needs a credential (API key, account) — procurement, not engineering |
| 🚦 | Needs a **decision** only Gowtham can make — no credential, no code |
| 🏢 | **Permanently human-gated** — must never be automated, not even after credentials exist |
| 💰 / 💬 | Fires a real charge / real message — requires **explicit human confirmation every single time**, never a standing approval |
| 🛠️ | Code-only fix, zero credential, zero decision — can happen in any session, any time |
| ✅ | Mechanism/code is 100% built and tested; only the item to its left is missing |

---

## Phase index

| Phase | Goal | Item count | Blocking type |
|---|---|---|---|
| [0](#phase-0--access--platform-prerequisites) | Unblock the environment itself | 3 | 🔑🚦 |
| [1](#phase-1--credentials-the-one-time-unlock) | One `.env` pass unlocks 8 downstream phases | 9 | 🔑 |
| [2](#phase-2--voice-pipeline-go-live) | A real phone call, end to end | 7 | 🔑 (built on Phase 1) |
| [3](#phase-3--data-path-go-live-managed-supabase) | Managed Supabase serving real rows | 3 | 🔑🚦 |
| [4](#phase-4--payments--messaging-go-live) | Real money, real WhatsApp | 6 | 🔑💰💬🚦 |
| [5](#phase-5--deploys--ci-go-live) | Green deploys, green CI | 2 | 🚦 (2 clicks + 1 billing page) |
| [6](#phase-6--compliance--legal) | Legally defensible consent + policy docs | 4 | 🚦 (legal review) |
| [7](#phase-7--multi-tenant-real-test) | Prove isolation against a real second agency | 3 | 🚦🏢 |
| [8](#phase-8--marketing-site-new-scope) | The `frontend/` site CLAUDE.md describes | 1 | 🚦 (new scope) |
| [9](#phase-9--zero-credential-code-fixes-do-these-anytime) | Fixes needing nothing from Gowtham | 2 | 🛠️ |
| [10](#phase-10--technical-debt-backlog-non-blocking) | Hardening backlog, not go-live blocking | 11 | 🛠️ |

**44 tracked items total.** Phases 0–8 gate on Gowtham (credentials or decisions); Phase 9 is
actionable immediately in any session; Phase 10 is real but does not block go-live.

---

## Phase 0 — Access & platform prerequisites

Nothing below this line is testable from an agent sandbox until these three are done. This is the
critical path's critical path.

### 0.1 — Re-authorize the Supabase MCP connector 🔑
**State:** dropped mid-session on 2026-08-10; blocks applying migration `0022` (already written,
applied clean on a local Postgres, verified zero cross-tenant rows) to the **live** database.
**Steps:**
1. Open the connector settings for this Claude session (claude.ai connector settings, or `/mcp` in
   an interactive CLI session).
2. Re-authorize the `supabase` connector against the `xhrrkwojitchaaghohvr` project.
3. Tell the agent to resume — it will run `apply_migration` for `0022`, then the standard
   verification queries already documented in that file's header comment.
**Unlocks:** any live-DB check, applying `0022`, re-proving RLS-as-anon against the real stack.

### 0.2 — Two Vercel Root Directory clicks 🚦
**State:** code-side 100% ready (`agency-dashboard/vercel.json`, `api/pyproject.toml
[tool.vercel] entrypoint`) since wave-2. Exact click-path already written down —
see [`scripts/DEPLOY_READINESS.md`](scripts/DEPLOY_READINESS.md). Duplicated here for
completeness — this is [Phase 5.1](#51--two-vercel-root-directory-clicks-).

### 0.3 — GitHub Actions billing 🚦
**State:** CI pipeline is 100% code-complete and gating (250 backend tests, coverage step,
scoreboard check). Every job has failed runnerless (`runner_id: 0`, ~2s, no logs) since run #22.
This is [Phase 5.2](#52--github-actions-billing-).

---

## Phase 1 — Credentials: the one-time unlock

One `.env` pass. Every credential below is read from `api/app/core/config.py`'s `Settings` class —
add it there (or the platform's real secret manager for the deploy target), restart the API, and
the corresponding stub flips to live with **no code changes** — every seam was built stub-first
specifically so this would be true.

| # | Credential | Env var(s) | Unlocks | Current stub behavior |
|---|---|---|---|---|
| 1.1 | 🔑 Plivo | `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_PHONE_NUMBER`, `PUBLIC_BASE_URL` | Real inbound/outbound calls, audio playback ([BLK-1](#reference-blocker-index), B-P2-01) | Webhook signature check fails open when unset; TTS bytes produced but never transmitted |
| 1.2 | 🔑 Deepgram + Sarvam | `DEEPGRAM_API_KEY`, `SARVAM_API_KEY` | Real STT (English via Deepgram, Telugu via Sarvam Saarika) (B-P2-03, B-P3-05) | `transcribe_utterance()` returns a stub transcript |
| 1.3 | 🔑 Anthropic | `ANTHROPIC_API_KEY` | Real conversation turns, real-time suggestions, post-call summaries, real sentiment, and — as a direct consequence — real report content (B-P2-04, B-P3-02, B-P3-03, DEBT-07, B-P4-05: report sentiment/summaries stop being the flat `lead_score=40` constant the moment this key exists) | `ai_engine.run_turn()` returns a heuristic reply; sentiment is a clamped constant |
| 1.4 | 🔑 ElevenLabs | `ELEVENLABS_API_KEY` | Real TTS synthesis + barge-in latency (B-P2-05) | `synthesize_speech()` returns silence |
| 1.5 | 🔑 Supabase service role | `SUPABASE_SERVICE_ROLE_KEY` | The managed-Supabase leg of the data path — RLS-as-anon live, service-role writes ([BLK-2](#reference-blocker-index)) | The app path itself is already proven via the local seam (`scripts/local_seam/`) — this closes only the "against the real host" half |
| 1.6 | 🔑 Redis | `REDIS_URL` | Multi-worker rate limiting AND multi-worker live-call feed/JTI consistency in ONE variable (B-P2-06, B-P3-04, DEBT-02 — same root cause, one fix) — both already have graceful in-memory fallback wired | Both features work today, per-process only |
| 1.7 | 🔑 Razorpay | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Real payment links (B-P4-01) — see [Phase 4.1](#41--one-real-razorpay-payment-link--) for the human-confirmation gate that follows | `stub://` links; full status machine already runs against real DB rows |
| 1.8 | 🔑 WhatsApp/Meta | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` (or BSP equivalent) | Real WhatsApp sends (B-P4-02) — see [Phase 4.2](#42--one-real-whatsapp-send--) | Writes to `whatsapp_outbox`, calls nothing |
| 1.9 | 🔑 Sentry | `SENTRY_DSN` (api), `VITE_SENTRY_DSN` (both frontends) + `pip install sentry-sdk` + `npm install @sentry/browser` in both apps | Live error tracking + the wave-2 alerting rules firing for real ([BLK-6](#reference-blocker-index)) | Stub transport: events logged + counted, nothing leaves the process |

**Verification after each addition:** `scripts/regression_check.sh` (the floor check — login +
one authenticated GET), then the credential-specific test named in its BLOCKERS.md row above.

---

## Phase 2 — Voice pipeline go-live

Depends on **1.1, 1.2, 1.3, 1.4** (Plivo + STT + Claude + TTS). This is "Phase 2B" in the ledger's
own numbering — it never ran.

### 2.1 — Stand up the MPC leg 🔑 (closes B-P2-02, B-P3-01)
**Steps:**
1. With 1.1–1.4 set, expose the API publicly (`PUBLIC_BASE_URL` — ngrok for a first test, a real
   domain for production).
2. Point a real Plivo number's answer webhook at `POST {PUBLIC_BASE_URL}/api/travel/v1/webhooks/voice/answer`.
3. Call the number. `voice_turn_service.py` (already wired, [DEBT-20 closed]) will run the full
   loop: customer speaks → real STT → `ai_engine.run_turn()` with real Claude → real ElevenLabs TTS
   → played back over the live call.
**Verify:** the call completes with an audible AI reply; `travel_calls`/`travel_transcripts` rows
exist; grep the logs for `VOICE_TURN` and confirm per-hop latencies are populated.

> **Ledger note:** `DEBT-04` ("`ai_engine.run_turn()` has zero call sites") describes the exact
> defect `DEBT-20` fixed and marked RESOLVED — `DEBT-04`'s own row was never flipped when `DEBT-20`
> superseded it. No code action needed here; `BLOCKERS.md` should mark `DEBT-04` RESOLVED
> (see `DEBT-20`) the next time that file is touched.

### 2.2 — Measure headroom, decide inline vs. async (DEBT-01) 🚦
Once 2.1 produces a real `headroom_ms` baseline: if ≥300ms, upgrade T3 (suggestions)/T4 (sentiment)
from post-call batch to synchronous inline-in-the-turn-loop. This is a decision gated on data that
only exists after 2.1.

### 2.3 — Supervisor live controls (B-P3-01) 🔑
Same credentials as 2.1. Run the monitor/barge/takeover/release sequence on a real call — the
takeover state machine is fully built and unit-tested; this is its first live exercise.

### 2.4 — Telugu path (B-P3-05) 🔑
Needs `SARVAM_API_KEY` (1.2) + a real call (2.1). Exercises Saarika STT + Bulbul TTS + barge-in
specifically in Telugu.

### 2.5 — Per-participant recording URL (B-P3-06) 🔑
Falls out of 1.1 automatically — `travel_calls.recording_url` populates once Plivo credentials
exist and a call completes.

### 2.6 — Fix the WS contract drift before any dashboard is built against it (DEBT-05) 🚦🛠️
**State:** the code emits `type:"suggestion"`/`"sentiment"` shapes that don't match
`api-conventions.md`'s documented `type:"whisper"` contract; five spec'd message types
(`speaking`, `intent`, `event`, `extraction`, `whisper`) are never emitted at all.
**Decision needed:** for each undocumented/mismatched type — align the code to the doc, or cut it
from the doc. **Do this before Phase 2 hands off to any frontend work that assumes the doc is
correct** — it currently isn't.

### 2.7 — Fix the fire-and-forget task leak (DEBT-06) 🛠️
`schedule()` in three services (suggestions, sentiment, post-call) calls
`asyncio.ensure_future()` and discards the handle — CPython can garbage-collect them mid-flight.
Fix: hold strong references in a module-level set + `add_done_callback` that logs exceptions. No
credential needed; do this alongside 2.1 testing since real calls are what will expose it.

---

## Phase 3 — Data path go-live (managed Supabase)

Depends on **0.1** (MCP re-auth) and **1.5** (service-role key).

### 3.1 — Apply migration 0022 to the live database 🔑
**Steps:** once 0.1 is done, run `apply_migration` for
`supabase/migrations/0022_payment_links_customer_backfill_exhaustive.sql` (verification queries
are in the file's own header — cross-tenant check must return 0).

### 3.2 — Re-prove RLS-as-anon on the live stack 🔑 (closes B-P4-06)
The wave-1 run already probed every table as `anon` against live Supabase and got denied on all
44. Re-run that probe after 3.1 to confirm nothing regressed — this is also the live-DB half of
`B-P4-06`'s cross-phase access-matrix sweep (`scripts/access_matrix.py` +
`scripts/regression_check.sh`), unrunnable until 0.1/1.5 exist.

### 3.3 — Resolve multi-agency traveller lookup (B-FE7-08) 🚦
**State:** `travel_customer_profiles` is unique per `(business_id, email)`, not globally — the same
email can exist under several agencies. Traveller login collects only an email, so when a person
has booked with two agencies, the lookup currently picks deterministically (oldest wins) rather
than correctly. Not a cross-person leak — just possibly the wrong agency's booking shown.
**Decision needed:** how does `customer-app` learn which agency it serves — a subdomain per
agency, per-agency branding config, or a deep link carrying `business_id`? Once decided, scope the
`_profile_by_email` lookup in `api/app/routers/travel/traveller.py` by it (one function, already
isolated for exactly this swap).

> **Ledger note:** `B-FE7-01` ("is `customer-app` agency self-serve or traveller-facing?") is the
> parent question this and `B-FE7-02`/`B-FE7-03` answer. The latter two's rows say RESOLVED
> (traveller-facing, OTP-based identity) but `B-FE7-01`'s own row was never flipped —
> `BLOCKERS.md` should mark it RESOLVED-by-B-FE7-02/03 the next time that file is touched. Not a
> live blocker; `B-FE7-08` above is the one genuinely open piece of the traveller-identity question.

---

## Phase 4 — Payments & messaging go-live

### 4.1 — One real Razorpay payment link 🔑💰
Depends on **1.7**. **This requires explicit human confirmation every time — never a standing
approval.** Steps:
1. Add Razorpay **test-mode** keys (1.7).
2. Create one payment link via the dashboard UI.
3. **Before actually charging/paying it: get Gowtham's explicit go-ahead for that one transaction.**
4. Verify the webhook signature check accepts the real Razorpay callback and the status machine
   (`created→sent→viewed→paid`) advances correctly.

### 4.2 — One real WhatsApp send 🔑💬
Depends on **1.8**. **Same rule — explicit confirmation every time, to a human-confirmed test
number, never a real customer**, until templates are approved (4.3).

### 4.3 — Meta template approval for scheduled reports (B-P4-07) 🚦 (calendar-time, not engineering-time)
**State:** correct-by-design, not a bug — a scheduled report is unsolicited, so it falls outside
WhatsApp's 24-hour customer-service window and the provider ABC correctly refuses `send_freeform`
for it. **Fix:** register a Meta-approved report **template**, then switch delivery to
`send_template()`. Start this early — Meta review is measured in days, not minutes.

### 4.4 — Wire an email transport for report schedules (B-P4-08) 🛠️
**State:** `RESEND_API_KEY` already exists in config (used by `auth.py`'s password-reset flow) but
no report mailer is wired — `delivery_channel='email'` returns `status: "unavailable"`.
**Fix (zero new credential — reuses 1.9's neighbor, already in `.env`):** point the report sender
at the same dependency-free Resend HTTP call `auth.py` already uses. This is code-only.

### 4.5 — Decide the PDF story (B-P4-03) 🚦
`GET /reports/{id}/pdf` currently isn't a true PDF — no `reportlab`/`weasyprint` is installed.
**Decision:** add one of those as a dependency, or accept HTML delivery as the permanent answer.

### 4.6 — Backfill real cost data (B-P4-04) 🔑 (falls out of Phase 2)
Every cost figure today is `is_estimated=true`, computed from rate constants — no call has ever
logged real STT seconds/LLM tokens/TTS characters, because Phase 2 never ran. Once 2.1 is live,
backfill `usage_metrics` from real logged usage.

---

## Phase 5 — Deploys & CI go-live

Both items are **procedural, not engineering** — everything code-side has been ready since
wave-2.

### 5.1 — Two Vercel Root Directory clicks 🚦 (closes B-FE1-02, B-FE1-03)
| Project | Current setting | Correct setting |
|---|---|---|
| `agency-dashboard` | Root Directory = `agency-app` (never existed) | `agency-dashboard` |
| `techscapeai-platform` | Root Directory = *(empty)* | `api` |
**Path:** Vercel → each project → Settings → Build & Deployment → Root Directory. Full evidence of
why this is the fix (not Vercel's own suggested `pyproject.toml` route, which was tried and
verified not to work here) is in `scripts/DEPLOY_READINESS.md` and PR comment history.
**Verify:** next push deploys `Ready` on both projects.

### 5.2 — GitHub Actions billing 🚦
**Path:** GitHub → repo Settings → Billing → Actions. Evidence the pipeline itself is not the
problem: identical `ci.yml` passed runs #15–21; every failure since #22 is `runner_id: 0`, ~2s,
zero logs — a runner was never allocated. **Verify:** the next push produces a real (non-2-second)
run; the gating `pytest tests/` (250 tests) and the `Scoreboard Check` job both execute for real.

---

## Phase 6 — Compliance & legal

Detail lives in `COMPLIANCE_CHECKLIST.md`; this is the sequencing.

### 6.1 — Legal review of the consent announcement wording (BLK-8) 🚦
**State:** the *mechanism* is done — `CONSENT_ANNOUNCEMENT` plays before the media stream opens
(`api/app/services/travel/voice.py`), and the disclosure-played event is written to
`travel_call_events` on every call. Only the wording constant itself
(marked `# PENDING LEGAL REVIEW` in the source) needs sign-off, plus Telugu/Hindi translations
keyed to `ai_config.languages`.
**Steps:** legal reviews/approves the English text → translate for te/hi → replace the placeholder
constant → deploy.

### 6.2 — Finalize ToS / Privacy Policy text (Compliance D-1) 🚦
**State:** `docs/legal/TERMS_OF_SERVICE_DRAFT.md` and `PRIVACY_POLICY_DRAFT.md` exist —
structure and every schema-derived fact (data collected, processors used, no-card-data statement,
the erasure endpoint) filled in, loud `[LEGAL TO COMPLETE]` markers everywhere prose is needed.
**Steps:** legal completes the marked sections → publish → point `TermsPage.tsx`'s currently-dead
spans at the real published docs (a one-line change once URLs exist).

### 6.3 — Pick a backup policy (BLK-7) 🚦
**State:** mechanism built — `scripts/backup_db.sh` (parameterized `pg_dump`, retention pruning,
refuses to run without explicit `RETENTION_DAYS`) and `scripts/BACKUP_OPTIONS.md` (the three
options, one line each).
**Steps:** pick **A** (rely on Supabase's own PITR/daily — verify the plan tier includes it),
**B** (nightly `backup_db.sh` + retention N from a machine with DB access), or **C** (both). Then
**run one restore drill** — a policy nobody has restored from is unproven.

### 6.4 — Code-only compliance fixes 🛠️ (see [Phase 9](#phase-9--zero-credential-code-fixes-do-these-anytime))
Two items (B-FE7-04, B-FE7-07) are compliance-adjacent but need no decision at all — moved to
Phase 9 since they're actionable immediately.

---

## Phase 7 — Multi-tenant real test

### 7.1 — Apply the Tenant-B fixture migration to a live DB (B-P5-02) 🔑
Depends on **0.1**. Migration `0018` (synthetic second-agency fixture: real business, branch, 4
role users, a reserved non-dialable phone number, a deliberately different `ai_config`) is written
but never applied to a live database. Apply it, then run `scripts/access_matrix.py` for the real
5-role × 2-tenant sweep.

### 7.2 — 🏢 Plivo Reseller application for a real second tenant (B-P5-03)
**This is not code, and Claude Code must never submit this.** Real KYC, a real contract, a real
Plivo account. Gowtham does this personally when a real second agency is ready to onboard.

### 7.3 — 🏢 Real invoicing / charging a second agency (B-P5-04)
Billing scaffolding (draft invoices, `draft→sent→paid`) is built. **Wiring a real charge is
permanently human-gated** — this gate does not expire even after 7.2 is done. Every real invoice
needs explicit authorization at the time.

---

## Phase 8 — Marketing site (new scope)

### 8.1 — Decide scope (BLK-9) 🚦
`CLAUDE.md`'s design-system section (blue #3D75F3, salmon #F5A086, the `.wrap`/`.btn`/`.card`
conventions) describes a `frontend/` React SPA that **does not exist in this repo** — confirmed,
documented with a READ-FIRST banner (RISK-2, closed 2026-08-09). Building it is new scope, not a
gap in existing scope.
**Decision needed:** does Gowtham want it built here, or does it already live in another repo?
If building: supply requirements (the design tokens already exist in `CLAUDE.md` as a starting
point) and this becomes its own phase-0-to-done project, not a line item.

---

## Phase 9 — Zero-credential code fixes (do these anytime)

Neither of these needs a credential or a decision. They can be done in the next available session.

### 9.1 — Stop echoing the plaintext password in 422 responses (B-FE7-04) 🛠️
**State (verified against the live code, not just the ledger):** no `RequestValidationError`
handler exists in `api/app/main.py` — FastAPI's default handler is active, and it echoes the raw
submitted value under `detail[].input`. Captured live: registering with `password123` returns
`{"loc":["body","user_password"],...,"input":"password123"}` verbatim. Any client logger, proxy
log, or error-tracking transport (BLK-6, once live) that records response bodies now holds real
passwords.
**Fix:** add `from fastapi.exceptions import RequestValidationError` and an
`@app.exception_handler(RequestValidationError)` in `api/app/main.py` (near the existing global
handler at line 102) that strips `input` and `ctx` from every error dict — or at minimum from any
field matching `*password*` — before returning. The frontends already only render `msg` (fixed in
DEBT-19), so this closes the wire-level leak without touching either client.

### 9.2 — Require a verified-OTP token at registration (B-FE7-07) 🛠️
**State:** `RegisterBusinessIn` has no OTP field; `register_business` performs no OTP check, so
account creation succeeds against a never-verified email address regardless of what the client
does. `customer-app` gates the *screen* on `otpVerified` (`features/onboarding/RequireStep.tsx`),
but that's `localStorage` — trivially bypassable by anyone who skips the UI and calls the endpoint
directly.
**Fix:** have `POST /auth/otp/verify` (or an equivalent) return a short-lived verification token;
require that token as a field on `POST /auth/register-business`; reject registration without a
valid one. This is the guarantee the frontend gate currently only pretends to be.

---

## Phase 10 — Technical debt backlog (non-blocking)

Real, tracked, does **not** block go-live. Burn down opportunistically.

| ID | One-line fix |
|---|---|
| B-P3-07 | Local dev only (not this sandbox, not production): `colima start && supabase start -x vector,logflare` before running regression checks against a local stack |
| DEBT-08 | `WebSocketDisconnect` on the media-stream handler discards all buffered audio and marks the call `failed` — run the same stop-handler path on disconnect so an abrupt hangup (common on mobile) doesn't lose the whole call's data |
| DEBT-09 | Keyword matching uses unanchored substrings (`"may"` fires on *maybe*) — switch to `\b`-bounded regex |
| DEBT-10 | WhatsApp 24h session-window state lives in an in-process dict — persist to Postgres/Redis so it's correct under multiple workers |
| DEBT-11 | `fx_rate_at()` returning NULL pre-snapshot is correct, but nothing forces callers to handle it — make the rollup endpoint fail loudly instead of silently dropping rows |
| DEBT-12 | Recorded intentionally: Plivo verifier fails OPEN when unset, Razorpay fails CLOSED — if ever "unified", go closed, never open |
| DEBT-13 | `TakeoverState` duplicated in `types/ws.ts` and `types/travel.ts` — pick one home, re-export |
| DEBT-14 | *(Already fixed — `vite.config.ts` `/ws` proxy entry added.)* |
| DEBT-15 | Five spec'd WS message types are never emitted — see [2.6](#26--fix-the-ws-contract-drift-before-any-dashboard-is-built-against-it-debt-05-) |
| DEBT-17 | `customer-app` and `agency-dashboard` use different localStorage key names for tokens — namespace both before ever co-hosting |
| B-P3-08 | Root `.env.example` is missing 14 fields `api/.env.example` already has (incl. `REDIS_URL`) — sync it |
| B-SPRINT2B-02 | `fastembed`'s model can't download in this sandbox (proxy blocks `huggingface.co`) — pre-bake the ONNX weights into the sandbox image, or allowlist the host |

---

## Reference: blocker index

Every ID mentioned above, one line, cross-referenced to `BLOCKERS.md` for full detail. **IDs are
listed individually, never as a range or slash-join** — `scripts/check_roadmap_updated.sh`'s
orphan check parses this table literally, and a shorthand like `B-P2-01…06` hides four IDs from it.
Every active (non-RESOLVED) ID in `BLOCKERS.md` must appear somewhere in this file.

| ID | Phase | What it is |
|---|---|---|
| BLK-1 | 1.1, 2.1 | No Plivo credentials |
| BLK-2 | 1.5, 3 | No Supabase service-role key |
| BLK-3 | 0.1, 3 | Sandbox network policy blocks supabase.co (environment, not Gowtham) |
| BLK-4 | 5.1 | Two Vercel Root Directory settings |
| BLK-5 | 5.2 | GitHub Actions billing |
| BLK-6 | 1.9 | No SENTRY_DSN |
| BLK-7 | 6.3 | Backup policy undecided |
| BLK-8 | 6.1 | Consent wording legal review |
| BLK-9 | 8.1 | Marketing site scope |
| B-P2-01 | 1.1 | Plivo credentials (voice pipeline) |
| B-P2-02 | 2.1 | Live media stream + TTS full loop |
| B-P2-03 | 1.2 | Deepgram/Sarvam STT credentials |
| B-P2-04 | 1.3 | Anthropic credential |
| B-P2-05 | 1.4 | ElevenLabs TTS credential |
| B-P2-06 | 1.6 | JTI blacklist in-memory — needs Redis |
| B-P2B-01 | 2 | Phase 2B (the MPC leg) never ran |
| B-P3-01 | 2.3 | Supervisor live monitor/barge/takeover/release |
| B-P3-02 | 1.3 | Claude-powered real-time suggestions |
| B-P3-03 | 1.3 | Claude Sonnet post-call summary |
| B-P3-04 | 1.6 | Multi-worker call_feed/JTI — needs Redis |
| B-P3-05 | 2.4 | Telugu STT/TTS path |
| B-P3-06 | 2.5 | Per-participant recording URL |
| B-P3-07 | 10 | Local Colima/Supabase stack for local dev |
| B-P3-08 | 10 | Root `.env.example` missing 14 fields |
| B-P4-01 | 1.7, 4.1 | Razorpay credentials + one human-confirmed real link |
| B-P4-02 | 1.8, 4.2 | WhatsApp credentials + one human-confirmed real send |
| B-P4-03 | 4.5 | PDF rendering library decision |
| B-P4-04 | 4.6 | Real cost data (falls out of Phase 2) |
| B-P4-05 | 1.3 | Report quality bounded by stub post-call pipeline |
| B-P4-06 | 3.2 | Cross-phase access-matrix sweep needs a live DB |
| B-P4-07 | 4.3 | Meta template approval for scheduled reports |
| B-P4-08 | 4.4 | Email transport for report schedules |
| B-P5-01 | 7.1 | Tenant-B fixture (designed approach, not a workaround) |
| B-P5-02 | 7.1 | Tenant-B migration `0018` not applied live |
| B-P5-03 | 7.2 | 🏢 Plivo Reseller application |
| B-P5-04 | 7.3 | 🏢 Real invoicing of a second agency |
| B-FE1-02 | 5.1 | Vercel Root Directory — agency-dashboard |
| B-FE1-03 | 5.1 | Vercel Root Directory — techscapeai-platform |
| B-FE7-01 | 3.3 (note) | Agency-self-serve-vs-traveller-facing — answered in practice by B-FE7-02/03, ledger row stale |
| B-FE7-04 | 9.1 | Password echoed in 422 — code-only fix |
| B-FE7-07 | 9.2 | No verified-OTP requirement at registration — code-only fix |
| B-FE7-08 | 3.3 | Multi-agency traveller lookup decision |
| B-SPRINT2B-01 | 0.1 | Supabase access unavailable from this sandbox |
| B-SPRINT2B-02 | 10 | fastembed model can't download in this sandbox |
| DEBT-01 | 2.2 | Latency headroom decision (inline vs. async) |
| DEBT-02 | 1.6 | In-memory JTI blacklist — needs Redis |
| DEBT-04 | 2.1 (note) | Superseded by DEBT-20 (resolved), ledger row stale |
| DEBT-05 | 2.6 | WS contract drift vs. api-conventions.md |
| DEBT-06 | 2.7 | Fire-and-forget task leak in schedule() |
| DEBT-07 | 1.3 | Sentiment score is a clamped-constant EMA |
| DEBT-08 | 10 | Abrupt hangup discards buffered audio |
| DEBT-09 | 10 | Unanchored keyword substring matching |
| DEBT-10 | 10 | WhatsApp session-window state not shared across workers |
| DEBT-11 | 10 | `fx_rate_at()` NULL not enforced on callers |
| DEBT-12 | 10 | Recorded intentionally — do not "fix" the Plivo/Razorpay fail-open/closed asymmetry |
| DEBT-13 | 10 | `TakeoverState` duplicated in two type files |
| DEBT-15 | 2.6 | Five spec'd WS message types never emitted |
| DEBT-17 | 10 | Divergent localStorage token key names across apps |

---

## Keeping this in sync

This file is a **sequencing view**, not a scoreboard — it does not carry percentages and is not
subject to the `gogaga-scoreboard` skill's per-commit update rule. When a phase item closes:
1. Flip its status in `BLOCKERS.md` (the ID's row).
2. If it moves a scored area, update `GOGAGA_ANALYSIS_REPORT.md` in the same commit (the skill
   enforces this for scoring-relevant paths).
3. Strike the line here or move it to a "Closed" section — this file should always show the
   **current** shortest path to 100% live, not a history of what used to block it.

**This is now partly automated.** A weekly Routine (`trig_01HDAtTFMngH7VvzkD8nkiqW`, Mondays
03:00 UTC, documented in `CLAUDE.md`) runs exactly this sweep — audits the codebase for genuinely
new stubs/gaps, and if it finds one, performs steps 1–2 above itself before pushing. It does not
replace an in-session update when a session resolves something directly; it exists to catch drift
between sessions.

---

## Closed this phase (Phase 9-shaped: zero-credential work, log kept per the skill's convention)

- **2026-08-10 — Installed the `gogaga-golive-roadmap` skill.** Self-maintenance mechanism for
  this file, mirroring `gogaga-scoreboard`'s discipline. Included a real orphan sweep on install
  (`scripts/check_roadmap_orphans.py`), which found and fixed two classes of drift that predated
  the skill: (a) `BLK-1`–`BLK-5` were referenced throughout this file and
  `GOGAGA_ANALYSIS_REPORT.md` but had no row in `BLOCKERS.md` — added; (b) 12 active blockers
  (`B-FE1-03`, `B-FE7-01`, `B-P2-02`, `B-P2-06`, `B-P3-03`, `B-P3-04`, `B-P3-07`, `B-P4-05`,
  `B-P4-06`, `DEBT-02`, `DEBT-04`, `DEBT-08`) were hidden from this file by compact range/slash
  notation (`B-P2-01…06`, `B-FE1-02/03`) in the old reference index — expanded every ID
  individually and placed each in its real dependency phase. Also surfaced two ledger rows that
  are stale (`B-FE7-01` and `DEBT-04` describe work later resolved under `B-FE7-02`/`B-FE7-03` and
  `DEBT-20` respectively, but their own status cells were never flipped) — noted in-line at 3.3
  and 2.1 rather than silently edited, since correcting `BLOCKERS.md` itself is that file's own
  maintenance, not this skill's.
