# Platform status — narrative evidence behind the scoreboard

Last updated **2026-08-10 (wave-2 push-to-100 run)**. History: wave-1 baseline
at `361a318`, wave-1 tables at `21d4775`.

> **The numbers live in `GOGAGA_ANALYSIS_REPORT.md`** — one combined table,
> updated in the same commit as any change that moves a row (enforced by the
> gogaga-scoreboard skill + `scripts/check_scoreboard_updated.sh`). This file
> holds the narrative evidence and the as-found risk records; it no longer
> duplicates the tables, because two copies of the same numbers WILL drift.

---

## Wave-2 evidence (2026-08-10)

**The caveat fell.** Wave 1 ended with "no data has ever travelled from
Postgres to a screen". Wave 2 built a local verification seam
(`scripts/local_seam/`): Postgres 16 + pgvector with every real migration
applied (0001–0022, zero errors on vanilla PG), bridged to the UNMODIFIED
application path by a minimal PostgREST-compatible shim. Through it, in one
session: real signup → real login → lead/customer/booking written through the
API → traveller OTP login → `/me/trip` → **the real customer-app UI rendered
booking SEAM-BALI-001 in Chromium (0 page errors)**, and **the real dashboard
UI rendered the lead on Mission Control and the Journey Board**. Cross-token
separation returned 401 against real data. What the seam deliberately does not
prove: RLS-as-anon on managed Supabase (proven separately via MCP probes),
service-role behaviors, PostgREST beyond the shim's measured subset — those
wait on BLK-2/BLK-3.

**Everything measured this run, with how:**

- **Backend testing**: 250 tests (was 80), coverage measured at 54% lines with
  the scoring rule in `api/tests/COVERAGE_RULE.md` (all 45 router modules
  exercised success+failure through the app; core/deps 92%).
- **Frontend testing**: 31 + 39 component/interaction tests (was 13+13); rule
  in `customer-app/src/TESTING_RULE.md`.
- **Rate limiting**: Redis sliding-window (sorted set, atomic pipeline) with
  in-memory fallback; two OS processes proven to share one budget (combined
  11th request 429s).
- **Accessibility**: axe-core WCAG 2 A/AA on **all 34 routes of both apps,
  authenticated, with real data: 0 violations** after fixing 27 (unnamed
  password-eye button, 15 unlabeled selects, three contrast tokens); keyboard
  pass green on the 5 interactive-heavy screens.
- **Compliance mechanisms**: consent event row written when the answer XML is
  served; DPDP erasure endpoint anonymizing 10 tables (money kept, audited);
  ToS/Privacy DRAFT skeletons (facts only, `[LEGAL TO COMPLETE]`).
- **Observability**: 3 alert rules as code with real producer hooks firing
  into the stub transport; uptime checks defined + runnable; ErrorBoundary in
  both apps (the dashboard's error reporting was never initialized — found and
  wired this run).
- **Deployment/CI code-readiness**: dashboard `vercel.json`, api
  `pyproject.toml` `[tool.vercel] entrypoint`, CI pytest gating + coverage
  step; the remaining red is BLK-4 (two Root Directory clicks) and BLK-5
  (Actions billing) — both human dashboard actions, exact click-paths in
  `scripts/DEPLOY_READINESS.md`.
- **Data model**: migration 0022 makes the payment_links attribution backfill
  exhaustive (phone is the lead's only identity column — verified against
  information_schema) and payments.py now attributes at creation. Applied
  clean locally; **pending apply to live Supabase — the Supabase MCP dropped
  its authorization mid-run (re-auth needed, then apply 0022)**.

Corrections made against wave-1's own record, for honesty's sake: the
"1 feature not on the API" line was a wording bug (the 13th dashboard feature
is `layout`, correctly a shell); a wave-2 claim that bad payment amounts had
been a DB-500 was wrong (a validator already made them 422) and was corrected
before push.

---

## Risks found while compiling this (as-found records, both closed)

### RISK-1 — ✅ CLOSED 2026-08-09: unauthenticated endpoints had no rate limiting

As found: the limiter lived inside `require_business`, keyed by business_id —
`/auth/login`, `/auth/otp/send`, `/auth/password/forgot`, and the new
`/me/auth/request-otp` (added that same day, inheriting the gap) had none.
Closed same run with IP+email dual-key limiting on all six endpoints; wave 2
moved it to Redis with a two-process proof.

### RISK-2 — ✅ RECONCILED 2026-08-09: `CLAUDE.md` described an application that does not exist

As found: the repo's instruction file specified a `frontend/` marketing site in
detail; no such directory exists. Reconciled with a READ-FIRST banner mapping
the real apps to their convention sources; building the marketing site is
BLK-9 scope.

---

## Blockers — what is genuinely not closable from here

| ID | Blocker | Blocks | Owner |
|---|---|---|---|
| **BLK-1** | No Plivo credentials (`PLIVO_AUTH_ID`/`TOKEN`/`PHONE_NUMBER` + `PUBLIC_BASE_URL`) | Audio playback — TTS bytes are produced and measured, transmitting them needs an MPC leg | Gowtham |
| **BLK-2** | No `SUPABASE_SERVICE_ROLE_KEY` | The managed-Supabase data path (the app seam itself is now proven via the local seam) | Gowtham |
| **BLK-3** | Sandbox gateway 403s `supabase.co:443` (and GitHub release downloads) | Reaching managed Supabase from this container at all | Environment policy |
| **BLK-4** | Two Vercel Root Directory clicks: `agency-dashboard` `agency-app`→`agency-dashboard`; `techscapeai-platform` empty→`api` | Both non-customer deploys. Everything code-side is committed; click-path in `scripts/DEPLOY_READINESS.md` | Gowtham |
| **BLK-5** | GitHub Actions billing (Settings → Billing → Actions) | All CI. The pipeline is complete and gating; every job since run #22 fails runnerless in ~2s | Gowtham |
| **BLK-6** | `SENTRY_DSN` | Error tracking + alerting going live (stub transport proven, rules firing) | Gowtham |
| **BLK-7** | Backup policy: pick A/B/C in `scripts/BACKUP_OPTIONS.md` + one restore drill | Trusting recovery. The pg_dump mechanism is built | Gowtham — decision |
| **BLK-8** | Legal review: consent wording (+te/hi), ToS/Privacy final text | Publishing the drafts; the mechanisms all run | Gowtham — legal |
| **BLK-9** | Marketing-site scope decision | Building `frontend/` per CLAUDE.md's design system | Gowtham — decision |
| **B-FE7-08** | How the customer app learns which agency it serves | Multi-agency travellers landing on the right trip | Gowtham — decision |
| **(new)** | Supabase MCP authorization dropped mid-run | Applying migration 0022 to the LIVE database (applied clean locally) | Gowtham — re-auth connector |
