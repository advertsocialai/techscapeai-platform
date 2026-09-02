# Feature Document — Dashboards

**Branch:** `Klara-ai` @ `2a87dec` · **Validated live:** 2026-09-02 · **Method:** Playwright against the Vercel branch previews

Covers the **Agency dashboard** (18 feature routes) and the **Klara traveller dashboard** (3 screens).

Status key: **Works** = exercised live and behaved correctly · **Guarded only** = the auth guard was verified, the feature behind it could not be reached · **Broken** = exercised live and failed.

---

## Reading this document honestly

Every dashboard feature on both surfaces sits behind authentication, and **authentication is broken on both surfaces** (see `FEATURE_ONBOARDING.md`, gaps O-1 and O-6). So for all 21 feature screens this run establishes exactly one thing:

> the route is correctly guarded, and an anonymous visitor is sent to the login screen instead of a broken page.

It establishes **nothing** about whether any feature works. Widgets, data loading, filters, mutations, WebSocket streams and empty/error states are all **unvalidated**. That is a limitation of the environment, not a verdict on the code — and it is the single largest hole in coverage right now.

---

## Part A — Agency dashboard

Routes from `agency-dashboard/src/App.tsx`, all wrapped in `RequireAuth` inside `DashboardLayout`.

### A1 · Auth guard — the one thing fully proven

| Result | Detail |
|---|---|
| **18 / 18 routes redirect anonymous → `/login`** | no leaks, no blank pages, no uncaught JS |

This is a genuine pass and worth stating plainly: there is no route on the agency dashboard that renders privileged chrome to a signed-out visitor.

### A2 · Feature inventory and status

| # | Feature | Route | Status |
|---|---|---|---|
| 1 | Mission Control (home) | `/` | Guarded only |
| 2 | Journey Board | `/journey-board` | Guarded only |
| 3 | Guest Story (lead detail) | `/journey-board/:leadId` | Guarded only |
| 4 | Bookings | `/bookings` | Guarded only |
| 5 | Packages | `/packages` | Guarded only |
| 6 | Payment Links | `/payment-links` | Guarded only |
| 7 | WhatsApp | `/whatsapp` | Guarded only |
| 8 | Follow-ups | `/follow-ups` | Guarded only |
| 9 | Reports | `/reports` | Guarded only |
| 10 | Cost | `/cost` | Guarded only |
| 11 | Report Schedules | `/report-schedules` | Guarded only |
| 12 | Team | `/team` | Guarded only |
| 13 | Activity Log | `/activity` | Guarded only |
| 14 | Playbooks | `/playbooks` | Guarded only |
| 15 | AI Config | `/ai-config` | Guarded only |
| 16 | Empire (admin) | `/empire` | Guarded only |
| 17 | Live Call list | `/live-call` | Guarded only |
| 18 | Live Call detail | `/live-call/:callId` | Guarded only |

### A3 · Backing endpoints — every one is down

