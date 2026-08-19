# Onboarding Scheduler — Issues, Blockers & Errors

**Repo:** advertsocialai/techscapeai-platform · **Branch:** `Klara-ai` · **Last updated:** 2026-08-19
**Build status:** Phase 0 (discovery complete — implementation NOT started, awaiting approval)

| Severity | Meaning |
|---|---|
| 🔴 Blocker | Implementation cannot proceed, or shipping this would break production. |
| 🟠 High | Real defect or data-integrity risk. Must fix before launch. |
| 🟡 Medium | Degrades reliability or UX. Fix soon. |
| 🔵 Low | Hygiene or tech debt. |

## Summary

| ID | Sev | Title | Area | Status |
|---|---|---|---|---|
| SCH-01 | 🔴 | No server-side record of an incomplete onboarding — 4 of 6 requested steps have nothing to schedule against | onboarding page / database | OPEN |
| SCH-02 | 🔴 | No reachable database: migrations 0011+ never applied, local Supabase not running | database | OPEN |
| SCH-03 | 🔴 | No cron/worker execution surface exists on the deploy target | infra / deploy | OPEN |
| SCH-04 | 🔴 | `FOR UPDATE SKIP LOCKED` is unreachable through the repo's PostgREST-only data layer | scheduler engine / database | OPEN |
| SCH-05 | 🟠 | Email verification state lives in per-process memory — the `verify_email_reminder` skip condition cannot be evaluated | scheduler engine / auth | OPEN |
| SCH-06 | 🟠 | No per-user timezone column; timezone is per-business only | database / scheduler engine | OPEN |
| SCH-07 | 🟠 | `deliver_report()` is `async def` but calls blocking `httpx.post` | notifications | OPEN |
| SCH-08 | 🟡 | No notification adapter interface — Resend is called inline at two unrelated call sites | notifications | OPEN |
| SCH-09 | 🟡 | Two existing pull-based schedulers have never been driven by anything | scheduler engine | OPEN |
| SCH-10 | 🔵 | Untracked cruft at repo root (`a`, `fix.md`) | hygiene | OPEN |

## Blockers (🔴)

### SCH-01 — Onboarding step state is client-side only; no user row exists until the final step
- **Status:** OPEN
- **Area:** onboarding page / database
- **Where:** `customer-app/src/features/onboarding/context/OnboardingContext.tsx:61-72`,
  `customer-app/src/features/onboarding/pages/TermsPage.tsx:92`,
  `api/app/routers/techscape/auth.py:129-166`,
  `database/techscape_core_schema.sql:49-66`
- **What happened:** The five onboarding screens (`/onboarding/personal-info`, `/address`, `/otp`,
  `/terms`, `/success` — `customer-app/src/App.tsx:43-66`) keep all step state in React state
  mirrored to `localStorage['klara_onboarding_state']`. Nothing is written server-side until the
  **last** screen, where `TermsPage.tsx:92` calls `authApi.register()` →
  `POST /auth/register-business`, which creates the `ts_businesses` + `ts_users` rows in one shot
  (`auth.py:138-155`). `ts_users` has columns `id, business_id, email, password_hash, first_name,
  last_name, role, status, last_login_at, created_at, updated_at` and nothing else — no
  `onboarding_step`, no `onboarding_completed_at`, no `email_verified`, no `last_activity_at`.
- **Why it blocks:** Four of the six requested sequence steps are defined against a user who has
  signed up but **not** finished onboarding: `verify_email_reminder` (signup+24h),
  `profile_nudge` (signup+48h), `activation_tip` (signup+4d), `expire_incomplete` (signup+30d,
  "internal state change"). In this codebase a user who abandons onboarding at the address screen
  leaves **zero** database rows. There is no `user_id` to anchor a timeline to, no address to send
  to, and nothing for `expire_incomplete` to expire. Equally, `stalled_checkin` fires on
  "last activity + 7d" and there is no last-activity timestamp anywhere on `ts_users`
  (`last_login_at` is written only on successful login).
