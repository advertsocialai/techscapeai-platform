# Codebase Analysis — Issues & Fix Plan
**Analysed:** 2026-08-10  
**Scope:** `api/` (FastAPI backend), `agency-dashboard/` (React TS), `customer-app/` (React TS), `supabase/migrations/`

---

## CRITICAL

### C1 — Weak default JWT secrets checked into config
**File:** `api/app/core/config.py:71-72`  
**Issue:** `JWT_SECRET = "change-me-in-prod"` and `JWT_REFRESH_SECRET = "change-me-too-in-prod"` are hardcoded defaults. If the production environment omits these vars, any attacker can forge valid JWTs for any user.  
**Fix:** Add a validator that raises at startup if these are still the default values in non-DEBUG mode.  
```python
# In Settings class, add:
from pydantic import model_validator

@model_validator(mode="after")
def check_secrets(self) -> "Settings":
    if not self.DEBUG:
        if self.JWT_SECRET == "change-me-in-prod":
            raise ValueError("JWT_SECRET must be set in production")
        if self.JWT_REFRESH_SECRET == "change-me-too-in-prod":
            raise ValueError("JWT_REFRESH_SECRET must be set in production")
    return self
```
**Risk if unfixed:** Full authentication bypass — anyone can sign JWTs for any user ID.

---

### C2 — Plaintext password persisted to localStorage during onboarding
**File:** `customer-app/src/features/onboarding/context/OnboardingContext.tsx:71`  
**Issue:** Every state update triggers `localStorage.setItem('klara_onboarding_state', JSON.stringify(state))`. The `state` object contains `password` (plaintext). Any XSS or devtools access on the client can read it.  
**Fix:** Exclude sensitive fields before persisting.  
```typescript
// Replace the useEffect with:
useEffect(() => {
  const { password, ...safeState } = state  // never persist password
  localStorage.setItem('klara_onboarding_state', JSON.stringify(safeState))
}, [state])
```
**Risk if unfixed:** Plaintext user password stored unencrypted in browser storage — recoverable via XSS or shared device.

---

### C3 — In-memory OTP & password-reset stores don't survive restarts / multi-worker
**File:** `api/app/routers/techscape/auth.py:99-124, 306-327`  
**Issue:** `_reset_tokens: dict[str, tuple[str, float]]` and `_otp_tokens` are module-level dicts. A server restart invalidates all pending resets/OTPs mid-flow. Under `--workers N` (uvicorn), each worker has its own copy — a token issued by worker-1 cannot be consumed by worker-2, causing ~50% failure rate.  
**Fix (short-term):** Store in Supabase table `ts_otp_tokens(email, code_hash, expires_at)` with an RLS-restricted service-role write. The existing Supabase admin client is already available. Alternatively, use Redis (already partially wired via `REDIS_URL`).  
**Fix (long-term):** Provision Redis and use `SETEX <token_hash> <ttl_seconds> <user_id>`.  
**Risk if unfixed:** Password resets and OTPs silently fail after deploys or under load.

---

## HIGH

### H1 — Frontend logout doesn't revoke the JWT on the server
**File:** `agency-dashboard/src/lib/auth.tsx:74-78`  
**Issue:** `logout()` only removes tokens from `localStorage`. It never calls `POST /api/techscape/v1/auth/logout`. The backend has a JTI blacklist (`blacklist_jti`), but it is never triggered from the frontend logout path. The access token stays valid until it expires (15 min default).  
**Fix:**
```typescript
async function logout() {
  try {
    await api.post('/techscape/v1/auth/logout')  // blacklists the JTI
  } catch {
    // ignore — token expires naturally
  }
  localStorage.removeItem('gogaga_access_token')
  localStorage.removeItem('gogaga_refresh_token')
  setMe(null)
}
```
Also update the function signature to `async`.  
**Risk if unfixed:** Stolen/intercepted tokens remain valid for up to 15 minutes after a user "logs out". Critical if a user logs out from a shared device.

---

