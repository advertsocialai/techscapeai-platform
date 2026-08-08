---
name: gogaga-frontend
description: Conventions, verified API/WS contracts, and reusable patterns for the GoGaga agency dashboard frontend (agency-dashboard/ — Vite + React 19 + TypeScript + TanStack Query + react-router-dom 7 + axios). ALWAYS use this skill when writing, editing, reviewing or planning ANY frontend code in agency-dashboard/ or customer-app/ — screens, hooks, API calls, WebSocket handling, RBAC gating, forms, currency display. Trigger on any mention of a screen ID (S0-S27), Mission Control, Live Call, Journey Board, Guest Story, takeover UI, payment link UI, follow-up ladder, or any FE Phase N task. Use even for one-line fixes.
---

# GoGaga Frontend Skill

The agency-facing dashboard. Built by EXTENDING `agency-dashboard/` — never a rewrite,
and never a new app.

## 0. The directory is `agency-dashboard/`, NOT `agency-app/`

Several loop prompts and the Vercel project's Root Directory setting both say
`agency-app`. **That directory has never existed.** The real one is
`agency-dashboard/`. This is not cosmetic — it is why the `agency-dashboard`
Vercel deployment has been failing with `NOW_SANDBOX_WORKER_ROOTDIR_NOT_EXIST`.
Build in `agency-dashboard/`; fixing the Vercel setting is a dashboard change, not
a code change.

## 1. Stack (verified from package.json, do not add without cause)

| Concern | Choice |
|---|---|
| Build | Vite 8 |
| UI | React 19 (⚠️ StrictMode double-invokes effects in dev — see §4) |
| Language | TypeScript ~6 |
| Routing | react-router-dom 7 |
| Server state | **@tanstack/react-query 5** — already a dependency; use it, do not hand-roll fetching-and-caching |
| HTTP | axios (single configured instance in `src/lib/api.ts`) |
| Class names | clsx |

There is no CSS framework, no component library, and no charting library as of
FE Phase 1. A charting choice is owed by FE Phase 5 — record it here when made.

## 2. Layout: feature-folders

```
src/
  lib/        api.ts (the axios instance + per-domain API objects), ws.ts
  types/      auth.ts, travel.ts, ws.ts
  hooks/      cross-feature hooks (useCallFeed, ...)
  features/   auth/ live-call/ mission-control/ layout/ playbooks/
              bookings/ guest-story/ journey-board/
```
One folder per feature area; a screen lives with its feature, not in a global
`pages/`.

## 3. API client — the conventions that actually matter

`src/lib/api.ts` exports **one configured axios instance** plus an object per
domain (`authApi`, `leadsApi`, `callsApi`, …). Follow the existing shape:

```ts
export const leadsApi = {
  list: (params?: {...}) => api.get<Lead[]>('/travel/v1/leads', { params }).then(r => r.data),
}
```

- `baseURL` is `/api`, so paths start at `/travel/v1/...` or `/techscape/v1/...`.
  **Writing `/api/travel/v1/...` double-prefixes and 404s.**
- Always `.then(r => r.data)` — callers never see the axios envelope.
- Auth is a request interceptor reading `gogaga_access_token` from localStorage.

### Token refresh — do not "simplify" this
The 401 interceptor refreshes via a **single shared in-flight promise**
(`refreshPromise`). This is load-bearing, not defensive style: the refresh token
**rotates on every use**, so two parallel 401s (Mission Control fires several
queries at once) would race, and the second call would present an
already-spent token and hard-fail the session. Keep the shared promise.

### Route prefixes are NOT uniform — verify before writing a path
Some backend routers mount with a prefix, others declare full paths themselves:

| Surface | Real path |
|---|---|
| packages | `/travel/v1/packages` |
| follow-ups | `/travel/v1/follow-ups` |
| activity log | `/travel/v1/activity-log` |
| cost/usage | `/travel/v1/analytics/cost` |
| **payments** | `/travel/v1/payment-links` *(router mounts with NO prefix)* |
| **reports** | `/travel/v1/reports/...` and `/travel/v1/report-schedules` *(no prefix)* |

To get ground truth rather than guessing, enumerate the server's real routes:
```bash
cd api && SUPABASE_URL=x SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_ANON_KEY=x \
  JWT_SECRET=y JWT_REFRESH_SECRET=z python -c "
import app.main as m
for r in sorted(m.app.routes, key=lambda x: getattr(x,'path','')):
    print(','.join(sorted(getattr(r,'methods',[]) or [])), getattr(r,'path',''))"
```
**A client path absent from that list is a bug.** Diff against it.

## 4. WebSocket layer — read this before touching real-time UI

