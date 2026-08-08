# customer-app — scope questions

**Status:** discovery complete, feature build **not** started (by design).
**Date:** 2026-08-08

FE Phase 7 was scoped as discovery and scaffolding only. This document exists
because the questions below cannot be answered by reading the codebase, and
guessing any one of them wrong means building the wrong product.

---

## What already exists

`customer-app/` is a working Vite + React 19 + TypeScript app, same stack as
`agency-dashboard/` (TanStack Query, axios, react-router-dom 7, plus `zod`,
which the dashboard does not use).

It contains a **complete 6-screen onboarding flow**:

| Route | Screen |
|---|---|
| `/onboarding/login` | Login |
| `/onboarding/personal-info` | Name, email, phone, password |
| `/onboarding/address` | Street, city, state, postcode, country, company |
| `/onboarding/otp` | Email OTP verification |
| `/onboarding/terms` | Terms, age confirmation, marketing opt-in |
| `/onboarding/success` | Confirmation |

`/dashboard` is a placeholder that renders "🚀 Dashboard coming soon…".

**Its API surface is correct.** All 7 declared client paths were diffed against
the live route table and every one exists:
`/auth/login`, `/auth/register-business`, `/auth/otp/send`, `/auth/otp/verify`,
`/auth/me`, `/auth/password/forgot`, `/auth/refresh`.

### One real defect, fixed during this pass

The 401 interceptor logged the user out on **any** 401 without attempting a
refresh. Access tokens live **15 minutes** (`JWT_ACCESS_TTL_MIN`); refresh
tokens live 7 days and `POST /auth/refresh` exists. So a customer was bounced to
the login screen every quarter of an hour while holding a perfectly valid
refresh token.

Now uses the same shared-in-flight-promise pattern as the dashboard. That
sharing is load-bearing, not stylistic: `/auth/refresh` **rotates** the refresh
token, so two parallel 401s refreshing independently would have the second
present an already-spent token and hard-fail the session.

---

## The question that blocks everything else

> **Who is the customer-app for?**

The name says "customer", but the onboarding flow it contains collects
`business_name`, `industry`, `website_url` and calls
`POST /auth/register-business`. **That is an agency signing up, not a traveller.**

Two incompatible readings, and they share almost no screens:

**(A) It is agency self-serve signup.** The onboarding flow is already right,
and `/dashboard` should simply redirect to `agency-dashboard`. Remaining work is
small.

**(B) It is a traveller-facing app** — someone who took a GoGaga call and wants
to see their itinerary, pay, and message their agent. Then the entire existing
onboarding flow is **wrong** (a traveller has no business name or industry), and
essentially nothing is reusable except the visual shell.

Everything below assumes (B), because that is the only reading under which
Phase 7 is a real body of work. **If the answer is (A), stop — most of these
questions dissolve.**

---

## If it is traveller-facing

### 1. Authentication — the backend has no traveller identity

`ts_users` rows belong to a **business**. Every auth route issues a JWT carrying
`business_id`, and every travel endpoint scopes on it. A traveller is a
`travel_customers` row, which has no password, no login, and no token.

So: **how does a traveller authenticate?**

- Phone + OTP, with a new customer-scoped token type? (New backend work — a
  whole parallel auth path, plus a token claim the RBAC layer must learn to
  reject for agency endpoints.)
- A magic link per booking, no account at all? (Simplest; no session to manage.)
- Reuse `ts_users` with a `customer` role? (**Do not.** `require_role` treats
  unknown roles as lowest rank, but a traveller row inside the agency's user
  table is one join away from appearing in Team screens and access matrices.)

This is the single largest unknown. Nothing else can be specified until it is
settled.

### 2. What can a traveller actually see?

Every current endpoint is agency-scoped. Which of these get a customer-facing
counterpart, and what exactly does it expose?

- **Itinerary** — `travel_bookings` has the data, but no read route scoped to a
  customer.
- **Payment** — `payment_links` exists. Does the traveller open a link (no app
  needed) or pay in-app?
- **Messaging** — would need a traveller→agency inbound channel. None exists
  today; the WhatsApp integration is outbound-only, which is also why the
  24-hour session window is tracked in an in-process dict (`DEBT-10`).
- **Call history / recordings** — recordings are not provisioned at all
  (`B-P3-01`), and exposing a call recording to a customer has consent
  implications that are a legal question, not an engineering one.

### 3. Multi-tenancy — which agency's app is this?

A traveller of GoGaga and a traveller of a future Tenant B would both open this
app. How is the tenant resolved?

- Subdomain per agency?
- The booking reference / magic link carries it?
- One shared app with an agency picker? (Worst option — it leaks the tenant
  list.)

The backend fails closed here now: `_resolve_business_id` only falls back to
`PLIVO_BUSINESS_ID` when `business_phone_numbers` is empty. Any customer-app
design must not reintroduce a guessing path.

### 4. Branding

Does the app carry GoGaga's branding, the agency's, or neutral platform
branding? If per-agency, that needs a public (unauthenticated) branding endpoint
— and it must expose **only** name, logo and colours. A public endpoint keyed by
tenant is an enumeration surface; deciding what it may return is a security
decision, not a styling one.

### 5. Notifications

Push, email, or WhatsApp only? Push means service workers, a manifest, and a
token registry the backend does not currently have.

### 6. Offline / PWA?

A traveller opens this at an airport. Is offline access to a cached itinerary in
scope? That changes the storage architecture, not just a config flag.

---

## Recommended sequencing, once (A) or (B) is decided

If **(B)**, the order that avoids rework:

1. **Decide traveller auth** (§1). Everything depends on it.
2. Build the backend's customer-scoped read endpoints **first** — the FE Phase 1
   lesson was expensive: the live-call WebSocket was header-authenticated and
   therefore unusable from a browser, and nobody noticed because the only client
   that had ever exercised it was a Python script.
3. Then screens, in this order: itinerary view → payment → messaging.

If **(A)**, the work is roughly a day: point `/dashboard` at the agency app,
tidy the onboarding copy, and delete this document.

---

## Not blocking, but worth recording

- `customer-app` uses token keys `access_token` / `refresh_token`; the dashboard
  uses `gogaga_access_token` / `gogaga_refresh_token`. Fine while they are
  separate origins — **a collision the moment they share one.**
- `customer-app` depends on `zod`; `agency-dashboard` does not. Pick one
  validation story before the two apps diverge further.
- Two pre-existing `react-hooks/exhaustive-deps` warnings in `OtpPage` and
  `SuccessPage`. Left alone — they are in flow logic whose intent belongs to
  whoever owns the answer to §1.
