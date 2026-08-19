# Onboarding Scheduler — Issues, Blockers & Errors

**Repo:** advertsocialai/techscapeai-platform · **Branch:** claude/vigilant-goodall-dw56vg · **Last updated:** 2026-08-19  
**Build status:** Phase 0 – Discovery complete

| Severity | Meaning |
|---|---|
| 🔴 Blocker | Implementation cannot proceed, or shipping this would break production. |
| 🟠 High | Real defect or data-integrity risk. Must fix before launch. |
| 🟡 Medium | Degrades reliability or UX. Fix soon. |
| 🔵 Low | Hygiene or tech debt. |

## Summary
| ID | Sev | Title | Area | Status |
|---|---|---|---|---|
| SCH-P0-01 | 🔵 | Onboarding completion state not yet modeled in DB | onboarding page | OPEN |
| SCH-P0-02 | 🔵 | User timezone not persisted; no current onboarding email template | notifications | OPEN |

## Phase 0 — Discovery Findings

### Stack
- **Language/Framework:** Python 3.x + FastAPI 0.115.6 + Uvicorn 0.32.1
- **ORM/Query:** Supabase Python client 2.10.0 (direct SQL + RPC layer)
- **Deployment:** Serverless on Vercel (FastAPI backend at `api/` with entrypoint `app.main:app`)
- **Package manager:** pip + requirements.txt (no poetry/setup.py)
- **Node version:** Not used for backend; frontend uses npm
- **Hosting target:** Vercel (serverless functions, no long-lived processes)

### Database
- **Engine:** PostgreSQL via Supabase
- **Migrations:** `/supabase/migrations/` — SQL files, numbered sequentially, forward-only
- **Current pattern:** Service-role-only (FastAPI is gatekeeper), RLS enabled on all tables, `REVOKE ALL FROM anon, authenticated`
- **Users table:** No explicit `ts_users` creation visible in Phase 0 (likely created by Supabase Auth), but migrations reference it with FK to `id UUID`
- **Current user-related tables:** `ts_users`, `ts_businesses`, `branches`, `ts_api_integrations`
- **Existing scheduler tables:** `report_schedules` (0012), `follow_up_rules` + `follow_ups` (0013, not applied yet)

### Onboarding Page (Customer App)
- **Location:** `/customer-app/src/features/onboarding/`
- **Steps:** 5 pages (route `/onboarding/*`)
  1. `LoginPage` — email + password sign-in
  2. `PersonalInfoPage` — first/last name, email, phone, country, password
  3. `AddressPage` — street, city, state, postal, country, company
  4. `OtpPage` — OTP verification (email or SMS)
  5. `TermsPage` — terms, age, marketing opt-in
  6. `SuccessPage` — completion screen
- **State persistence:** React Context (`OnboardingContext`) → localStorage (`klara_onboarding_state`)
- **Completion marker:** No explicit "onboarding_complete" flag visible; success page reached = end-state
- **No backend API endpoint for onboarding state** observed yet — purely frontend-driven

### Existing Async Work
- **Pattern established:** PULL-BASED, no APScheduler, no background threads
  - `playbook_scheduler.py` (lines 1–156): time-based dispatch for bookings
  - `report_scheduler.py` (partial read): timezone-aware recurring reports
  - Both exposed as `/scheduled/due` (GET) + `/scheduled/run-due` (POST)
  - Invoked by external cron/queue worker (every 5 minutes is standard)
- **De-duplication:** Persisted state only (travel_playbook_runs table, report_schedules.last_run_at)
- **No background workers, no Celery, no RQ, no Redis-backed queues** — pull-based only
- **Redis optional:** Available in config (`REDIS_URL`) for pub/sub + JWT blacklist, but not required

### Email/Notification Provider
- **Primary:** SendGrid (`sendgrid_provider.py`) — uses v3 REST API
- **Fallback:** Stub mode when no API key (returns fake delivery ID, logs to stdout)
- **Also available:** Resend API key in config (not yet integrated)
- **Email address:** `FROM_EMAIL = "noreply@techscapeai.com"`, `NOTIFICATION_EMAIL = "hello@techscapeai.com"`
- **Templates:** None found; would need to be created