### H2 — `get_supabase_admin()` creates a new client on every call (performance + connection waste)
**File:** `api/app/database/connection.py:22-30`  
**Issue:** `get_supabase()` is a singleton (module-level `_supabase_client`). `get_supabase_admin()` creates a fresh client on **every call**. `BusinessService.__init__` calls `get_supabase_admin()`, so every request that instantiates `BusinessService` (which is most of them) creates a new client with its own HTTP connection pool.  
**Fix:** Apply the same singleton pattern:
```python
_supabase_admin_client: Client | None = None

def get_supabase_admin() -> Client:
    global _supabase_admin_client
    if _supabase_admin_client is None:
        _supabase_admin_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _supabase_admin_client
```
**Risk if unfixed:** Under load, creates hundreds of HTTP clients/second; potential connection pool exhaustion.

---

### H3 — `increment_message_count` race condition
**File:** `api/app/services/techscape/business_service.py:200-208`  
**Issue:** Read-then-write without a transaction:
```python
used = int(biz.get("monthly_messages_used") or 0)
self.db.table("ts_businesses").update({"monthly_messages_used": used + n})
```
Two concurrent sends can read the same `used` value, both compute `used + 1`, and both write the same incremented value — losing one increment.  
**Fix:** Use a Supabase RPC or raw SQL to do an atomic increment:
```python
# Add to migration: CREATE FUNCTION increment_monthly_messages(p_id uuid, p_n int) ...
# Or use the PostgREST hint for atomic updates:
# Alternative quick fix: use rpc with a postgres function
self.db.rpc("increment_monthly_messages", {"p_business_id": str(business_id), "p_n": n}).execute()
```
Or add `monthly_messages_used = monthly_messages_used + n` via raw SQL using the service role.  
**Risk if unfixed:** Monthly message counts under-report under concurrent load; businesses may exceed their limits without enforcement.

---

### H4 — WebSocket path not proxied in agency-dashboard dev server
**File:** `agency-dashboard/vite.config.ts:8-13`  
**Issue:** The Vite proxy only covers `/api`. The live-call WebSocket endpoint is at `ws://localhost:8000/ws/calls/{id}` (no `/api` prefix — confirmed in `api/app/main.py:82`). In dev, all WS connections will fail with a 404 because Vite doesn't proxy `/ws`.  
**Fix:**
```typescript
server: {
  port: 5174,
  proxy: {
    '/api': { target: 'http://localhost:8000', changeOrigin: true, secure: false },
    '/ws':  { target: 'ws://localhost:8000',  changeOrigin: true, ws: true },
  },
},
```
**Risk if unfixed:** Live call feature is completely broken in local development.

---

### H5 — `_VALID_ROLES` in `_deps.py` missing `super_admin` and `agent`
**File:** `api/app/routers/techscape/_deps.py:29`  
**Issue:** `_VALID_ROLES = {"admin", "manager", "user", "viewer"}` is missing `"super_admin"` and `"agent"` — both valid in the DB (migration 0002). If any router calls `_deps.require_role("super_admin")`, it raises `ValueError: Unknown roles: {'super_admin'}` at startup/first call. The `core/deps.py` version correctly includes them.  
**Note:** Currently `users.py` imports `require_role` from `core/deps.py`, not `_deps.py`, so no crash yet. But the discrepancy is a landmine.  
**Fix:**
```python
_VALID_ROLES = {"admin", "manager", "user", "viewer", "super_admin", "agent"}
```
**Risk if unfixed:** Adding a route that uses `_deps.require_role("super_admin")` will crash silently or raise a 500 at first call.

---

## MEDIUM

### M1 — `update_user` silently drops None-valued fields (can't unset nullable columns)
**File:** `api/app/services/techscape/business_service.py:174-178`  
**Issue:**
```python
clean = {k: ... for k, v in fields.items() if v is not None}
```
PATCH requests cannot set a field to `null`. For example, removing a user's `branch_id` (moving them to unscoped) is impossible through the API because `{"branch_id": null}` is stripped.  
**Fix:** Use `exclude_unset=True` at the Pydantic model level (already done in the router), and preserve explicit `None` values in the service:
```python
clean = {k: (str(v) if k == "branch_id" and v is not None else v)
         for k, v in fields.items()}
# Remove the `if v is not None` filter
```
Use Pydantic's sentinel pattern (`__fields_set__`) to distinguish "not provided" from "explicitly null" if needed.

---