- **What I need from you:** One decision — which of these is the product intent?
  **(a)** The anchor is *registration completion* (`ts_users.created_at`), the sequence is a
  post-signup activation drip, and `expire_incomplete` is dropped or redefined; **or**
  **(b)** onboarding must gain server-side persistence — a `pending_signups` table (or
  `ts_users` rows created at the personal-info step in a `pending` status) — which is a change to
  the onboarding flow itself, not to the scheduler, and needs its own scope and migration.
  I will not guess between these: (a) and (b) produce entirely different schemas and different
  cancellation semantics.
- **Workaround in place:** None. Nothing has been implemented.

### SCH-02 — No reachable database; the migration series is unapplied
- **Status:** OPEN
- **Area:** database
- **Where:** `supabase/migrations/LOG.md` (8 rows carrying "NOT APPLIED"), `scripts/DEPLOY_READINESS.md:1-12`
- **What happened:** `supabase/migrations/LOG.md` records migrations `0011_whatsapp_outbox`
  through `0025` with an "Applied by" column reading variants of *"WRITTEN, NOT APPLIED (no live
  DB in sandbox)"* — 8 entries. A local stack is also not up right now: both
  `http://127.0.0.1:54321/rest/v1/` and `http://127.0.0.1:55321/rest/v1/` (the +1000-shifted port
  documented in `GO_LIVE_ROADMAP.md:13`) refuse the connection, curl exit status `000`.
  `GO_LIVE_ROADMAP.md:52` lists hosted Supabase credentials as 🔑 *"Needs hosted project creds"*.
- **Why it blocks:** Deliverable 1 is a migration, and acceptance criteria 1, 2, 3 and 4 are all
  integration assertions against Postgres (exactly-one delivery row under two concurrent workers;
  re-claim after a killed worker; zero pending jobs after completion; nothing sent to pre-cutoff
  users). None can be executed. Working method step 5 — "dry-run against real data" — has no real
  data to run against.
- **What I need from you:** Either the hosted Supabase `SUPABASE_URL` +
  `SUPABASE_SERVICE_ROLE_KEY` for a non-production project, or confirmation to start the local
  stack (`colima start && supabase start -x vector,logflare` per `GO_LIVE_ROADMAP.md:22-27`) and
  apply migrations 0011–0025 first. Note the second option means applying 15 unapplied migrations
  authored by earlier sessions, which is its own risk and not something I will do unasked.
- **Workaround in place:** None.

### SCH-03 — There is no cron or worker execution surface on the deploy target
- **Status:** OPEN
- **Area:** infra / deploy
- **Where:** `api/pyproject.toml:24-26`, commit `00c19d8` "Remove GitHub Actions CI entirely",
  `api/app/main.py:37-48`, `scripts/DEPLOY_READINESS.md:1-12`
- **What happened:** The backend deploy target is **Vercel serverless** — `api/pyproject.toml`
  carries `[tool.vercel] entrypoint = "app.main:app"` and `scripts/DEPLOY_READINESS.md` documents
  Root Directory = `api`. There is no `api/vercel.json`, so there is no `crons` array. GitHub
  Actions was **deliberately deleted** in commit `00c19d8` (the workflow survives only as
  `.github.backup/workflows/ci.yml`, which has `on: push` and no `schedule:` trigger), so a
  scheduled GH Action is not an available target either. There is no `fly.toml`, no `Procfile`,
  no `pg_cron` usage anywhere in `supabase/migrations/`. The only always-on machinery is
  `app/main.py:37-48`, which launches `asyncio.create_task` loops gated behind
  `ENABLE_WEBHOOK_WORKER=1` and `OBSERVABILITY_ALERTS` — both in-process tasks that a serverless
  runtime does not keep alive, and precisely the pattern the brief forbids for scheduling.
  Separately, the backend has never deployed successfully: `scripts/DEPLOY_READINESS.md` and
  BLK-4 record that the Vercel project's Root Directory setting is still wrong and needs a human
  dashboard click.
- **Why it blocks:** Deliverable 4 is "worker/cron entry point wired to the deployment target,
  with the cron schedule committed to the repo". No target currently accepts one. Vercel Cron on
  the Hobby plan is limited to one invocation per day, which cannot satisfy "one cron entry runs
  every minute"; Pro is required for minute-level schedules.
