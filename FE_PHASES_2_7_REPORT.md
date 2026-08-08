# FE Phases 2–7 — Agency Dashboard

**Date:** 2026-08-08 · **Branch:** `Klara-ai` · **Directory:** `agency-dashboard/`

All six remaining UI phases built on the Phase 1 foundation. 14 screens across
15 navigation entries, plus customer-app discovery.

---

## What shipped

| Phase | Screens | Commit |
|---|---|---|
| 2 | Mission Control, Live Call Monitor, Live Transcript + takeover | `39805ce` |
| 3 | Journey Board kanban, Guest Story, search/filter, assign | `f9cc456` |
| 4 | Packages, Payment Links, WhatsApp, Follow-ups | `ebcfd49` |
| 5 | Reports, Cost & Revenue, Team, Activity Log | `c2de315` |
| 6 | AI Playbook config, Empire/branches, RBAC nav gating | `d4dfd2c` |
| 7 | customer-app discovery + scope questions | `6406f76` |

---

## The decisions worth defending

### Optimism is applied by consequence, not by convention

Three mutation patterns, chosen deliberately rather than for consistency:

| Action | Optimistic? | Why |
|---|---|---|
| Drag a lead between kanban columns | **Yes**, with rollback | Low-consequence and reversible; a round-trip wait makes the board feel broken |
| Assign a lead to an agent | **No** | Changes RBAC scoping — a false success leaves someone believing a colleague can see a lead they cannot |
| Takeover a live call | **Never** | An operator who wrongly believes they hold the call will talk over an AI that is still speaking to a customer |

Takeover's display comes from the `takeover_state` WebSocket broadcast, and
from nothing else — not local state, and not the POST response, because
`CallOut` carries no `takeover_state` field. In flight it shows an explicit
"requesting…"; with no broadcast received it disables the controls rather than
assuming `ai`.

### Stub mode is the primary content, not a footnote

Wherever the backend can be in stub mode, the screen leads with it:

- **Payment Links** — `gateway_mode` is the top banner. `stub://` URLs render as
  inert code, never as anchors, so they cannot be clicked and mistaken for live.
- **WhatsApp** — reports what actually happened rather than "sent". A stubbed
  row is recorded and transmitted to nobody but looks like success in every
  other field.
- **Cost** — `all_estimated` is a banner. Nothing is metered; Phase 2B never ran.
- **Reports** — when `is_constant` or `stub_derived` is set, the sentiment panel
  is **replaced** by an explanation. Showing an average of a constant with the
  caveat below it would be worse than showing nothing: someone would quote the
  number without the caveat.

### Gaps are stated on screen, not left as empty boxes

`DEBT-15`: the spec assumes ten WS message types; the backend publishes five.
`speaking`, `intent`, `event`, `extraction` and `whisper` have no publisher.
Rather than scaffolding four panels that would render permanently empty — which
an operator reads as "the call is quiet" — S11 lists them as unavailable with
the reason. Same for `B-P3-01`: takeover state changes are live, but audio
bridging is not provisioned, so clicking Monitor and hearing silence is
explained rather than mysterious.

### Money never appears bare

`formatMoney` requires a currency and there is deliberately no
`formatAmount(n)` — the missing function is the point. On the revenue rollup,
`complete` is read before `total`, and unconvertible rows get their own table
instead of being dropped: a short total that looks whole is worse than one that
is obviously partial. The UI never converts; the server uses the FX snapshot at
each transaction's own timestamp so a re-run gives the same answer.

### RBAC is labelled as what it is

Nav links carry a minimum role and hide below it. The type's comment says
plainly that this is a UX affordance and **not** access control — the server
re-reads the caller's row and ignores the token's role claim, so a hidden link
is still reachable by URL and still correctly refused there.

---

## Defects found and fixed along the way

Three were real, and none were in the phase specs:

1. **Memoisation defeated** (Phase 3) — the leads array was re-allocated every
   render, changing the deps of both `useMemo`s and silently defeating them.
2. **React anti-pattern** (Phase 6) — the AI config form seeded state from a
   fetch inside `useEffect`, which renders twice and can clobber an edit
   mid-keystroke. Replaced with a keyed child initialising `useState` from
   props. Caught by lint; fixed at the cause rather than suppressed.
3. **customer-app logged users out every 15 minutes** (Phase 7, `DEBT-16`) —
   the 401 interceptor never attempted a refresh, though access tokens live 15
   minutes, refresh tokens live 7 days, and `/auth/refresh` exists.

---

## Verification

| Check | Result |
|---|---|
| `agency-dashboard` — `tsc --noEmit` | exit 0 |
| `agency-dashboard` — `eslint` | exit 0, no warnings |
| `agency-dashboard` — `vite build` | 423 kB / 127 kB gzip |
| `customer-app` — `tsc`, `build` | exit 0 |
| `api` — `pytest` | **71 passed** |
| Nav audit | 15 links, 15 routes, **0 orphans, 0 dead links** |
| Client paths vs server routes | 68 checked, **0 mismatches** |

Routes intentionally absent from nav: two detail pages reached contextually
(`/journey-board/:leadId`, `/live-call/:callId`), four auth screens outside the
shell, and the catch-all.

---

## What is NOT verified

**There is no database in this sandbox.** Migrations `0009`–`0019` are written
and unapplied; the Supabase connector is unauthenticated in this session.

Verified: paths, types, auth channels, WS framing, RBAC reasoning, route
registration, build integrity. **Not verified: a single live round-trip.** Every
DB-touching endpoint returns 500 here. Nothing above should be read as "these
screens were seen working against real data".

Per the standing gates: **no real payment was created, no real WhatsApp message
was sent, and no tenant was onboarded.** Every money and messaging surface was
built and reasoned about against stub-mode contracts.

---

## Open, and owed to a human

| ID | What |
|---|---|
| `B-FE1-02` | Vercel `agency-dashboard` Root Directory → `agency-dashboard` |
| `B-FE1-03` | Vercel `techscapeai-platform` Root Directory → `api` |
| `B-FE7-01` | Is customer-app agency self-serve, or traveller-facing? |
| `B-FE7-02` | The backend has no traveller identity to authenticate against |
| `DEBT-15` | Five spec'd WS message types have no publisher |

The two Vercel items are settings changes, not code — I verified that Vercel's
own suggested fix for the second would fail at import, so the root-directory
change is the actual answer.

`B-FE7-01` blocks the whole of Phase 7 beyond discovery and cannot be resolved
by reading the codebase: `customer-app` is named for travellers but its
onboarding collects `business_name` and calls `register-business`, which is an
agency signing up. See `CUSTOMER_APP_SCOPE_QUESTIONS.md`.
