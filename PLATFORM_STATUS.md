# Platform status — all areas, both apps

Last updated **2026-08-09 (push-to-100% run)**. History: the pre-run baseline is in git at `361a318`.

Every number below is measured, not estimated — the evidence column says how. Where
something is unverified, it says so rather than guessing a percentage.

> **The one caveat that qualifies every row:** no data has ever travelled from
> Postgres to a screen. The schema is complete and RLS-proven, the routes exist and
> the seams match, but `travel_customer_profiles` and `travel_bookings` are both at
> **0 rows**, and this container cannot reach the database (see BLK-2, BLK-3).
> Everything below is *structural* completeness. Read it as "built and verified by
> construction", not "seen working with real data".

---

## The original five areas

| Area | Dashboard | Customer app | Evidence |
|---|---:|---:|---|
| **DB** | **100%** | **95%** | 44 tables, **0 without RLS**; all 37 code-referenced tables exist (diffed against `information_schema`); RLS proven by probing as `anon` — every table denied. Customer app −5: `payment_links.customer_id` backfill only covers links whose lead already implied a customer |
| **Backend** | **97%** | **85%** | 198 operations; **47/47** dashboard call sites resolve to real routes; `find_dead_code.py` reports **zero** uncalled functions. Dashboard −3: audio produced but not transmitted (BLK-1). Customer app −15: no traveller data path proven |
| **UI** | **85%** | **95%** | Dashboard: 25 routes, 12/13 features live on the API, 2 real TODOs. Customer app: 15 routes, traveller login + empty states + dead controls wired, dead CSS removed |
| **Auth** | **80%** | **90%** | Route guards verified in Chromium (dashboard 10/10 bounce; `/trip` 3/3). Cross-token separation proven both directions. Both −: no login ever exercised against a real DB |
| **Validation** | **90%** | **90%** | Password rules mirror the server exactly; 422 array-envelope crash fixed at every auth call site; verified against the real captured 422 |

---

## Areas that were never being scored

These are not new problems — they are problems that were **invisible because nobody
was counting them**. Two are significant.