Each feature was traced to its API endpoint and probed directly. All returned `500 FUNCTION_INVOCATION_FAILED` (RC-1 — the API's dependencies are never installed):

| Feature | Endpoint | Live |
|---|---|---|
| Journey Board | `/api/travel/v1/leads` | 500 |
| Bookings | `/api/travel/v1/bookings` | 500 |
| Packages | `/api/travel/v1/packages` | 500 |
| Payment Links | `/api/travel/v1/payments` | 500 |
| WhatsApp | `/api/travel/v1/whatsapp/sessions` | 500 |
| Follow-ups | `/api/travel/v1/followups` | 500 |
| Reports | `/api/travel/v1/reports` | 500 |
| Cost | `/api/travel/v1/usage` | 500 |
| Activity Log | `/api/travel/v1/activity` | 500 |
| AI Config | `/api/travel/v1/ai-config` | 500 |
| Playbooks | `/api/travel/v1/playbooks` | 500 |
| Live Call | `/api/travel/v1/calls` | 500 |
| Empire | `/api/techscape/v1/businesses` | 500 |
| Team | `/api/techscape/v1/users` | 500 |

**Gap D-1 (BLOCKER):** every agency feature is dataless. Even with login fixed, all 18 screens would render against a dead API.

An intended check could not run at all: **do these endpoints reject anonymous callers with 401/403?** A 500 masks the answer. Tenant isolation and access control on the agency surface therefore remain **unverified** — worth re-running first once RC-1 is fixed, since a leak here would be serious.

**Gap D-2 (MEDIUM):** `agency-dashboard/src/lib/ws.ts` notes that the Live Call WebSocket bypasses the `/api` base. WebSocket connection, auth and stream handling are entirely unvalidated.

---

## Part B — Klara traveller dashboard

Routes from `customer-app/src/App.tsx`, behind `RequireTraveller`, backed by `travellerApi.ts`.

### B1 · Guard behaviour — proven

| Route | Anonymous result |
|---|---|
| `/trip` | → `/trip/login` |
| `/trip/payments` | → `/trip/login` |
| `/trip/messages` | → `/trip/login` |
| `/dashboard` (alias) | → `/trip/login` |

All correct.

### B2 · Traveller sign-in — Broken

- **Route:** `/trip/login` — email → OTP (a traveller has no password)
- **Page:** renders correctly
- **Submit:** **fails**

```
POST https://klara-customer-app-git-klara-ai-….vercel.app/api/travel/v1/me/auth/request-otp
→ 405 Method Not Allowed
```

**Gap D-3 (BLOCKER):** `travellerApi.ts` uses a **relative** base (`/api/travel/v1/me`), and `customer-app/vercel.json` rewrites `/(.*)` → `/index.html`. The OTP request lands on the static host, which refuses POST.

Note this is a *different* failure from the onboarding login on the same app: onboarding uses an absolute Railway URL (dead host), the traveller surface uses a relative path (static host). **Two separate fixes are required in one app.**

Historical context: BLK-14 recorded that `travellerApi.ts` called `/me/auth/request-otp` and `/verify-otp`, which did not exist on the backend; `baaf167` restored them. That fix cannot be confirmed live — the request never reaches the backend, and the platform 500s anyway.

### B3 · Feature status

| Feature | Route | Status | Unvalidated |
|---|---|---|---|
| Trip overview | `/trip` | Guarded only | itinerary render, booking data, empty state |
| Payments | `/trip/payments` | Guarded only | payment list, Razorpay links, status |
| Messages | `/trip/messages` | Guarded only | thread render, send, delivery |

`GET /api/travel/v1/me/trip` probed directly → **500**.

---

## Dashboard gap register

| ID | Sev | Gap | Fix |
|---|---|---|---|
| D-1 | BLOCKER | All 14 agency endpoints 500 — every feature dataless | Fix RC-1 (`api/pyproject.toml` dependencies) |
| D-3 | BLOCKER | Traveller OTP POSTs to the static host → 405 | Add `/api` rewrite, or absolute base in `travellerApi.ts` |
| D-4 | BLOCKER | Agency login broken → all 18 features unreachable | See O-6 |
| D-2 | MEDIUM | Live Call WebSocket entirely unvalidated | Re-test after D-1 |
| D-5 | HIGH (unknown) | Anonymous access control on protected endpoints unverifiable behind 500s | Re-run the protected-endpoint checks first after RC-1 |

---

## What to run first once a backend answers

The suite already contains these checks; they are currently drowned out by 500s.

1. **Anonymous rejection** — every protected endpoint must return 401/403, never 200. (`specs/platform-api.spec.ts`)
2. **Agency login → Mission Control**, then walk all 18 routes authenticated.
3. **Traveller OTP → `/trip`**, then payments and messages with real data.
4. **Tenant isolation** — agency A must not read agency B's leads, bookings or payments. Not yet written; add once login works.