- **What I need from you:** Pick the execution surface, and confirm the plan tier if it is Vercel:
  (a) Vercel Cron via a new `api/vercel.json` — needs a Pro plan for sub-daily ticks;
  (b) restore a GitHub Actions workflow with `on: schedule` — reverses a deliberate decision, and
  GH's shortest cron is 5 minutes with no delivery guarantee;
  (c) an always-on container (Fly/Railway/Render) running a worker loop — a new hosting target;
  (d) `pg_cron` inside Supabase calling a Postgres function or `net.http_post` to the API.
- **Workaround in place:** None.

### SCH-04 — The repo's data layer cannot express `SELECT ... FOR UPDATE SKIP LOCKED`
- **Status:** OPEN
- **Area:** scheduler engine / database
- **Where:** `api/app/database/connection.py:10-31`, `api/app/services/travel/wiki_service.py:68`
- **What happened:** Every database call in `api/app/` goes through the Supabase Python client
  (`create_client(...)` → `.table(...).select()/.insert()/.update()`), i.e. PostgREST over HTTP.
  There is no `asyncpg`, no `psycopg`, no SQLAlchemy and no raw-SQL path in
  `api/requirements.txt`. PostgREST has no syntax for row-level locking, so the brief's named
  mechanism is not expressible as written. The single precedent for reaching past PostgREST is
  `wiki_service.py:68`, `self.db.rpc("match_travel_wiki", {...})` — a Postgres function invoked as
  an RPC.
- **Why it blocks:** The concurrency-safety requirement is explicit and non-negotiable
  ("state which one and why"), and acceptance criterion 1 tests it directly. The three viable
  routes each carry a decision I am not authorised to take alone: **(a)** write the claim as a
  `plpgsql` function using `FOR UPDATE SKIP LOCKED` internally and call it via `db.rpc()` — fits
  the existing precedent, keeps dependencies unchanged, my recommendation; **(b)** add
  `asyncpg`/`psycopg` to `requirements.txt` and open a second connection path to Postgres — a new
  dependency plus a second credential (the direct DB URI, which the repo does not currently
  hold — see `scripts/BACKUP_OPTIONS.md:11`); **(c)** rely on a conditional-update claim
  (`UPDATE ... WHERE status='pending' AND locked_at IS NULL` returning the claimed rows), which
  PostgREST *can* express and which is safe under Postgres' read-committed re-check, but is not
  the mechanism the brief names.
- **What I need from you:** Approve (a), (b), or (c). Under the "no new heavy dependency without
  asking" constraint, (b) specifically needs a yes.
- **Workaround in place:** None.

## Issues (🟠 / 🟡 / 🔵)

### SCH-05 — Email-verification state is per-process memory, so the `verify_email_reminder` skip condition has no source of truth
- **Status:** OPEN
- **Area:** scheduler engine / auth
- **Where:** `api/app/routers/techscape/auth.py:317` (`_otp_tokens`), `auth.py:320`
  (`_verified_emails`), `auth.py:109` (`_reset_tokens`)