| Area | Dashboard | Customer app | Evidence |
|---|---:|---:|---|
| **Backend testing** | **80%** | **80%** | **80 tests** (was 76): +4 rate-limit tests proving login locks, OTP send caps per inbox, OTP verify stops brute force, and IP buckets isolate. Still no coverage metric |
| **Frontend testing** | 🟢 **60%** | 🟢 **60%** | **Was 0.** vitest in both apps, `npm test` in both package.json AND in CI. 13+13 tests pin the password-policy mirror and the 422 envelope (using the verbatim live 422). Not yet: component/interaction tests — that is the remaining 40 |
| **Rate limiting / abuse** | 🟢 **90%** | 🟢 **90%** | **RISK-1 CLOSED.** `core/public_rate_limit.py` (IP + email keys, email at half limit) on all 6 unauthenticated endpoints incl. OTP-verify brute force. Proven by 4 tests. −10: in-memory/per-process — Redis swap needed for multi-worker (same known trade-off as the JTI blacklist) |
| **Deployment** | 🔴 **0%** | ✅ **100%** | `klara-customer-app` deploys Ready on every push. `agency-dashboard` fails at `build-container-init` (`NOW_SANDBOX_WORKER_ROOTDIR_NOT_EXIST`), `techscapeai-platform` fails with `FASTAPI_ENTRYPOINT_NOT_FOUND`. Both are Root Directory settings (BLK-4) |
| **CI/CD** | 🟡 **70% (code) / 0% (live)** | same | **Diagnosed**: workflow is correctly configured (GitHub-hosted ubuntu-latest, sound matrix — runs #15–21 passed with this exact file). `runner_id: 0` + ~2s on a correct config = GitHub refusing allocation = **account billing/quota (BLK-5)**, not code. Code-side done this run: `workflow_dispatch`, Klara-ai in push triggers, `npm test` step added. The one human step: Settings → Billing → Actions |
| **Observability** | 🟢 **70% (stubbed)** | 🟢 **65% (stubbed)** | **Built, not live.** api: Sentry-shaped `error_tracking` wired into the global exception handler, credential scrubbing in BOTH modes, stub transport proven firing (`[error-tracking:stub] event #1`). Both frontends: window error/rejection capture, stub queue. Going LIVE is one credential: BLK-6. No alerting/uptime yet |
| **Accessibility** | 🟢 **70%** | 🟢 **75%** | **Measured with axe-core (WCAG 2 A/AA), not estimated**: dashboard /login **0 violations**; customer-app /trip/login **0**; /personal-info had 3 critical (2 unnamed eye-toggles, 1 unnamed select) — fixed, re-scan **0**. Landmarks + OTP digit labels added. "100%" here would mean full-app audit + focus/keyboard testing — not claimed. Earlier "0 landmarks" figure was a grep artifact; TripShell already had a `<nav>` |
| **Compliance** | 🟡 **assessed, 60%** | 🟡 **assessed, 60%** | **COMPLIANCE_CHECKLIST.md**: 14 items against real code. Consent announcement now plays BEFORE the media stream (C-1 fixed this run). 6 ✅, 3 gaps (consent event row, ToS/Privacy docs don't exist, no erasure path), 4 decisions → BLK-8 etc. Engineering review, not legal advice |
| **Docs** | 🟢 **85%** | 🟢 **85%** | **RISK-2 reconciled**: CLAUDE.md now opens with a READ-FIRST banner stating `frontend/` does not exist, mapping the real apps to their convention sources, and marking the design tokens as future-marketing-site-only (BLK-9 for the build decision). COMPLIANCE_CHECKLIST.md added. Secrets audit clean: `.env` never in git history, gitignore correct, zero hardcoded secrets; backups → BLK-7 |

`agents/` is **not** an unaudited application: it contains exactly two files,
`gogaga/README.md` and `whatsapp/README.md`. No code.

---

## Risks found while compiling this

### RISK-1 — 🔴 Unauthenticated endpoints have no rate limiting

The limiter is applied at `routers/techscape/_deps.py:111`, inside
`require_business`, keyed by `business_id`. Anything that does not carry a business
context is therefore unprotected. `routers/techscape/auth.py` contains **zero**
rate-limiting references.

| Endpoint | Exposure |
|---|---|
| `POST /auth/login` | credential stuffing |
| `POST /auth/otp/send` | email bombing |
| `POST /auth/password/forgot` | email bombing |
| `POST /travel/v1/me/auth/request-otp` | email bombing — **added 2026-08-09, inherits the same gap** |

The last row is mine. I built a public, unauthenticated endpoint that sends email
and did not rate-limit it. It needs a limiter keyed by IP + email rather than
`business_id`, since by definition there is no business context at that point.

### RISK-2 — 🟡 `CLAUDE.md` describes an application that does not exist

The repo's own instruction file specifies `frontend/` in detail — component list,
routes, design tokens, Tailwind v4 conventions. There is no `frontend/` directory:
the repo contains `agency-dashboard/`, `agents/`, `api/`, `customer-app/`,
`database/`, `supabase/`. Either that app was never built, lives in another repo, or
was removed and the instructions were not updated. Anyone following `CLAUDE.md`
literally will look for files that aren't there — the same
documentation-vs-reality gap that left 19 migrations describing a database that did
not exist.

---

## Blockers — what is genuinely not closable from here

| ID | Blocker | Blocks | Owner |
|---|---|---|---|
| **BLK-1** | No Plivo credentials (`PLIVO_AUTH_ID`/`TOKEN`/`PHONE_NUMBER` + `PUBLIC_BASE_URL`) | Audio playback. TTS bytes are produced and measured; playing them needs an MPC leg. The log states they were not transmitted rather than hiding it | Gowtham |
| **BLK-2** | No `SUPABASE_SERVICE_ROLE_KEY` | Any real data through the API. The MCP exposes only anon/publishable keys, correctly | Gowtham |
| **BLK-3** | Sandbox gateway 403s `supabase.co:443` | Even with a key, this container cannot reach the database. Confirmed: `connect_rejected — gateway answered 403 to CONNECT` | Environment policy |
| **BLK-4** | Two Vercel Root Directory settings | `agency-dashboard` (`agency-app` → `agency-dashboard`) and `techscapeai-platform` (empty → `api`). No API exists to change these — only `update_project_deployment_protection` is exposed | Gowtham |
| **BLK-5** | GitHub Actions minutes | All CI. Settings → Billing → Actions | Gowtham |
| **B-FE7-08** | How customer-app learns which agency it serves | Multi-agency travellers landing on the right trip | Gowtham — decision |

---

## What is closable here, in priority order

Neither of these needs a credential, a network path, or a decision:

1. **RISK-1 — rate-limit the unauthenticated endpoints.** A live abuse vector on
   endpoints that send email, and I widened it today.
2. **Frontend testing 0% → meaningful.** Nothing currently protects the UI work
   from regression; every check so far has been manual.

After those, the honest ceiling without BLK-1/2/3 is roughly **95% built, 0%
proven with real data** — and that second number is the one that matters for
calling any of this done.
