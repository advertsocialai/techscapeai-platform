# FE Phase 1 — Foundation

**Date:** 2026-08-08 · **Branch:** `Klara-ai` · **Directory:** `agency-dashboard/`

Phase 1 was not in the original FE plan. It was created because all six queued
FE phases hit a hard stop, and building screens on top of that stop would have
produced work that could not run.

---

## Why this phase exists

Three things blocked every queued FE phase:

1. **`agency-app/` has never existed.** Every FE loop prompt named it, and so
   does the Vercel project's Root Directory setting — which is why that
   deployment fails with `NOW_SANDBOX_WORKER_ROOTDIR_NOT_EXIST`. The real
   directory is `agency-dashboard/`.
2. **No WebSocket layer at all.** Phases 2 and 3 are almost entirely real-time
   screens.
3. **No `gogaga-frontend` skill**, so every phase would have re-derived the
   same contracts from scratch and re-made the same mistakes.

All three are now cleared.

---

## The finding that mattered

**The live call feed could never have worked from a browser.**

`/ws/calls/{call_id}` depended on `get_current_user`, which reads the
`Authorization` header and nothing else. The browser `WebSocket` constructor
cannot set request headers — there is no option for it and no fetch-style
escape hatch. Every dashboard handshake would have been rejected at the HTTP
layer before `.accept()`.

What makes this worse than a plain 401: a rejected WebSocket handshake reaches
browser JavaScript as close code `1006` with no reason string — identical to a
dropped network connection. A naive client retries it forever. The screen shows
a spinner that never resolves and a console that says nothing useful.

It looked correct because it *was* correct against the client it was verified
with: `gogaga-verifier/scripts/ws_probe.py` uses
`websockets.connect(url, additional_headers=...)`, a Python-only capability.
The route comment even cites that convention approvingly.

### The fix

`get_current_user_ws` (`api/app/core/deps.py`) accepts three channels:

| Channel | Browser-safe | Notes |
|---|---|---|
| `Sec-WebSocket-Protocol` — `['bearer', token]` | ✅ **default** | The constructor *can* set this |
| `Authorization: Bearer <jwt>` | ❌ | Retained so `ws_probe.py` does not regress |
| `?token=<jwt>` | ✅ | Last resort — leaks the JWT into access logs and Referer |

The subprotocol is preferred over the more common `?token=` because query
strings are written to access logs, proxy logs and browser history, where a
captured access token outlives its own expiry as a stolen credential.

Two details that are load-bearing rather than stylistic:

- **The server must echo the subprotocol on `accept()`.** RFC 6455 says a
  browser silently drops any connection whose offered subprotocol the server
  did not echo. Without the echo the server believes it accepted and the client
  sees a mystery disconnect — so there is a test pinning it.
- **It raises `WebSocketException`, not `HTTPException`.** A WebSocket scope has
  no way to send an HTTP response; raising `HTTPException` makes Starlette
  attempt one and fail confusingly instead of closing cleanly with 1008.

---

## Delivered

### Backend
| File | Change |
|---|---|
| `api/app/core/deps.py` | `get_current_user_ws`, `ws_accept_subprotocol`, `_user_from_token` extracted from `get_current_user` |
| `api/app/routers/travel/calls.py` | WS route switched to the new dependency; echoes the subprotocol on accept |
| `api/tests/test_ws_auth.py` | 10 unit tests on token extraction across all three channels + malformed offers |
| `api/tests/test_ws_handshake_live.py` | 5 tests through the real ASGI app, including a browser-shaped handshake with no Authorization header |

### Frontend
| File | Purpose |
|---|---|
| `src/lib/api.ts` | 12 new API groups (`callsApi`, `takeoverApi`, `packagesApi`, `paymentsApi`, `whatsappApi`, `reportsApi`, `followUpsApi`, `activityApi`, `usageApi`, `aiConfigApi`, `usersApi`, `branchesApi`) |
| `src/types/ws.ts` | The message union, typed off the publisher call sites |
| `src/lib/ws.ts` | Connection manager: backoff+jitter, complete teardown, StrictMode-safe sharing, subprotocol auth |
| `src/hooks/useCallFeed.ts` | React binding with connection status |
| `src/lib/rbac.ts` | Role hierarchy + the spec↔stored vocabulary mapping |
| `src/lib/errors.ts` | `errorMessage()` — prefers the backend's `detail` over the axios message |
| `src/lib/money.ts` | Currency formatting; **there is deliberately no `formatAmount(n)`** |
| `src/components/DataState.tsx` | Skeletons, empty-with-reason, error-with-retry |
| `src/components/RequireRole.tsx` | Role gating + `NoAccess` fallback |

---

## Verification

| Check | Result |
|---|---|
| `pytest api/tests/` | **71 passed** (was 56) |
| `npx tsc --noEmit -p tsconfig.app.json` | exit 0 |
| `npm run lint` | exit 0 |
| Client paths vs real server routes | **68 checked, 0 mismatches** (195 routes enumerated from the live app object) |
| WS backoff / teardown / unknown-frame / StrictMode | all pass, driven with a fake socket + fake clock |

Two of these were built to be non-vacuous on purpose:

- **The handshake tests have a control run.** Reverting the route to
  `get_current_user` makes 4 of the 5 fail. Without that check, "the test
  passes" would not have distinguished a working fix from a test that asserts
  nothing.
- **The teardown test also has a control**, proving the reconnect timer really
  does fire when `close()` isn't called — otherwise "no second socket opened"
  proves nothing. StrictMode safety is verified by counting socket
  constructions, not by reading the code.

---

## What is NOT verified, and cannot be here

**There is no database in this sandbox.** Migrations `0009`–`0019` are written
and unapplied; the Supabase MCP connector is unauthenticated in this session.

So: paths, types, auth channels, WS framing, RBAC reasoning and route
registration are all verified. **A genuine live round-trip is not.** Every
DB-touching endpoint returns 500 here. Nothing in this report should be read as
"the dashboard was seen working against real data".

---

## Findings logged

| ID | Summary |
|---|---|
| `B-FE1-01` | WS handshake auth — **resolved this sprint** |
| `DEBT-13` | `TakeoverState` declared in two type files |
| `DEBT-14` | `vite.config.ts` proxies `/api` only, not `/ws` |
| `DEBT-15` | 5 WS message types are emitted; the FE specs assume 10 |

`DEBT-15` is the one that affects planning. The backend emits exactly
`transcript`, `call_status`, `sentiment`, `suggestion`, `takeover_state`. The
FE Phase 2 spec additionally assumes `speaking`, `intent`, `event`,
`extraction`, and `api-conventions.md` assumes `whisper` — **no publisher emits
any of them.** UI built against them renders permanently empty, so parts of the
Phase 2 spec need either a backend publisher or a scope cut before they can be
built honestly. The `gogaga-frontend` skill previously listed `summary` as
emitted; that was also wrong and is now corrected.

Related: `seq` is documented as monotonic for gap detection but is hardcoded
`1`, so gap detection built on it would silently mislead.

---

## Next

FE Phase 2 (S0 Mission Control, S10 Live Call Monitor, S11 Live Transcript) is
now unblocked — its real-time surface can actually connect. Phases 3–7 remain
queued and unstarted.
