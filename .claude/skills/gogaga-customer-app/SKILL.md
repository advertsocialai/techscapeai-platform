---
name: gogaga-customer-app
description: "Conventions for the TRAVELLER-facing customer-app (customer-app/ — Vite + React 19 + TypeScript, same base stack as the dashboard but a completely different identity/auth model). ALWAYS use this skill when writing, editing, reviewing, or planning ANY code in customer-app/ — OTP login, /me/* trip screens, payment-link viewing, WhatsApp opt-in, onboarding. Trigger on any mention of "traveller", "customer-app", "OTP login", "/me/", Klara onboarding, or a screen under customer-app/src/features/. Do NOT use gogaga-frontend's RBAC/role patterns here — travellers are not ts_users and have no roles. Use even for one-line fixes."
---

# GoGaga Customer App Skill (traveller-facing surface)

`customer-app/` looks like a sibling of `agency-dashboard/` (same Vite/React 19/TS/TanStack Query/axios stack) but its **identity model is deliberately separate and simpler**. Do not carry over `gogaga-frontend` or `gogaga-backend` RBAC assumptions here — that's the single most common mistake when extending this app.

## 1. Travellers are not `ts_users` — ever

- Travellers authenticate against `travel_customer_profiles` via OTP (`features/onboarding/pages/OtpPage.tsx` + backend OTP verify endpoint), **not** the `ts_users`/business-login flow that `gogaga-backend`/`gogaga-frontend` describe.
- The resulting JWT carries `role: "traveller"`, is scoped by `(business_id, email)`, has a **60-minute TTL and NO refresh token** (deliberately — re-OTP on expiry rather than silent refresh; this is a design choice, not a gap. Don't "fix" it by adding a refresh flow without checking with Gowtham first).
- Never join a traveller session to `ts_users`, `ts_businesses` roles, or any RBAC-gated endpoint. The two identity worlds are kept one join away from each other on purpose — see `BLOCKERS.md` note on this: a traveller token must 401 on every `/leads`, `/packages`, `/team`, etc. staff route, and an agency staff token must 401 on every `/me/*` route. Any change here needs both-direction proof (see §4).

## 2. API surface this app talks to

- All traveller reads/writes go through `/api/travel/v1/me/*` — never call a non-`/me/` travel endpoint from this app, even if it looks convenient (e.g. don't call `/leads/{id}` directly even if you have the id — that's a staff-scoped endpoint and will 401 correctly, which is the point, not a bug to route around).
- Payment links: `/me/payment-links/*` shows the traveller their own link state (created→sent→viewed→paid); this app **never creates or triggers** a payment link — that's an agency-staff action from the dashboard, gated by `gogaga-money-and-messages`.
- WhatsApp opt-in/consent state is read-only here too.

## 3. UX rules specific to this app

- This is a customer-facing surface for a travel agency's end customers — copy tone is warm/reassuring, not operational. Avoid dashboard-style jargon (no "lead", "qualification", "franchisee" language ever reaches this UI — map internal terms to customer language, e.g. lead → "your enquiry", franchisee → the agency's own brand name).
- Currency/number formatting must respect `fx_rate_at` snapshots the same way the dashboard does (see `gogaga-frontend` §currency) — a traveller must never see a price that silently re-prices between page loads.
- No RBAC-gated UI branches exist in this app (there's only one "role"). If you find yourself writing `if (role === ...)` in `customer-app/`, stop — that's a sign the code was copy-pasted from the dashboard and needs the branch removed, not conditionally rendered.

## 4. Verification for any change here

Because the two-identity separation is a security property, not just a UX one, prove **both directions** whenever touching auth boundaries, not just the happy path:
1. Real traveller OTP login → `/me/trip` → 200 with only that traveller's own data (no cross-tenant, no cross-traveller leakage).
2. Traveller token against a staff route (`/leads`, `/team`, any `techscape/` or non-`/me/` `travel/` route) → 401.
3. Staff (agency) token against `/me/*` → 401.
4. Cross-tenant: traveller token from business A against business A's own `/me/*` succeeds; confirm no business-B row is ever reachable by id-guessing (IDOR check) — travel_customer_profiles rows must be scoped by `(business_id, email)` in every query, not just at login.

Use `gogaga-verifier`'s token-minting script as the base and mint traveller-role tokens the same way, not staff tokens with a role string overridden — the claim shapes differ (no `biz`-only + role hierarchy; traveller claims are `{sub, business_id, email, role:"traveller", type:"access", exp}`).

## 5. Known gaps (check `BLOCKERS.md`/`SPEC_GAP_ANALYSIS.md` before assuming these are stale)

- No refresh flow (intentional, see §1) but also currently **no graceful re-OTP prompt** on 401 mid-session — a traveller whose 60-min token expires mid-scroll gets a raw failed request today, not a "please verify again" prompt. Worth a small UX fix.
- Multi-agency branding resolution (which agency's traveller a given customer-app deploy serves — subdomain vs. deep link vs. default) is a decision debt (`B-FE7-08`), not yet finalized platform-wide.
