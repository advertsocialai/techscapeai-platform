# Real API Inventory + GoGaga Target Contract

Prefixes (CONFIRMED at P1 recon — the router mount adds a `/v1` segment
that this doc previously missed): **`/api/techscape/v1/*`** and
**`/api/travel/v1/*`** (via `ts_router = APIRouter(prefix="/techscape/v1")`
/ `travel_router = APIRouter(prefix="/travel/v1")`, both then mounted
under `app.include_router(api_router, prefix="/api")`).

## techscape/* — EXISTING ~80 endpoints
auth.py (11): register-business ✅ login ✅ refresh ✅ me ✅ api-key/rotate ✅ password/forgot+reset ✅ otp/send+verify ✅ oauth/google url+callback ✅ logout ✅ (was already built pre-P1, contrary to this doc's old ❌)
_deps.py: require_business ✅ (JWT | X-API-Key | dev X-Business-ID; active check; rate limit; **P1 fixed**: now also rejects a deactivated user's token, not just an inactive business) · require_role 🔧 still buggy for techscape's own dual-auth model (untouched — out of scope, superseded for travel/GoGaga routes by `app/core/deps.py`'s hierarchical require_role instead of being patched in place)
users.py (P1, new): GET/POST '' · GET/PATCH/DELETE /{id} — branch-scoped (manager=own branch, super_admin/admin=all), role-elevation guarded, soft-delete=status:inactive
branches.py (P1, new): GET/POST '' · GET /{id} (+stats stub) — POST is super_admin-only
businesses.py: register, me · admin.py: aggregate-day, reset-monthly-counter
OUT OF SCOPE (never touch): workflows(14) templates(7) executions(7) integrations(6) contacts(6) analytics(5) webhooks(5) billing(4) gdpr(3) ai(6) send(1) demo(1)

## travel/* — EXISTING ~53 endpoints (extend)
wiki(5): GET/POST /wiki, /bulk, POST /search (ilike — P2 wires embeddings), DELETE ✅
leads(4): POST '' 201 · GET '' · GET /{id} · PUT /{id}/status ✅ → **P1 (partial)**: role-gated only (read=agent+, write=manager+; switched off `require_business` onto `core/deps.py`'s JWT-only hierarchy, same as wiki/users/branches). **NOT built**: "assigned only" row scoping — blocked on `travel_leads.assigned_agent`, which doesn't exist until P2's travel_leads extension. P2.5 adds PATCH reassign; P3 adds POST /search (vector).
catalog(8) itinerary(5) booking(5)+bookings(4) customer(5) on_ground(5) playbooks(7) franchisee(1) language(1) demo(2) ✅
inbound(1): POST /inbound/whatsapp ✅ dispatcher — calls LeadService directly, does NOT go through leads.py's router, so leads.py's P1 auth change doesn't affect it

## GoGaga additions (target, by phase)
P1 (DONE): POST /auth/logout · GET/POST /users · GET/PATCH/DELETE /users/{id} · GET/POST /branches · GET /branches/{id} · role-gating on travel/leads.py (assigned-only row scoping deferred to P2)
P2: travel_leads.assigned_agent + agent assigned-only scoping on leads.py · POST /webhook/{provider}/voice · WS /webhook/{provider}/stream · GET /calls/live · GET /calls/{id}/transcript · WS /ws/calls/{call_id}
P3: POST /calls/{id}/takeover · POST /leads/search
P4: POST /webhook/razorpay · POST+GET /payment-links · GET /dashboard/summary · GET /branches/{id}/stats (replaces the P1 stats stub — needs travel_calls/leads branch linkage) · GET /agents/{id}/stats · report schedule CRUD (if playbooks insufficient)

## Screens (28) ← endpoints: see blueprint plan; Mission Control/Empire/Dream Team wait on P4 aggregates.
