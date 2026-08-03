# Real API Inventory + GoGaga Target Contract

Prefixes: /api/techscape/* and /api/travel/* (via app.include_router(api_router, prefix="/api")). Verify exact mount paths in routers/__init__.py during recon.

## techscape/* — EXISTING ~80 endpoints
auth.py (11): register-business ✅ login ✅ refresh ✅ me ✅ api-key/rotate ✅ password/forgot+reset ✅ otp/send+verify ✅ oauth/google url+callback ✅ — logout ❌ (P1 adds)
_deps.py: require_business ✅ (JWT | X-API-Key | dev X-Business-ID; active check; rate limit) · require_role 🔧 buggy (P1 fix)
businesses.py: register, me · admin.py: aggregate-day, reset-monthly-counter
OUT OF SCOPE (never touch): workflows(14) templates(7) executions(7) integrations(6) contacts(6) analytics(5) webhooks(5) billing(4) gdpr(3) ai(6) send(1) demo(1)

## travel/* — EXISTING ~53 endpoints (extend)
wiki(5): GET/POST /wiki, /bulk, POST /search (ilike — P2 wires embeddings), DELETE ✅
leads(4): POST '' 201 · GET '' · GET /{id} · PUT /{id}/status ✅ → P1 adds RBAC scoping ("assigned only"); P2.5 adds PATCH reassign; P3 adds POST /search (vector)
catalog(8) itinerary(5) booking(5)+bookings(4) customer(5) on_ground(5) playbooks(7) franchisee(1) language(1) demo(2) ✅
inbound(1): POST /inbound/whatsapp ✅ dispatcher

## GoGaga additions (target, by phase)
P1: POST /auth/logout · GET/POST /users · GET/PATCH/DELETE /users/{id} · GET/POST /branches · GET /branches/{id}
P2: POST /webhook/{provider}/voice · WS /webhook/{provider}/stream · GET /calls/live · GET /calls/{id}/transcript · WS /ws/calls/{call_id}
P3: POST /calls/{id}/takeover · POST /leads/search
P4: POST /webhook/razorpay · POST+GET /payment-links · GET /dashboard/summary · GET /branches/{id}/stats · GET /agents/{id}/stats · report schedule CRUD (if playbooks insufficient)

## Screens (28) ← endpoints: see blueprint plan; Mission Control/Empire/Dream Team wait on P4 aggregates.