### M2 — `DashboardLayout` can crash when `me.user` is an empty object
**File:** `agency-dashboard/src/features/layout/DashboardLayout.tsx:60`  
**Issue:**
```tsx
{(me?.user.first_name?.[0] ?? me?.user.email[0] ?? '?').toUpperCase()}
```
When the `/me` endpoint is called via API-key auth, `_user` is `None`, the server returns `"user": {}`. Then `me.user.email` is `undefined`, and `undefined[0]` throws a TypeError crashing the sidebar.  
**Fix:** Add optional chaining:
```tsx
{(me?.user?.first_name?.[0] ?? me?.user?.email?.[0] ?? '?').toUpperCase()}
```
Also update `MeResponse.user` type to `BusinessUser | null` to reflect reality.

---

### M3 — Two `require_role` implementations with divergent semantics
**Files:** `api/app/core/deps.py:75-92` vs `api/app/routers/techscape/_deps.py:125-149`  
**Issue:** `core/deps.py` uses a **rank hierarchy** (admin ≥ manager ≥ user ≥ viewer). `_deps.py` uses **exact-match with admin bypass** (`role not in roles and role != "admin"`). They differ on: whether `super_admin` is accepted for `require_role("admin")`, and whether viewer can access manager routes. This dual-implementation is a maintenance trap.  
**Fix:** Remove `require_role` from `_deps.py` entirely. Route it to `core/deps.py`:
```python
# In _deps.py — remove the local require_role definition, re-export from core:
from app.core.deps import require_role  # noqa: F401
```
Audit all routers importing from `_deps` to ensure they're using the hierarchy version.

---

