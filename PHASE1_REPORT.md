# GoGaga Backend — Phase 1 Report

Autonomous loop run, 2026-08-03. Branch `Klara-ai`. Target: local Supabase
stack (`supabase_db_techscapeai-platform`, Postgres on `127.0.0.1:55322`) —
**not** a hosted cloud project, contrary to the gogaga-migrations skill's
general "production-shared" framing (recon deviation, see below).

## Completed tasks

### T0 — Recon
- Mapped `api/app/routers/{techscape,travel}` and `core/`. Found `POST
  /auth/refresh`, `POST /auth/logout` (jti blacklist), and a clean new
  `app/core/deps.py` (`get_current_user` + hierarchical `require_role`)
  **already built and already wired into `wiki.py`** from prior work —
  the "P1 fix require_role + logout" phase-gate items were already done
  before this loop started.
- Confirmed real mount prefixes are `/api/techscape/v1/*` and
  `/api/travel/v1/*` — the verifier's `regression_check.sh` assumption
  (`/api/techscape/*`, no `/v1`) was wrong; worked around via its
  `GOGAGA_LOGIN_PATH`/`GOGAGA_WIKI_PATH` env overrides rather than editing
  the script.
- `JWT_SECRET`/`JWT_REFRESH_SECRET` are the literal source-code dev
  defaults (`change-me-in-prod...`) — not sensitive, not overridden in
  `.env`.
- Created an isolated test business+admin via `POST /auth/register-business`
  (`regression-fixture@techscapeai.com` / `TestPass123!`) instead of using
  any real user — zero risk to existing data, and this fixture now doubles
  as the permanent "working test login" for future regression runs.
- Minted a token via `make_test_token.py` (using the project **venv**
  python — system `python3` lacks `pyjwt`) and confirmed the API accepts
  it (`GET /wiki` → 200) — the T0 critical gate.
- Baseline `regression_check.sh`: GREEN.

### T2 — Migration: `branches` table + `ts_users` scoping
File: `supabase/migrations/0002_branches_and_user_branch_scoping.sql`
(completed a pre-existing unapplied draft found in the working tree).
- New `branches` table (RLS enabled, `REVOKE ALL FROM anon, authenticated`
  added — the draft was missing this).
- `ts_users.branch_id` FK → `branches(id)` (nullable = unscoped).
- `ts_users_status_check` widened: `active/disabled` → `active/disabled/inactive`
  (soft-delete uses `'inactive'`).
- `ts_users_role_check` widened: added `super_admin`, `agent` alongside
  the 4 legacy values (`admin/manager/user/viewer`) — fully additive.
- Applied via `psql` against the local stack; SQL printed before execution.
- **RLS proof**: anon-key REST call to `branches` → `401
  {"code":"42501","message":"permission denied for table branches"}`.
- Regression: PASS after apply.
- `supabase/migrations/LOG.md` created and appended.

### T3 — Users reads (`GET /users`, `GET /users/{id}`)
File: `api/app/routers/techscape/users.py` (+ `business_service.py`,
`schemas/techscape.py`).
- Branch scoping: `super_admin`/`admin` (rank 4) see the whole business;
  `manager` (rank 3, branch-admin) is restricted to their own `branch_id`.
- Real per-role DB fixtures (not just token claims — `core/deps.py`
  re-fetches the actual DB row) confirmed: `GET /users` →
  super_admin 200, manager 200, agent 403, viewer 403.
- Out-of-branch `GET /users/{id}` → **404** for a branch-scoped manager,
  200 for super_admin (never 403 — no existence leak).
- Grep-verified `UserOut` never includes `password_hash`.

