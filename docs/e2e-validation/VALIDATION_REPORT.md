# Klara-ai — Live End-to-End Validation Report

**Branch:** `Klara-ai` @ `2a87dec`
**Date:** 2026-09-02
**Method:** Playwright 1.62.1 (Chromium), run against the live Vercel branch deployments — not mocks, not local builds.
**Coverage:** 83 automated checks across all three surfaces.

| Result | Count |
|---|---|
| Passing | 55 |
| HIGH | 2 |
| BLOCKER | 26 |

Suite lives in [`e2e/`](../../e2e). Re-run instructions: [`e2e/README.md`](../../e2e/README.md).

---

## 1. Targets validated

| Surface | Live URL (branch preview) | Reachable |
|---|---|---|
| Techscape AI platform (API) | `techscapeai-platform-git-klara-ai-…vercel.app` | yes, but 500s on every route |
| Agency dashboard | `agency-dashboard-git-klara-ai-…vercel.app` | yes |
| Klara app (customer-app) | `klara-customer-app-git-klara-ai-…vercel.app` | yes |

All three previews sit behind **Vercel Deployment Protection (SSO)**. A plain request returns `302 → vercel.com/sso-api`, and a naive check that follows redirects gets `200` from *Vercel's login page* — which looks like a healthy app and is not. The suite defends against this explicitly (see §6).

Production aliases, for contrast:

| Alias | Status |
|---|---|
| `techscapeai-platform.vercel.app` | **500** `FUNCTION_INVOCATION_FAILED` |
| `agency-dashboard.vercel.app` | **401** (protected, no public access) |
| `stagingklara.techscapeai.in` | 200, but serving `main`, which is far behind `Klara-ai` |

---

## 2. Headline finding

> **No user can sign in on any of the three surfaces, because no reachable backend exists on this branch.**

Three *independent* breakages each sever the frontend from the API. Fixing one does not fix the others.

Everything downstream of login — all 18 agency dashboard features, all 3 traveller screens — is therefore **unreachable, and consequently unvalidated beyond its auth guard**. This report does not claim those features work; it claims they could not be exercised.

---

## 3. Root causes

### RC-1 — The API's dependencies are never installed (BLOCKER)

`api/pyproject.toml` declares a `[project]` table with **no `dependencies` key**. Vercel's Python build uses `uv`, and when a `pyproject.toml` is present it installs from that file and **ignores `requirements.txt`** — where all 36 real packages (including `fastapi`) actually live.

Build log for `dpl_HYajVVqTXfCDrJXpPm9i5gXy6ZBP`:

```
Installing required dependencies from pyproject.toml...
Compiling Python bytecode...
Build Completed in /vercel/output [2s]
```

Two seconds, and no package list — nothing was installed. At runtime the import of `fastapi` fails before the handler is reached, which is why the platform returns `FUNCTION_INVOCATION_FAILED` and why **no runtime logs exist**: the failure happens at module import, before any logging is configured.

**Evidence:** 23 of 23 probed endpoints return 500 — `/api/health`, `/openapi.json`, `/docs`, every auth entry point, every protected route.

The file's own comment states the intent — *"Dependencies intentionally stay in requirements.txt (also supported by the Vercel Python runtime)"*. That premise is what does not hold: `requirements.txt` is supported only when no `pyproject.toml` shadows it.

### RC-2 — The Klara app points at a Railway host that no longer exists (BLOCKER)

`customer-app/src/lib/api.ts` uses `VITE_API_URL`, set on the Vercel project to `https://techscapeai-platform-klara-dev.up.railway.app`. That host is gone:

```
GET https://techscapeai-platform-klara-dev.up.railway.app/api/health
→ 404 {"status":"error","code":404,"message":"Application not found"}
```

Railway's 404 carries no CORS headers, so the browser reports it as a CORS failure — which disguises a dead host as a configuration problem:

```
Access to XMLHttpRequest at '…up.railway.app/api/techscape/v1/auth/login'
from origin 'https://klara-customer-app-git-klara-ai-….vercel.app'
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header…
```

The repo's own `api/.env` points at a *second* Railway host, `techscapeai-platform-production.up.railway.app` — **also** `Application not found`. Both are dead.

To its credit, the login screen fails honestly rather than hanging: it renders *"Could not reach the server. Check your connection and try again."*

### RC-3 — Relative `/api` base + SPA catch-all rewrite (BLOCKER)

Both frontends ship a `vercel.json` containing:

```json
{ "rewrites": [ { "source": "/(.*)", "destination": "/index.html" } ] }
```

