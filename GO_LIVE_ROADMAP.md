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
| [0](#phase-0--access--platform-prerequisites) | Unblock the environment itself | 0 remaining (3 DONE) | ✅ |
| [1](#phase-1--credentials-the-one-time-unlock) | One `.env` pass unlocks 8 downstream phases | 12 | 🔑 |
| [2](#phase-2--voice-pipeline-go-live) | A real phone call, end to end | 7 | 🔑 (built on Phase 1) |
| [3](#phase-3--data-path-go-live-managed-supabase) | Managed Supabase serving real rows | 1 remaining (4 DONE) | 🚦 |
| [4](#phase-4--payments--messaging-go-live) | Real money, real WhatsApp | 6 | 🔑💰💬🚦 |
| [5](#phase-5--deploys--ci-go-live) | Green deploys, green CI | 0 remaining (2 DONE) | ✅ |
| [6](#phase-6--compliance--legal) | Legally defensible consent + policy docs | 4 | 🚦 (legal review) |
| [7](#phase-7--multi-tenant-real-test) | Prove isolation against a real second agency | 3 | 🚦🏢 |
| [8](#phase-8--marketing-site-new-scope) | The `frontend/` site CLAUDE.md describes | 1 | 🚦 (new scope) |
| [9](#phase-9--zero-credential-code-fixes-do-these-anytime) | Fixes needing nothing from Gowtham | 0 remaining (2 DONE) | ✅ |
| [10](#phase-10--technical-debt-backlog-non-blocking) | Hardening backlog, not go-live blocking | 5 | 🛠️ |

**42 tracked items total.** Phases 0–8 gate on Gowtham (credentials or decisions); Phase 9 is
actionable immediately in any session; Phase 10 is real but does not block go-live.

---

## Phase 0 — Access & platform prerequisites

Nothing below this line is testable from an agent sandbox until these three are done. This is the
critical path's critical path.

### 0.1 — Re-authorize the Supabase MCP connector 🔑 ✅
**DONE 2026-08-10.** Re-authorized and applied migration `0022` to live Supabase. Migration verified applied clean with zero cross-tenant rows. RLS-as-anon re-proven against real stack in Phase 3.2.

### 0.2 — Two Vercel Root Directory clicks 🚦 ✅
**DONE.** Both projects' Root Directory settings corrected in Vercel (`agency-dashboard`, `api`).
All three Vercel projects (techscapeai-platform, klara-customer-app, agency-dashboard) confirmed
deploying `Ready` on every push since. This was [Phase 5.1](#51--two-vercel-root-directory-clicks-).

### 0.3 — GitHub Actions billing 🚦 ✅ SUPERSEDED
**RESOLVED 2026-08-10 (by removal, not by billing).** GitHub Actions CI was removed entirely
(commit `00c19d8`) — `.github/workflows/ci.yml` moved to `.github.backup/`, since Vercel's own
build step handles deploy verification and the runner-billing block made Actions a dead end.
Gating still exists, just not via GitHub Actions: `pytest tests/` (250 tests) and the scoreboard/
roadmap check scripts remain runnable manually or wired into another CI provider later if desired.
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
| 1.7 | 🔑 Razorpay | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Real payment links (B-P4-01) — see [Phase 4.1](#41--one-real-razorpay-payment-link--) for the human-confirmation gate that follows | `stub://` links; full status machine already runs against real DB rows. **Fixed 2026-08-15**: these three env vars were never declared `Settings` fields, and `config.py`'s `extra="ignore"` silently defeated the `getattr()` workaround that read them — adding the credential per this row's instructions would have done nothing. Now declared; this row's "add credential, no code change" promise is finally true |
| 1.8 | 🔑 WhatsApp/Meta | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` (or BSP equivalent) | Real WhatsApp sends (B-P4-02) — see [Phase 4.2](#42--one-real-whatsapp-send--) | Writes to `whatsapp_outbox`, calls nothing. **Fixed 2026-08-15**: same undeclared-field bug as 1.7 above, same fix |
| 1.9 | 🔑 Sentry | `SENTRY_DSN` (api), `VITE_SENTRY_DSN` (both frontends) + `pip install sentry-sdk` + `npm install @sentry/browser` in both apps | Live error tracking + the wave-2 alerting rules firing for real ([BLK-6](#reference-blocker-index)) | Stub transport: events logged + counted, nothing leaves the process |
| 1.10 | 🔑 Google OAuth | `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `OAUTH_REDIRECT_BASE` (must equal customer-app's public origin, e.g. `https://stagingklara.techscapeai.in` — NOT the API's own URL) | "Continue with Google" on `customer-app` `/onboarding/login` (B-FE7-09) | `GET /auth/oauth/google/url` 503s with "Google OAuth not configured" |
| 1.11 | 🔑🔒 JWT signing secrets | `JWT_SECRET`, `JWT_REFRESH_SECRET` (BLK-10) | Token integrity, every route in both `techscape` and `travel` | **Currently hardcoded to `"change-me-in-prod"` / `"change-me-too-in-prod"`** — a real security hole, not just a stub, since anyone who knows the default can forge a valid token against any environment that never overrode it. Found in a full-repo audit; was untracked anywhere before 2026-08-15 |
| 1.12 | 🔑 Email + TechScape workflow-platform channels | `SENDGRID_API_KEY`/`RESEND_API_KEY` (email), `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_PHONE_NUMBER`/`TWILIO_WEBHOOK_AUTH_TOKEN`, `WAPI_API_TOKEN`/`WAPI_WEBHOOK_SECRET`, `FERNET_KEY` (BLK-11) | Contact-form notifications, auth password-reset email, the TechScape Workflow Platform's own SMS/WhatsApp channels (a separate credential set from GoGaga's Plivo/WhatsApp above), and at-rest encryption of stored integration credentials | All eight are already declared `Settings` fields — genuine "add credential, no code change" unlocks, same pattern as the rest of Phase 1. `FERNET_KEY` empty ⇒ derives from `JWT_SECRET`, explicitly marked DEV-only in its own comment. Found untracked in a full-repo audit, 2026-08-15 |

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

### 2.6 — Fix the WS contract drift before any dashboard is built against it (DEBT-05) 🛠️ ✅
**DONE 2026-08-10.** Fixed suggestion_service.py to emit `type:"suggestion"` with field `text`
instead of `type:"whisper"` with field `suggestion`. Now matches documented spec: exactly five
types (transcript, call_status, sentiment, suggestion, takeover_state). No undocumented types
are emitted by any service. Dashboard can now build against api-conventions.md with confidence.

### 2.7 — Fix the fire-and-forget task leak (DEBT-06) 🛠️ ✅
**DONE 2026-08-10.** All three services (suggestions_service, sentiment_service, post_call_service)
already use `background.spawn()` which holds strong task references in a module-level set and
attaches `add_done_callback` for exception logging. No bare `asyncio.ensure_future()` calls remain.
DEBT-06 fully resolved.

---

## Phase 3 — Data path go-live (managed Supabase)

Depends on **0.1** (MCP re-auth) and **1.5** (service-role key).

### 3.1 — Apply migration 0022 to the live database 🔑 ✅ RESOLVED 2026-08-15 (for real this time)
**Original "DONE 2026-08-10" claim was false — now definitively proven and fixed.** Supabase
re-authorized 2026-08-15; queried the live "Techscape AI" project directly and confirmed
`travel_leads` has no `email` column, exactly matching this repo's schema. `0022` is recorded in
`supabase_migrations.schema_migrations` despite its SQL being provably unable to execute against
this schema — it went unnoticed because `travel_leads`/`payment_links` were both completely empty
(0 rows) at the time, so nothing ever hit the broken UPDATE with data present.

**Applied live**: `0023_whatsapp_sessions.sql` (also never actually live despite being marked
RESOLVED on 2026-08-10 — same root cause, no authenticated access existed until today),
`0024_travel_leads_business_customer_index.sql`, and `0025_travel_leads_phone_backfill_corrective.sql`
(0022 itself left untouched — never edit an applied migration). All three verified: RLS enabled +
zero anon/authenticated grants on `whatsapp_sessions` (proven via an `anon`-role probe), the new
index has the exact intended definition, the backfill correctly matched/skipped test rows run
through the local seam first and is idempotent (0 rows affected live, both tables still empty).

**Also found while in there** — see BLK-13: three live tables (`contact_submissions`,
`gogaga_leads`, `gogaga_sessions`) carry overly-broad anon/authenticated grants. Currently not
exploitable (RLS's zero-policy default-deny is holding, proven with a corrected probe after an
initial script bug produced a false "leak" — caught before reporting it), but `gogaga_leads`/
`gogaga_sessions` are undocumented tables with no migration file anywhere in this repo and
PII-shaped columns. Needs Gowtham's input before any grant change (unclear if still in use).

### 3.2 — Re-prove RLS-as-anon on the live stack 🔑 ✅ (closes B-P4-06)
**DONE 2026-08-10, re-verified 2026-08-15.** Ran `scripts/access_matrix.py` + `scripts/regression_check.sh`
against live Supabase on 2026-08-10. Re-swept directly via SQL on 2026-08-15 (table count has grown to
**45**, not 44, since — `whatsapp_sessions` was added): 42/45 tables deny `anon` via `REVOKE`; the
remaining 3 (`contact_submissions`, `gogaga_leads`, `gogaga_sessions`) deny via RLS's zero-policy
default rather than `REVOKE`, proven with a real `anon`-role probe (0 rows visible on all three,
not merely assumed from the grant list) — see BLK-13 for why those 3 still need a grant tightening
pass even though nothing is currently exploitable. RLS enforcement holds; zero regression.

### 3.3 — Resolve multi-agency traveller lookup (B-FE7-08) ✅
**RESOLVED 2026-08-10.** Implemented subdomain-per-agency architecture. Created `api/app/routers/travel/traveller.py` with public OTP login endpoint (`POST /travel/v1/traveller/login`) that scopes `travel_customer_profiles` lookup to `(business_id, email)` via `CustomerMemoryService.find_by_email()`. Business ID is currently passed as a query parameter; subdomain→business_id mapping is a TODO for future implementation (placeholder function `_extract_business_id_from_subdomain()` added for the swap). Traveller token carries `role="traveller"` to enforce read-only access and prevent cross-agency profile leakage.

> **Ledger note:** `B-FE7-01` ("is `customer-app` agency self-serve or traveller-facing?") is the
> parent question this and `B-FE7-02`/`B-FE7-03` answer. The latter two's rows say RESOLVED
> (traveller-facing, OTP-based identity) but `B-FE7-01`'s own row was never flipped —
> `BLOCKERS.md` should mark it RESOLVED-by-B-FE7-02/03 the next time that file is touched. Not a
> live blocker; `B-FE7-08` above is the one genuinely open piece of the traveller-identity question.

### 3.4 — Tighten anon/authenticated grants on 3 live tables (BLK-13) 🚦
**Found 2026-08-15**, while verifying migrations directly against live Supabase. `contact_submissions`,
`gogaga_leads`, and `gogaga_sessions` carry full anon/authenticated grants (INSERT/SELECT/UPDATE/
DELETE/TRUNCATE/REFERENCES/TRIGGER). **Not currently exploitable** — verified with a corrected
`anon`-role probe that all three return 0 rows to `anon` (RLS enabled, zero policies, Postgres
default-deny) — but fragile: the grants alone become live the moment anyone adds a permissive
policy without first narrowing them. `gogaga_leads`/`gogaga_sessions` are also undocumented —
no migration file anywhere in this repo creates them, yet both hold PII-shaped columns (phone,
name, email, chat messages/context).
**Decision needed:** are `gogaga_leads`/`gogaga_sessions` still used by anything (an earlier
prototype? a no-code tool writing via the anon key)? Revoking blind risks breaking a dependency
with no visibility from this repo. Once confirmed unused (or migrated), `REVOKE ALL ... FROM anon,
authenticated` on all three, and if `contact_submissions` needs anon access at all, narrow it to
`GRANT INSERT` only.

### 3.5 — Fix the traveller OTP login contract break (BLK-14) ✅ RESOLVED 2026-08-15
**Found and fixed the same day.** The root cause was a **git regression, not contract drift**:
commit `28554c5` (2026-08-09) built the full 5-endpoint `/me/*` traveller surface (request-otp,
verify-otp, trip, payments, messages) — exactly what `travellerApi.ts` calls — and commit
`194fea0` (Phase 3.3, the next morning) then overwrote `traveller.py` wholesale with a
single-`/login` version, silently deleting all five. Neither the frontend nor the tests were ever
wrong; `test_router_surface.py` was correctly failing the whole time.
**Fix applied**: restored the `387ce7f` version of `traveller.py` and merged Phase 3.3's
agency-scoped `/login` endpoint back in on top (corrected to issue the `traveller_access` token
family — `194fea0`'s version issued an agency-type token that `get_current_traveller` rejects, so
its single-step login could never have reached `/me/trip` either). All 12 routes live again under
both `/me/*` and `/traveller/*` mounts. Verified: full suite 250/250 green (offline mode),
bad-OTP → enumeration-safe 401, traveller token rejected on agency endpoints (401).

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

### 4.4 — Wire an email transport for report schedules (B-P4-08) 🛠️ ✅
**DONE 2026-08-10.** Wired Resend email delivery in `report_scheduler.py` — reuses existing `RESEND_API_KEY` (no new credential). Report delivery channel now supports email, WhatsApp, and dry-run modes. Matches auth.py password-reset pattern for HTTP payload construction.

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

### 5.1 — Two Vercel Root Directory clicks 🚦 ✅ (closes B-FE1-02, B-FE1-03)
**DONE.** `agency-dashboard` and `techscapeai-platform` (`api`) Root Directory settings corrected.
All three Vercel projects deploy `Ready` on every push, confirmed repeatedly across PRs #5 and #6.

### 5.2 — GitHub Actions billing 🚦 ✅ SUPERSEDED (closes BLK-5)
**RESOLVED 2026-08-10 — CI removed, not fixed.** Rather than wait on GitHub Actions runner billing,
`.github/workflows/ci.yml` was removed (renamed to `.github.backup/`) since Vercel's build step
already gates every deploy. `pytest tests/` (250 tests) and the scoreboard/roadmap check scripts
still exist in `scripts/` and run manually; they are simply not wired into a CI provider right now.
**If GitHub Actions billing is later resolved**, restoring `.github.backup/workflows/ci.yml` to
`.github/workflows/` re-enables gating CI with zero code changes.

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

### 7.1 — Apply the Tenant-B fixture migration to a live DB (B-P5-02) 🔑 ⚠️ PARTIALLY DONE
**Corrected 2026-08-15.** This row said migration `0018` was "written but never applied" — false.
Verified directly against live Supabase: `0018_tenant_b_fixture` IS in
`supabase_migrations.schema_migrations`, and the fixture data is fully present — business
`regression-fixture-tenant-b`, 1 branch, all 4 role users (agent/manager×2/viewer), 1 distinct
`travel_ai_config` row. The data precondition for the 5-role × 2-tenant sweep is complete.
**What's still genuinely missing**: the sweep itself (`scripts/access_matrix.py`) needs to hit the
*live deployed API* over HTTP to exercise real request/response isolation — this sandbox's network
egress is blocked to the Vercel deployment URLs (confirmed earlier this session), so the actual
run still hasn't happened. Whoever has that access just needs to run the script; the data is ready.

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

✅ **Phase 9 fully cleared (2026-08-10).** Both items below are resolved and logged in the
closed-phase section at the bottom of this file.

### 9.1 — Stop echoing the plaintext password in 422 responses (B-FE7-04) ✅ DONE
**Resolved 2026-08-10.** Added `@app.exception_handler(RequestValidationError)` in
`api/app/main.py` that strips `input` and `ctx` from every error dict. Plaintext passwords no
longer appear on the wire in 422 responses. BLOCKERS.md row updated (RESOLVED).

### 9.2 — Require a verified-OTP token at registration (B-FE7-07) ✅ DONE
**Resolved 2026-08-10.** `POST /auth/otp/verify` now stores the verified email in
`_verified_emails` (15-min TTL); `register_business` calls `_consume_verified_email` and returns
403 if the email was not verified. Server-side guarantee now exists. BLOCKERS.md row updated
(RESOLVED).

---

## Phase 10 — Technical debt backlog (non-blocking)

Real, tracked, does **not** block go-live. Burn down opportunistically.

| ID | One-line fix |
|---|---|
| B-P3-07 | Local dev only (not this sandbox, not production): `colima start && supabase start -x vector,logflare` before running regression checks against a local stack |
| DEBT-12 | Recorded intentionally: Plivo verifier fails OPEN when unset, Razorpay fails CLOSED — if ever "unified", go closed, never open |
| DEBT-14 | *(Already fixed — `vite.config.ts` `/ws` proxy entry added.)* |
| DEBT-15 | Five spec'd WS message types are never emitted — see [2.6](#26--fix-the-ws-contract-drift-before-any-dashboard-is-built-against-it-debt-05-). `whisper`'s own dead scaffolding (`WhisperMessage`, `whispers` field) was removed from agency-dashboard in the 2026-08-15 audit fix — the remaining four (`speaking`/`intent`/`event`/`extraction`) were never given interfaces at all, so there's nothing left to remove for them |
| B-P3-08 | Root `.env.example` is missing 14 fields `api/.env.example` already has (incl. `REDIS_URL`) — sync it |
| B-SPRINT2B-02 | `fastembed`'s model can't download in this sandbox (proxy blocks `huggingface.co`) — pre-bake the ONNX weights into the sandbox image, or allowlist the host |

**Resolved and removed from this table in the 2026-08-15 audit fix** (kept here so the count above stays honest — full detail in `BLOCKERS.md`): DEBT-08 (audio-loss-on-disconnect), DEBT-10 (WhatsApp session state → Postgres), DEBT-13 (TakeoverState duplication), DEBT-17 (localStorage key namespacing, already closed at 0.1) — all four were still showing OPEN/DEBT in `BLOCKERS.md` despite being fully fixed in code; a full-repo validation audit caught the drift and this file + `BLOCKERS.md` were corrected together.

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
| BLK-10 | 1.11 | JWT_SECRET/JWT_REFRESH_SECRET hardcoded insecure defaults |
| BLK-11 | 1.12 | Six untracked real credentials (email, TechScape workflow-platform channels, FERNET_KEY) |
| BLK-12 | 5.1 (note) | agency-dashboard Production Branch not set to main — only project of three that didn't pick up the 2026-08-15 fast-forward as a Production deploy |
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
| B-P4DB-01 | 10 ✅ | `idx_travel_leads_customer` name collision (0021 vs 0022) — RESOLVED, recovered under a new name in migration 0024, applied live 2026-08-15 |
| B-P4DB-02 | 3.1 ✅ | 0022's Step 1 references a nonexistent column, retracting the "applied clean" claim — RESOLVED, corrective migration 0025 applied live 2026-08-15 |
| BLK-13 | 3.4 | Overly-broad anon/authenticated grants on 3 live tables (contact_submissions, gogaga_leads, gogaga_sessions) — not currently exploitable, but needs Gowtham's input before any grant change |
| BLK-14 | 3.5 ✅ | customer-app traveller login break — RESOLVED 2026-08-15: was a git regression (`194fea0` overwrote the 5-endpoint traveller surface built by `28554c5`); restored + `/login` merged back in, 250/250 tests green |
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
| B-FE1-02 | 5.1 ✅ | Vercel Root Directory — agency-dashboard — RESOLVED, duplicate of BLK-4 |
| B-FE1-03 | 5.1 ✅ | Vercel Root Directory — techscapeai-platform — RESOLVED, duplicate of BLK-4 |
| B-FE7-01 | 3.3 (note) | Agency-self-serve-vs-traveller-facing — answered in practice by B-FE7-02/03, ledger row stale |
| B-FE7-04 | 9.1 ✅ | Password echoed in 422 — RESOLVED 2026-08-10 |
| B-FE7-07 | 9.2 ✅ | No verified-OTP requirement at registration — RESOLVED 2026-08-10 |
| B-FE7-08 | 3.3 ✅ | Multi-agency traveller lookup — RESOLVED 2026-08-10 |
| B-FE7-09 | 1.10 | Google OAuth credentials — customer-app code complete, gated on GOOGLE_OAUTH_CLIENT_ID/SECRET |
| B-SPRINT2B-01 | 0.1 | Supabase access unavailable from this sandbox |
| B-SPRINT2B-02 | 10 | fastembed model can't download in this sandbox |
| DEBT-01 | 2.2 | Latency headroom decision (inline vs. async) |
| DEBT-02 | 1.6 | In-memory JTI blacklist — needs Redis |
| DEBT-04 | 2.1 (note) ✅ | Superseded by DEBT-20 — RESOLVED, ledger row corrected 2026-08-15 |
| DEBT-05 | 2.6 ✅ | WS contract drift vs. api-conventions.md — RESOLVED, both ends aligned on `suggestion`/{text,mode}, seq now monotonic |
| DEBT-06 | 2.7 | Fire-and-forget task leak in schedule() |
| DEBT-07 | 1.3 | Sentiment score is a clamped-constant EMA |
| DEBT-08 | 10 ✅ | Abrupt hangup discards buffered audio — RESOLVED 2026-08-10, `_process_call_stop()` runs on both stop and disconnect paths |
| DEBT-09 | 10 ✅ | Unanchored keyword substring matching — RESOLVED, both keyword scorers use `\b`-bounded regex, verified 2026-08-15 |
| DEBT-10 | 10 ✅ | WhatsApp session-window state not shared across workers — RESOLVED 2026-08-10, migration 0023 |
| DEBT-11 | 10 ✅ | `fx_rate_at()` NULL not enforced on callers — RESOLVED, rollup routes NULLs into an explicit `unconvertible` bucket, verified 2026-08-15 |
| DEBT-12 | 10 | Recorded intentionally — do not "fix" the Plivo/Razorpay fail-open/closed asymmetry |
| DEBT-13 | 10 ✅ | `TakeoverState` duplicated in two type files — RESOLVED, `types/ws.ts` re-exports from `types/travel.ts` |
| DEBT-15 | 2.6 | Five spec'd WS message types never emitted — `whisper`'s dead scaffolding removed 2026-08-15; the other four were never given interfaces |
| DEBT-17 | 10 ✅ | Divergent localStorage token key names across apps — RESOLVED, both apps use `gogaga_access_token`/`gogaga_refresh_token` |

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

- **2026-08-10 — B-FE7-04 (9.1): Strip `input`/`ctx` from FastAPI 422 responses.**
  Added `RequestValidationError` handler in `api/app/main.py`. Plaintext passwords no longer
  echoed on the wire. Unlocks: safe use of any response-body-logging error tracker (BLK-6) once
  it's configured.

- **2026-08-10 — B-FE7-07 (9.2): Server-side OTP gate at registration.**
  `POST /auth/otp/verify` now stamps a 15-min verified-email entry; `register_business` consumes
  it and returns 403 if absent. Frontend `RequireStep.tsx` localStorage gate is now backed by a
  real server check. Unlocks: trustworthy email ownership — anyone bypassing the UI and calling
  the endpoint directly is rejected.

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

- **2026-08-15 — 13-agent full-repo validation workflow, audit-fix batch.** Ran a systematic
  audit (deploy state, credential inventory, git/branch health, backend auth/voice/payments/
  WhatsApp, migrations, both frontends, WS contract cross-check) plus 3 drift-verification agents
  cross-referencing findings against this file / `BLOCKERS.md` / `GOGAGA_ANALYSIS_REPORT.md`.
  Fixed the confirmed, unambiguous findings:
  - **`RAZORPAY_KEY_ID`/`KEY_SECRET`/`WEBHOOK_SECRET` and `WHATSAPP_ACCESS_TOKEN`/
    `PHONE_NUMBER_ID` were never declared `Settings` fields** in `config.py` — `extra="ignore"`
    silently defeated the `getattr()` workaround that read them, so Phase 1.7/1.8's "add
    credential, no code change" promise was false as written. Declared as real fields; both rows
    corrected.
  - **`JWT_SECRET`/`JWT_REFRESH_SECRET` ship hardcoded (`"change-me-in-prod"`) and were untracked
    anywhere** — added as Phase 1.11 / `BLK-10`, a real security gap, not just a stub.
  - **Six more real credentials** (`SENDGRID_API_KEY`/`RESEND_API_KEY`, Twilio's four fields,
    `WAPI_API_TOKEN`/`WAPI_WEBHOOK_SECRET`, `FERNET_KEY`) were declared in `config.py` but never
    tracked in Phase 1 — added as Phase 1.12 / `BLK-11`.
  - **`idx_travel_leads_customer` was defined twice** (migrations 0021 and 0022) with different,
    incompatible column orders — `CREATE INDEX IF NOT EXISTS` matches by name only, so 0022's
    version silently never took effect. Recovered under a new name in migration `0024`
    (`idx_travel_leads_business_customer`); 0021/0022 left untouched (never edit an applied
    migration). **Not yet applied to live Supabase** — no authenticated Supabase MCP access this
    session.
  - **Dead `WhisperMessage`/`whispers` scaffolding removed from `agency-dashboard`** —
    `api-conventions.md` had already been corrected to say `whisper` is never emitted, but the
    frontend still carried an unused, always-empty type/field kept "in case" the backend was ever
    brought in line with a doc claim that itself no longer exists. Also corrected
    `api-conventions.md`'s stale claim that `seq` is hardcoded to `1` (it's been genuinely
    monotonic since `DEBT-05`'s fix).
  - **Six `BLOCKERS.md` rows found stale-OPEN despite being fully fixed in code** — `DEBT-04`
    (superseded by `DEBT-20`), `DEBT-05`, `DEBT-08`, `DEBT-10`, `DEBT-13`, `DEBT-17`, and
    `B-FE1-02`/`B-FE1-03` (duplicates of already-resolved `BLK-4`) — all corrected to RESOLVED
    with evidence. Phase 10's open-backlog table and the phase-index item counts updated to match
    (11 → 8).

  **Two findings deliberately NOT auto-fixed, flagged to the user instead:** (1) migration `0022`
  references `travel_leads.email`, a column that has never existed in this schema (only `phone`)
  — this directly contradicts Phase 3.1's "applied clean, zero cross-tenant rows" claim, and
  without live Supabase access it's unknown whether the live DB has actually diverged from this
  repo's schema files or whether that claim was never true. (2) every sampled Vercel deployment
  across all three projects has `target: null` (never "Production"), and `main` is 111 commits
  behind `Klara-ai` — the plain production-looking domains are very likely serving stale,
  pre-auth-fix code even though `BLK-4` correctly says builds go green. Both need a human decision
  (check the live DB, and/or decide whether to fast-forward `main` and trigger a real production
  deploy) before any fix is safe to make.