### M4 — Google OAuth and "Forgot password?" are non-functional in customer-app
**Files:** `customer-app/src/features/onboarding/pages/LoginPage.tsx:184, 217`  
**Issue 1:** "Forgot password?" is a `<span>` with `cursor:pointer` but no `onClick` or navigation — clicking it does nothing.  
**Issue 2:** "Continue with Google" button has no `onClick` handler — clicking does nothing.  
**Fix (Forgot password):** Link to a `/onboarding/forgot-password` route (needs to be created, or reuse agency-dashboard's flow via the same API endpoint `POST /auth/password/forgot`).  
**Fix (Google):** Either wire up the Google OAuth flow via `GET /api/techscape/v1/auth/oauth/google/url`, or replace the button with a `// TODO` comment and hide it until implemented. A non-functional button on a live login page is a UX defect.

---

### M5 — `run.sh` missing venv activation
**File:** `api/run.sh`  
**Issue:** The script calls `uvicorn` directly without activating the virtualenv. If the system doesn't have uvicorn on `PATH`, it silently fails or uses the wrong interpreter. The venv exists at `api/venv/`.  
**Fix:**
```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"   # ensure we're in api/
source venv/bin/activate
echo "Starting TechScape AI backend..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level info
```

---

### M6 — Onboarding flow has no step guard (users can skip steps)
**File:** `customer-app/src/App.tsx:33-46`  
**Issue:** All onboarding routes are directly accessible. A user can navigate to `/onboarding/terms` without completing personal-info, OTP, or address. The `onboarding_context` will have empty fields, and the final registration call will fail with missing required fields — but silently from the user's perspective.  
**Fix:** Add a `RequireStep` guard to each route that checks `onboardingCtx` state completeness:
```tsx
function RequireStep({ check, redirectTo, children }: { check: boolean; redirectTo: string; children: ReactNode }) {
  if (!check) return <Navigate to={redirectTo} replace />
  return <>{children}</>
}

// Example usage:
<Route path="/onboarding/otp" element={
  <RequireStep check={!!ctx.email && !!ctx.firstName} redirectTo="/onboarding/personal-info">
    <OtpPage />
  </RequireStep>
} />
```

---

## LOW / INFORMATIONAL

### L1 — `customer-app` dashboard is a placeholder
**File:** `customer-app/src/App.tsx:13-27`  
The `/dashboard` route renders a `🚀 Dashboard coming soon...` div. Not a bug, but this is the destination after successful login — first thing a customer sees. Track this as a feature gap.

---

### L2 — `customer-app` "Forgot password?" shows spinner emoji but is not a `<form>`
**File:** `customer-app/src/features/onboarding/pages/LoginPage.tsx:183-185`  
The "forgot" span has no submit handler. This also means pressing Enter in the password field won't trigger password reset — it uses `handleKeyDown → handleLogin` instead. Low impact but unexpected for keyboard users.

---

### L3 — `fastembed` pinned to old version with model download on first call in production
**File:** `api/requirements.txt:28`  
`fastembed==0.8.0` downloads the BAAI/bge-small-en-v1.5 model (~67MB) on first embed call if not already cached. In a cold-start container or serverless deployment, this adds 5–30 seconds to the first wiki search. The venv includes it, but a new deployment will re-download.  
**Fix:** Pre-download the model in the Docker build step:
```dockerfile
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"
```

---

### L4 — No tests
No test files were found anywhere in the repository (no `tests/`, no `*.test.ts`, no `*_test.py`). All verification relies on manual scripts (gogaga-verifier) and human review. This makes regressions invisible.  
**Fix:** Add at minimum:
- Backend: `pytest` unit tests for `security.py` (JWT issue/verify/blacklist), `business_service.py` (password hashing/auth), and critical auth endpoints.
- Frontend: Vitest or Jest smoke tests for `auth.tsx` (login/logout state transitions).

---

### L5 — Open infrastructure blockers still require external credentials
**File:** `BLOCKERS.md`  
11 open blockers requiring credentials (Plivo, Deepgram, Sarvam, ElevenLabs, Anthropic, Redis) before voice, AI agent, and production auth hardening can be tested. These are tracked in BLOCKERS.md and require action from the project owner.

---

## Summary Table

| ID | Severity | Area | One-liner |
|----|----------|------|-----------|
| C1 | CRITICAL | API · Config | Default JWT secrets accepted in production |
| C2 | CRITICAL | customer-app | Password stored plaintext in localStorage |
| C3 | CRITICAL | API · Auth | OTP/reset tokens lost on restart / multi-worker |
| H1 | HIGH | agency-dashboard | Logout doesn't blacklist JWT on server |
| H2 | HIGH | API · DB | Supabase admin client recreated on every request |
| H3 | HIGH | API · Billing | Message counter has read-modify-write race |
| H4 | HIGH | agency-dashboard | WebSocket /ws not proxied in dev |
| H5 | HIGH | API · Auth | `_VALID_ROLES` missing super_admin, agent |
| M1 | MEDIUM | API · Users | PATCH can't unset nullable fields |
| M2 | MEDIUM | agency-dashboard | DashboardLayout crashes if user is empty object |
| M3 | MEDIUM | API · Auth | Dual `require_role` with different semantics |
| M4 | MEDIUM | customer-app | Google OAuth + forgot-pw buttons non-functional |
| M5 | MEDIUM | API | `run.sh` doesn't activate venv |
| M6 | MEDIUM | customer-app | No step guards on onboarding flow |
| L1 | LOW | customer-app | Dashboard is a placeholder |
| L2 | LOW | customer-app | Forgot-pw span has no handler |
| L3 | LOW | API | fastembed downloads model at runtime in prod |
| L4 | LOW | All | No test coverage |
| L5 | INFO | Infra | 11 open blockers need external creds |

---

## Recommended Fix Order

1. **C1** → validator in Settings (30 min, zero-risk)  
2. **H1** → async logout in `auth.tsx` (15 min, zero-risk)  
3. **C2** → exclude password from localStorage persist (10 min, zero-risk)  
4. **H2** → singleton admin client (10 min, zero-risk)  
5. **H4** → add `/ws` to vite proxy (5 min, zero-risk)  
6. **H5** → add missing roles to `_VALID_ROLES` (5 min, zero-risk)  
7. **M2** → optional chaining in DashboardLayout (5 min, zero-risk)  
8. **M5** → fix `run.sh` (5 min, zero-risk)  
9. **H3** → atomic message count (requires DB migration)  
10. **C3** → move tokens to DB/Redis (requires migration + Redis provisioning)  
11. **M3** → unify require_role (requires audit of all routers)  
12. **M1** → nullable field patch (requires API contract update)  
13. **M4** → wire Google OAuth / forgot-pw in customer-app  
14. **M6** → onboarding step guards  
15. **L3** → add model pre-download to Dockerfile  
16. **L4** → add tests  