### Deployment Constraints
- **Serverless (Vercel Functions):** No long-lived processes, no in-memory state, no daemon threads
  - Implication: Cannot use `asyncio.create_task()` with long waits; must be pull-based
  - Cold starts: ~1–5s, so external cron/queue is the trigger
- **API structure:** Single Vercel deployment runs FastAPI for all routes
- **Cron:** No built-in Vercel cron (they offer it only for hobby plan edge functions, not for Python backend)
  - **Solution:** Must wire to Vercel `/api/cron` edge function or external cron service (GitHub Actions, AWS EventBridge, cron.io, etc.)

---

## Proposed Architecture: **Option A — Database-backed job table + pull-based endpoints**

**Rationale:**

The repo already has an established pattern: `playbook_scheduler.py` and `report_scheduler.py` are both pull-based, with no third-party queue or APScheduler. They expose `/scheduled/due` and `/scheduled/run-due` endpoints, and an external cron pokes them. Extending this pattern for onboarding is the lowest-friction choice because:

1. **Consistency:** Matches the repo's two existing schedulers, so a future maintainer already knows the shape
2. **No new dependencies:** The repo has Supabase (Postgres) already; no need for BullMQ, SQS, QStash, etc.
3. **Debuggability:** Every job is a Postgres row, visible in SQL; easier than a queue black-box
4. **Serverless-friendly:** Pull-based avoids the 5-minute Lambda timeout and cold-start cascades
5. **Existing expertise:** The codebase already has retry logic, timezone handling, and at-least-once semantics in `report_scheduler.py`

**Architecture:**

- **Table:** `onboarding_jobs` — one row per `(user_id, step_key)`, with `run_at`, `status`, `attempts`, `locked_at`, `last_error`
- **Idempotency:** `UNIQUE (user_id, step_key)` + status enum (pending/in_progress/sent/failed/cancelled)
- **Concurrency:** `SELECT ... FOR UPDATE SKIP LOCKED` to claim jobs atomically
- **Retries:** Exponential backoff (2, 4, 8, 16 seconds) with jitter, max 3 attempts
- **Endpoint:** `POST /api/onboarding/scheduled/run-due` (mirrors playbook_scheduler)
- **External cron:** GitHub Action or Vercel cron edge function (to be wired during Phase 2)
- **Notifications:** Via `SendGridProvider` (existing)
- **Sequence config:** Python dataclass / dict, not scattered if-statements

---

## Open Questions

- Where does the backend currently read/persist user profile state (email verified, profile complete, etc.)? A quick grep showed no `users` table creation — is it managed by Supabase Auth, or does it need to be created?
- Should the scheduler start pre-loaded with defaults for the marketing site, or is this only for the customer app (Klara)?
- Are there existing email templates for onboarding sequences, or do we start from scratch?
- Who should be the fallback timezone if user timezone is not set? (Proposal: UTC with an explicit fallback, documented)

---

## Assumptions Made

1. **No users table yet:** The onboarding flow is frontend-only at the moment. The `ts_users` table exists (FK'd in migrations), but no "onboarding_complete" column. We will add this in the migration.
2. **Pull-based is preferred:** Given the existing `playbook_scheduler` and `report_scheduler` patterns, and Vercel's serverless constraints, the pull-based Option A is the natural extension.
3. **Vercel cron is available:** We will assume an external cron or Vercel cron edge function can hit `POST /api/onboarding/scheduled/run-due` every 5 minutes. If Vercel doesn't support this, we'll wire it via GitHub Actions.
4. **Service-role-only access:** All DB access happens via the FastAPI service-role key, no anon/authenticated JWT policies needed.
5. **Timezone fallback:** UTC if user doesn't have a timezone set; documented in `docs/scheduler.md`.

---

## Verification Not Performed

- [ ] Actual user signup flow endpoint (no `/api/auth/signup` found yet — may be Supabase Auth only)
- [ ] Whether email verification is already required before onboarding "complete"
- [ ] Existing email templates for onboarding (likely need to be created)
- [ ] Vercel cron availability and pricing in this account