### T4 — Users writes (`POST`/`PATCH`/`DELETE /users`)
- `POST /users`: super_admin 201, manager 201, agent 403, viewer 403.
- Role-elevation guard: a manager attempting to create `role=manager` or
  `role=super_admin` → 403 ("Cannot create a user at or above your own
  role"). Same guard blocks role changes on `PATCH`.
- `DELETE /users/{id}`: gated to `super_admin`-rank only (manager → 403).
  Self-delete → 400. Soft-delete confirmed via direct `psql` read
  (`status='inactive'`), not just the 200 response.
- **Token invalidation chain, both RBAC systems**: after soft-delete, the
  deleted user's existing access token now fails.
  - On `core/deps.py`-gated routes (`/wiki`, `/users`, `/branches`): was
    already correctly returning 403 (`get_current_user` checks
    `status != active`).
  - On the legacy `require_business` (`techscape/_deps.py`, e.g.
    `/auth/me`): **was returning 200** — a real bug, `require_business`
    only checked the *business's* status, never the individual user's.
    Fixed (see Decisions). Re-verified: both paths now return 403.

### T5 — Branches
File: `api/app/routers/techscape/branches.py` (+ `branch_service.py`).
- `GET /branches`: all 4 roles → 200.
- `POST /branches`: super_admin → 201; manager/agent/viewer → 403 (only
  the top rank creates branches, per spec).
- `GET /branches/{id}`: returns the row + `stats: {"leads":0,"calls":0,
  "conversion_rate":0}` stub with a P4 comment (real aggregates need
  `travel_leads`/`travel_calls` linkage that doesn't exist until P2).

### T6 — Partial: RBAC-gated leads
Originally missing from this report entirely (caught by user review, not
self-caught). File: `api/app/routers/travel/leads.py`.

**What was built**: role gating consistent with `core/deps.py`'s
hierarchy, switched from the legacy business-only `require_business` to
`get_current_user`/`require_role` (same pattern as `wiki.py`/`users.py`/
`branches.py`). `GET` (list, `/{id}`) requires `agent`+ (rank≥2); `POST`
(ingest) and `PUT /{id}/status` require `manager`+ (rank≥3, == spec's
"admin+"). Business scoping now comes from the caller's own
`user["business_id"]` instead of the API-key-resolvable `require_business`
principal — this is a real (intentional) behavior change: leads endpoints
are now JWT-only, no more `X-API-Key` access, matching the JWT-only
convention every other Phase 1 route already uses.

**What's formally deferred to Phase 2**: assigned-only row scoping (an
agent should eventually see/act only on leads where
`assigned_agent == self`). `travel_leads.assigned_agent` doesn't exist —
it's a named P2 addition in `gogaga-backend/references/schema.md`. Building
row-level filtering against a column that doesn't exist yet would mean
redoing it once P2 adds it, so this phase stops at the coarse role gate:
any agent+ can read all of the business's leads, any manager+ can write
any of them. No per-row narrowing yet.

**Verification** (fresh isolated test business, cascade-cleaned after):
```
POST /leads   (write)  super=201  manager=201  agent=403  viewer=403
GET  /leads   (read)   super=200  manager=200  agent=200  viewer=403
GET  /leads/{id}       agent=200
PUT  /leads/{id}/status agent=403  manager=200
bad token -> 401 {"detail":"Invalid token"}
```
Regression: PASS before and after. Cleanup: 4 users + 3 leads
cascade-deleted via the isolated test business's `ts_businesses` row.

### T7 — Acceptance sweep
`access_matrix.py` as shipped cannot run against this repo (see Decisions
— it doesn't pass `--biz`/`--sub`, and this repo's RBAC is DB-row-based,
not token-claim-based, so a fix needs real per-role user ids anyway). Ran
an equivalent sweep by hand using the same real per-role fixtures from
T3-T5, against the corrected `matrix-spec.json` (fixed stale `/v1`-less
paths, a missing required `category` field on the wiki probe body, and
the `.test.local` email domain that `EmailStr` rejects as reserved):

```
METHOD  PATH                              super_admin        admin        agent       viewer
--------------------------------------------------------------------------------------------
GET     /api/travel/v1/wiki                200/200  P  200/200  P  200/200  P  200/200  P
POST    /api/travel/v1/wiki                201/201  P  201/201  P  403/403  P  403/403  P
GET     /api/techscape/v1/users            200/200  P  200/200  P  403/403  P  403/403  P
POST    /api/techscape/v1/users            201/201  P  201/201  P  403/403  P  403/403  P
GET     /api/techscape/v1/branches         200/200  P  200/200  P  200/200  P  200/200  P
POST    /api/techscape/v1/branches         201/201  P  403/403  P  403/403  P  403/403  P

ACCESS MATRIX: ALL PASS (24/24 cells)
```

Logout tested separately per role (each call invalidates that role's own
token, so it can't share a row with the table above):

| role | POST /auth/logout | reuse on GET /wiki after |
|---|---|---|
| super_admin | 200 | 401 |
| admin (manager) | 200 | 401 |
| agent | 200 | 401 |
| viewer | 200 | 401 |

All 10 test users, 5 branches, and 2 wiki rows created during this sweep
lived under one isolated test business (`Phase1 Test Fixture`) and were
removed via a single cascading `DELETE FROM ts_businesses WHERE id=...`
(counts verified before/after: 10/5/2 → 0/0/0). `cleanup_test_artifacts.py`
was not used as-is — its hardcoded markers (`travel_franchisees`,
`*@test.local`) don't match this repo's actual `branches` table or the
`techscapeai.com` email domain `EmailStr` requires; noted for a future fix
rather than silently broadening its patterns.

Final regression: **GREEN** (fresh fixture — the original test business
was cascade-deleted during cleanup, so `regression-fixture@techscapeai.com`
/ `TestPass123!` was created to replace it; this fixture is intended to
persist as the standing dev regression-check login).

## Blocked Items

**NONE.** No task hit the 3-attempt failure threshold; nothing was
reverted.

## Decisions made autonomously

1. **`branches` is a dedicated table, not `travel_franchisees`.**
   `gogaga-backend/references/schema.md` suggested reusing
   `travel_franchisees` as the default branch model. Recon found a
   pre-existing, unapplied draft migration that had already decided on a
   separate `branches` table, and `matrix-spec.json`'s expected body
   (`{"name","city"}`) matches that shape, not franchisees' richer schema
   (owner_name, onboarding, metadata). Kept the dedicated table —
   `travel_franchisees` is a distinct franchise-partner concept and
   overloading it would conflate two meanings.

2. **Soft-delete status value is `'inactive'`**, added to the CHECK
   constraint alongside the pre-existing `'disabled'` (kept for whatever
   else already relies on it). Matches the pre-existing draft migration's
   intent.

3. **Role-name collision resolved by reserving bare `"admin"` for its
   legacy meaning.** The existing (pre-loop) `core/deps.py` already
   mapped legacy `admin` → spec `super_admin` (both top rank). The spec
   also wants a distinct "admin" tier one rank down (branch-admin). Since
   the same `role` column can't hold two different ranks under one
   string, new branch-admin rows are stored with `role='manager'`
   (already valid, already the correct rank) rather than a colliding
   second meaning of `"admin"`. `super_admin` and `agent` are the two
   genuinely new literal values added by the migration; `admin` and
   `user` are reserved for pre-migration rows only. Documented in
   `core/deps.py`'s docstring and `users.py`.

4. **Fixed a real bug in `require_business`** (`techscape/_deps.py`) —
   it never checked the fetched user row's own `status`, only the
   business's, so a soft-deleted user's token kept working on
   `/auth/me` and any other route still gated by the legacy dependency.
   This directly broke the mandatory token-invalidation-chain check, so
   it was in-scope to fix (`_deps.py` is an explicit extension point).

5. **New users.py/branches.py mounted under `/api/techscape/v1/`**, not
   `/api/travel/v1/`, matching `matrix-spec.json`'s pre-existing
   assumption and treating user/branch management as techscape-platform
   concerns (owns `ts_users`/`ts_businesses`) rather than travel-domain
   ones.

6. **Test fixtures via `/auth/register-business`**, not real/existing
   users. Avoids touching the 6 pre-existing real admin accounts found
   in the DB entirely.

7. **`leads.py` switched from `require_business` to `get_current_user`/
   `require_role`** (T6, added after initial review) — same JWT-only
   pattern as `wiki.py`/`users.py`/`branches.py`. This drops `X-API-Key`
   access to the leads HTTP endpoints. Checked before making the change:
   `inbound_dispatcher.py` (the WhatsApp/webhook lead-creation path) calls
   `LeadService` directly and never goes through this router, so nothing
   that currently exists breaks.

## TODOs for Phase 2

- **Assigned-only leads scoping** (T6 remainder): `travel_leads` needs an
  `assigned_agent` FK column (named P2 work in `schema.md`) before an
  agent's `GET /leads` can be narrowed to their own rows. Today any
  agent+ sees the whole business's leads. Building it now would have
  meant redoing it once P2 adds the column.
- `access_matrix.py`'s `mint()` doesn't pass `--biz`/`--sub` and will
  always fail against this repo — needs either real per-role fixture
  user ids wired in, or a documented "this repo's RBAC is DB-row-based,
  mint per real user" caveat promoted from a comment into the script
  itself.
- `cleanup_test_artifacts.py`'s `TEST_MARKERS` still point at
  `travel_franchisees` and `*@test.local`; should be updated to `branches`
  and a real-domain pattern (e.g. `%-fixture@techscapeai.com`) now that
  P1 has established those conventions.
- Branch stats (`GET /branches/{id}`) are a stub (`{"leads":0,"calls":0,
  "conversion_rate":0}`) pending `travel_leads`/`travel_calls` gaining a
  `branch_id`/linkage in P2.
- `REDIS_URL` / Redis-backed jti blacklist noted as a P1 env-var TODO in
  `gogaga-backend/references/env-vars.md` — a local `gogaga-redis`
  container is already running (docker, port 6379) from earlier in this
  session but `core/security.py`'s blacklist is still the in-memory dict
  (works fine for this single-process dev server; wiring `REDIS_URL` in
  is a small follow-up, not attempted here since it wasn't blocking any
  P1 verification and touching the blacklist mechanism itself was out of
  this loop's stated scope).
- `role='user'` and `role='admin'` (bare) remain valid only for
  pre-migration rows; no backfill/rename was performed (additive-only
  per the migrations skill) — worth a deliberate one-time data migration
  in a later phase if the legacy names should be retired.

=== PHASE 1 COMPLETE ===

NO BLOCKERS