`src/lib/ws.ts` + `src/hooks/useCallFeed.ts`. Endpoint: `/ws/calls/{call_id}`
(mounted at the app root with **no `/api` prefix**).

### The contract has three conflicting sources. The backend CODE wins.

| Source | Says |
|---|---|
| `api-conventions.md` | `transcript`, `whisper`, `call_status`, `sentiment` |
| **Backend code (authoritative)** | `transcript`, `call_status`, `sentiment`, **`suggestion`**, `takeover_state`, `summary` |
| FE loop prompts | adds `speaking`, `intent`, `event`, `extraction` |

Two things follow, and both have bitten already:

1. **`suggestion` vs `whisper`** — the doc specifies `whisper` with
   `{suggestion, confidence}`; the code emits `suggestion` with `{text, mode}`.
   Type the code's shape. Logged backend-side as `DEBT-05`.
2. **`speaking`, `intent`, `event`, `extraction` are NEVER emitted.** Any UI
   built against them renders permanently empty. Do not scaffold them as if
   they were live; if a spec asks for them, that is a backend gap to log, not a
   frontend feature to fake.

Also: `seq` is documented as monotonic-per-call for gap detection, but the
backend **hardcodes `seq: 1`**. Do not build gap detection on it — it would
silently mislead.

### Rules
- **Unknown `type` must be ignored, never crash.** Keep an `UnknownMessage`
  fallback in the union.
- **Every subscription needs teardown**, including any *pending reconnect timer*.
  A timer that fires after unmount is the classic leak here.
- **React 19 StrictMode double-invokes effects in dev.** A naive `useEffect`
  subscribe opens two sockets. Handle it, and verify by connection count — not
  by reading the code and assuming.
- Reconnect with **capped exponential backoff + jitter**. Never a tight loop.
- Surface connection status (`connecting | open | reconnecting | closed`) so
  screens can show a "reconnecting — data may be stale" banner. Losing messages
  during a gap is acceptable per the contract; **showing stale data as current
  is not.**

## 5. RBAC

Roles come from `MeResponse.user.role`: `admin | manager | user | viewer`
(the backend's stored values; its "admin tier" is stored as `manager` — see
`api/app/core/deps.py`). Gate in the UI as a *first* line of defence only.

> **The UI check is never the guarantee.** The server re-reads the user's row
> and ignores the token's role claim. A frontend role check improves UX; it does
> not make anything secure, and must never be described as if it does.

## 6. High-consequence actions — the confirmed-state pattern

Some actions have real-world effects: a **takeover** changes a live phone call,
a **payment link** moves money, a **WhatsApp send** messages a real person.

**Never render these as succeeded before the server confirms.** For takeover
specifically, the visual source of truth is the `takeover_state` WS broadcast,
not local optimistic state. Optimistic UI is a correctness bug here, not a UX
nicety — an operator who believes they have taken over a call, but has not, will
talk over an AI that is still speaking to a customer.

Optimistic UI **is** fine for low-consequence changes (dragging a lead between
kanban columns) — with correct rollback on failure.

Reserve an explicit confirmation dialog for the highest-consequence action in a
screen set (e.g. full takeover), not for every action — confirmation fatigue
defeats the purpose.

## 7. Money and currency

**Never render a bare amount.** Always amount + currency, together. The platform
is multi-branch and multi-currency (INR, plus USD/CAD for intl branches), and an
unlabelled number is a real business risk.

For historical rollups the backend converts using the **FX snapshot in effect at
the transaction's own timestamp**, never a live rate, so a report re-run days
later is identical. The UI must not re-derive or re-convert — display what the
server returns, labelled. If the server reports rows it could not convert, show
that explicitly; a silently short total is worse than an obviously incomplete one.

## 8. Loading and error states

Use **skeletons that match the eventual layout**, not spinners — a spinner tells
the user nothing about what is arriving. Every data surface needs three states:
loading, empty (with a reason), and error (with a retry). An empty state that
looks identical to a loading state is a bug.

## 9. Testing conventions that carry across phases

- **💰 / 💬** — building a payment or messaging UI never needs permission;
  *firing* a real charge or a real message during self-testing always does.
  Self-test against backend stub mode (`stub://` links, `whatsapp_outbox` rows)
  or a local mock. Never use live credentials that happen to be present.
- **🏢** — never onboard a real tenant or submit a real Reseller application.
  Test against the synthetic `regression-fixture-tenant-b` fixture.

## 10. Before writing code

- Endpoint shapes → read the router in `api/app/routers/travel/`, not a doc.
- WS message shapes → read the emitting service, not `api-conventions.md`.
- Backend behaviour/limits → the `gogaga-backend` skill.
- Known gaps → `BLOCKERS.md` at the repo root; check whether what you are about
  to build is already logged as blocked.