That rewrite is correct for SPA deep-linking but has no `/api` exclusion, and there is no rewrite pointing `/api` at the backend. So any code using a *relative* API base sends its requests to the static host itself:

| Caller | Base | Live result |
|---|---|---|
| `agency-dashboard/src/lib/api.ts` | `'/api'` | `POST /api/techscape/v1/auth/login` → **405** |
| `customer-app/src/lib/travellerApi.ts` | `'/api/travel/v1/me'` | `POST …/auth/request-otp` → **405** |

`405 Method Not Allowed` is the static host refusing a POST — the request never came near FastAPI.

Note this means the Klara app has **two different, separately broken** backend paths: onboarding/agency auth goes to Railway (RC-2), the traveller surface goes to the static host (RC-3).

---

## 4. Security gaps (both verified live, not inferred)

### SEC-1 — Plaintext password persisted to localStorage (HIGH)

`OnboardingContext` persists its whole state object — `password` field included — to `localStorage["klara_onboarding_state"]` on every change.

Verified live by completing step 1 and reading the key back: the probe password was present in cleartext. It is readable by any script on the origin and survives on shared or kiosk machines after signup. Tracked as **BLK-15**.

### SEC-2 — OTP step is bypassable from the client (HIGH)

`RequireStep` reads `otpVerified` from the same localStorage object. Setting it by hand walks straight onto `/onboarding/terms`:

```js
localStorage.setItem('klara_onboarding_state', JSON.stringify({
  email: 'forged@example.com', password: '…', otpVerified: true }))
// → /onboarding/terms renders
```

The component's own comment is candid that this is not a guarantee. The real gap is on the server: `RegisterBusinessIn` carries **no OTP field**, so the backend cannot check that an address was ever verified regardless of client behaviour. Tracked as **B-FE7-07**.

---

## 5. What is verified working

Routing and guards are in good shape — this is the strongest part of the branch.

| Behaviour | Result |
|---|---|
| Agency `RequireAuth` on all 18 feature routes | 18/18 correctly redirect anonymous → `/login` |
| Klara `RequireTraveller` on `/trip`, `/trip/payments`, `/trip/messages` | all redirect → `/trip/login` |
| Klara `RequireStep` on `/address`, `/otp`, `/terms` | all redirect → `/onboarding/personal-info` |
| `/` → `/onboarding/login`; `/dashboard` → `/trip` | correct |
| Public screens render with no uncaught JS | Klara S1/S2/S6 + Google callback + `/trip/login`; agency login/signup/forgot/reset |

No blank pages, no uncaught exceptions, and no console errors on any public screen other than the backend-connection failures described above.

---

## 6. A trap worth documenting

Vercel `_vercel_share` bypass tokens behave in two ways that will silently corrupt results:

1. **Only the most recently minted token is valid.** Minting a token for surface B revokes surface A's — including the cookie already exchanged for it. Surfaces must therefore be validated **one at a time**, each immediately after minting.
2. **A gated request still returns `200`** — Vercel's login page. An early run of this suite "passed" 15 Klara checks that were in fact measuring `vercel.com/login`.

The suite now writes the bypass outcome to `e2e/.auth/status.json`, and every spec calls `assertNotGated()` in `beforeAll`, so a gated surface fails loudly instead of reporting false green.

---

## 7. Fix order

Nothing else can be validated until a backend answers, so RC-1 comes first.

| # | Fix | Where | Unblocks |
|---|---|---|---|
| 1 | Move `requirements.txt` contents into `[project].dependencies`, **or** delete `api/pyproject.toml` and declare the entrypoint another way | `api/pyproject.toml` | the entire API (23 endpoints) |
| 2 | Point `VITE_API_URL` at the live API origin | Vercel env, `klara-customer-app` | Klara onboarding + agency-auth calls |
| 3 | Add an `/api` rewrite to the backend, or set an absolute base | `*/vercel.json`, `agency-dashboard/src/lib/api.ts`, `customer-app/src/lib/travellerApi.ts` | agency login, traveller OTP |
| 4 | Set CORS `allow_origins` to include both preview and production origins | `api/app/main.py` | browser calls, once 1–3 land |
| 5 | Stop persisting `password`; clear state on success | `OnboardingContext.tsx` | SEC-1 |
| 6 | Add a verification field to `RegisterBusinessIn` and enforce server-side | `api/.../auth` | SEC-2 |
| 7 | Re-run the suite; the 21 authenticated features become testable for the first time | `e2e/` | real feature validation |

**After step 7 the real work starts.** Every agency dashboard feature and every traveller screen is currently unproven — this run establishes only that they are correctly guarded, not that they function.