- **What happened:** OTP codes, the "this email was verified" marker, and password-reset tokens
  are all module-level Python dicts keyed on email with `time.monotonic()` expiries. Nothing is
  persisted. `ts_users` has no `email_verified` column (`database/techscape_core_schema.sql:49-66`).
  This is already tracked as roadmap item C3 (`GO_LIVE_ROADMAP.md:57`, "OTP/reset tokens lost on
  restart", status ❌ *Needs DB migration on hosted Supabase*) — I am logging it again here only
  because the requested sequence depends on it: `verify_email_reminder` is specified to skip when
  "email already verified", and at send time there is no durable fact to read. On serverless the
  dict is per-instance, so the answer also varies by which instance answers.
- **Impact if unfixed:** The 24-hour reminder either always sends (treating everyone as
  unverified) or needs its skip condition deleted. Both are wrong.

### SCH-06 — No per-user timezone; timezone is stored on the business
- **Status:** OPEN
- **Area:** database / scheduler engine
- **Where:** `database/techscape_core_schema.sql:30` (`ts_businesses.timezone VARCHAR(50) DEFAULT 'UTC'`),
  `api/app/routers/techscape/auth.py:69` (`RegisterBusinessIn.timezone: str = "UTC"` → written to
  the business row at `auth.py:147`)
- **What happened:** The IANA timezone captured at registration lands on `ts_businesses`, not on
  `ts_users`. `ts_users` has no timezone column. The requested quiet-hours rule is defined in
  "the user's local timezone".
- **Impact if unfixed:** Quiet hours would be evaluated per-business, which is wrong for any
  business with users in more than one zone. Fixable with an additive
  `ALTER TABLE ts_users ADD COLUMN timezone` defaulting to the business value, but it is a schema
  change and therefore gated behind SCH-02.
- **Precedent worth reusing:** `report_schedules` (migration `0012`) already models this correctly
  — local `TIME` + IANA `VARCHAR(64)`, with the reasoning for `TIME` over `TIMETZ` written into
  the migration. `app/services/travel/report_scheduler.py:evaluate_schedule` is a pure,
  clock-injectable function doing exactly the tz arithmetic this scheduler needs.

### SCH-07 — `deliver_report()` is `async def` but issues a blocking `httpx.post`
- **Status:** OPEN
- **Area:** notifications
- **Where:** `api/app/services/travel/report_scheduler.py:385` (`async def deliver_report`),
  `report_scheduler.py:452` (`resp = httpx.post(...)`, `timeout=10`)
- **What happened:** The synchronous `httpx.post` API is called inside a coroutine. It blocks the
  event loop for up to the 10-second timeout, stalling every other task on that worker — including
  the voice pipeline, which shares the loop.
- **Impact if unfixed:** This is the module I would otherwise copy for the new scheduler's email
  delivery, so the defect would propagate. It is pre-existing and out of scope to fix
  unilaterally (constraint: "do not modify unrelated files"), but the new adapter must use
  `httpx.AsyncClient` and I am flagging the existing one rather than silently diverging.

### SCH-08 — No notification adapter interface; Resend is called inline at two unrelated sites
- **Status:** OPEN
- **Area:** notifications
- **Where:** `api/app/routers/techscape/auth.py:367-380` (OTP email),
  `api/app/services/travel/report_scheduler.py:445-465` (report email)
- **What happened:** Both sites hand-roll the same `httpx` POST to `https://api.resend.com/emails`
  with `settings.RESEND_API_KEY` and `settings.FROM_EMAIL`, each with its own error handling
  (`auth.py` swallows into `traceback.print_exc()`; `report_scheduler` returns a status dict).
  There is no `EmailProvider` abstraction. By contrast WhatsApp *does* have one
  (`app/services/whatsapp/` with a `get_whatsapp_provider(business_id)` factory and a stub
  implementation that writes an outbox row instead of transmitting), and `app/services/payments/`
  follows the same base+stub shape.
- **Impact if unfixed:** Deliverable 5 asks for exactly that interface with a no-op/console
  implementation for tests and local dev. Building it is straightforward and the
  `whatsapp`/`payments` packages give the house pattern to copy — noting it so the new interface
  is understood as *new*, not as something already present.
- **Also relevant:** `RESEND_API_KEY` is unset (`GO_LIVE_ROADMAP.md:51`, 🔑 *Not set*), so no email
  can actually be delivered in this environment regardless.

### SCH-09 — Two pull-based schedulers already exist and nothing has ever driven them
- **Status:** OPEN
- **Area:** scheduler engine
- **Where:** `api/app/services/travel/playbook_scheduler.py:1-11`,
  `api/app/services/travel/report_scheduler.py:1-30`
- **What happened:** Both modules document themselves as pull-based and explicitly defer execution
  to something external — *"call it from a cron / queue worker (every 5 minutes is fine)"*
  (`playbook_scheduler.py:9-10`) and *"An external cron / queue worker pokes the endpoint every few
  minutes"* (`report_scheduler.py:16`). Per SCH-03, that cron does not exist. `report_scheduler`
  also defaults `dry_run=True` on `run_due`, so even a manual poke sends nothing by default.
- **Impact if unfixed:** This is the strongest argument for Option A plus **one shared tick**: a
  third independent scheduler with a third un-poked `/run-due` endpoint would make the problem
  worse. Whatever execution surface SCH-03 resolves to should drive all three.

### SCH-10 — Untracked files at repo root
- **Status:** OPEN
- **Area:** hygiene
- **Where:** repo root — `a` (36 bytes), `fix.md` (16 KB), both untracked per `git status`
- **What happened:** `a` looks like an accidental shell redirect artifact. `fix.md` is referenced
  by `GO_LIVE_ROADMAP.md` as a real working document but has
  never been committed, so the roadmap points at a file absent from the repository for anyone who
  clones it. (`GO_LIVE_ROADMAP.md:13` — "needs venv fix — see fix.md M5"; `GO_LIVE_ROADMAP.md:43` —
  "Phase 2 — Code Fixes (from fix.md)".)
- **Impact if unfixed:** Cosmetic for the scheduler; a genuine documentation gap for the roadmap.
  Not mine to delete or commit unasked.

## Errors encountered and resolved

None. Phase 0 was read-only discovery; no build, migration, or test was run, so nothing broke.

## Assumptions made

1. **"The onboarding page" means the customer-app flow, not the agency dashboard.**
   `customer-app/src/features/onboarding/` is the only directory implementing a stepped signup.
   `agency-dashboard/src/features/admin/EmpirePage.tsx` matches the string "onboard" but is an
   admin view, not a signup flow. *If wrong:* the entire target changes.
2. **"User" means `ts_users` (a business admin/agent), not `travel_customer_profiles` (a
   traveller).** The onboarding flow terminates in `POST /auth/register-business`, which creates a
   business plus its first admin user. The repo has a second, separate identity — travellers, who
   sign in at `/trip/login` (`customer-app/src/App.tsx:76`) — with its own access-path table
   (migration `0021_traveller_access_paths`). *If wrong:* different table, different anchor,
   different channels (travellers are reached over WhatsApp, not email).
3. **The default channel should be WhatsApp, not email.** Every delivery mechanism this repo has
   actually built targets WhatsApp; email exists only as two inline Resend calls (SCH-08), and
   `RESEND_API_KEY` is unset. The sequence table in the brief specifies email. *If wrong:* the
   adapter and templates change, not the engine.
4. **CLAUDE.md's banner applies here.** There is no `frontend/` directory; the design-system
   section of CLAUDE.md describes an unbuilt marketing site. I have not looked for or created
   anything there.

## Open questions

1. Should the sequence anchor on registration completion, or does onboarding need server-side
   persistence of partial progress first? (SCH-01 — blocking.)
2. Which execution surface drives the tick: Vercel Cron (Pro?), a restored GitHub Action, an
   always-on container, or `pg_cron`? (SCH-03 — blocking.)
3. Is adding `asyncpg`/`psycopg` acceptable, or should job claiming go through a `plpgsql` RPC in
   the `match_travel_wiki` style? (SCH-04 — blocking.)
4. Is there a hosted Supabase project I may apply migrations to, or should the local stack be
   started and migrations 0011–0025 applied first? (SCH-02 — blocking.)
5. What is the product definition of "activation" for `activation_tip`? Nothing in the schema
   marks a user as activated.
6. Should the new scheduler subsume the two existing un-driven schedulers' `/run-due` endpoints
   under one tick, or stay independent? (SCH-09.)
7. Is the audience business admins or travellers, and does the answer change the channel from
   email to WhatsApp? (Assumptions 2 and 3.)

## Verification not performed

Every acceptance criterion is unverified, because no implementation exists yet and Phase 0 stops
before code. Beyond that, these are blocked from *ever* being verified in the current environment
until SCH-02 and SCH-03 are resolved:

- [ ] Running the tick twice concurrently produces exactly one delivery row per
  `(user_id, step_key)` — no database (SCH-02); the claim mechanism is also undecided (SCH-04).
- [ ] Killing the worker mid-job leaves the job re-claimable — no database, no worker process.
- [ ] A user completing onboarding has zero pending jobs afterward — no database, and "completing
  onboarding" is not yet a defined server-side event (SCH-01).
- [ ] Enabling the scheduler on an existing database sends nothing to users created before the
  cutoff — no existing database with historical users to test against.
- [ ] Every failure path is visible in logs with `user_id` and `step_key` — no code.
- [ ] `docs/scheduler.md` is accurate enough for someone else to add a step — not written.
- [ ] Dry-run against real data (working method step 5) — no reachable database and no real user
  data.

`docs/` currently contains only a `legal/` subdirectory; no `docs/scheduler.md` exists.
