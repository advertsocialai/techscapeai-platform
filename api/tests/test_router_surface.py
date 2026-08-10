"""
Router surface suite — every router module gets at least one SUCCESS path and
one FAILURE path exercised through the real app (fastapi TestClient), with all
Supabase clients routed to tests/fake_supabase.py (no network, no credentials).

Why this exists (COVERAGE_RULE.md): the pre-existing suite proved pure
functions and app assembly, but a router that assembles is not a router that
answers. This file proves, per module:
  * success — an authenticated request reaches the handler, runs its service
    code against the fake DB, and returns 2xx;
  * failure — the same module refuses a bad request (401 unauthenticated for
    protected surfaces; 4xx validation/signature errors for public ones).

Auth is supplied via app.dependency_overrides on the three real dependency
entry points (core.deps.get_current_user, techscape._deps.require_business,
core.deps.get_current_traveller). require_role() wrappers depend on those, so
role gates still execute against the injected admin user — they are not
bypassed, they are fed.
"""
from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from fake_supabase import FakeDB, install

BIZ = "b0000000-0000-0000-0000-0000000000b1"
USER_ID = "d0000000-0000-0000-0000-0000000000d1"
CUST_ID = "c0000000-0000-0000-0000-0000000000c1"
CALL_ID = "a0000000-0000-0000-0000-0000000000a1"

USER = {
    "id": USER_ID, "business_id": BIZ, "role": "admin", "status": "active",
    "email": "smoke@example.com", "first_name": "Smoke", "last_name": "Test",
    "branch_id": None,
}

BUSINESS = {
    "id": BIZ, "status": "active", "name": "Smoke Biz",
    "contact_email": "biz@example.com", "subscription_tier": "starter",
    "max_monthly_messages": 10000, "monthly_messages_used": 0,
    "timezone": "Asia/Kolkata",
}


def _fake_require_business(request=None):
    principal = {**BUSINESS, "_user": dict(USER)}
    if request is not None:
        request.state.principal = principal
    return principal


@pytest.fixture
def plain_client(monkeypatch):
    """No auth overrides — for proving the 401/4xx failure paths.

    The fake DB is still installed: several dependencies (require_business)
    construct a Supabase client BEFORE deciding the request is anonymous, and
    the fixture credentials make that construction itself blow up into a 500,
    which would mask the 401 under test."""
    import app.main as m
    from app.core import public_rate_limit as prl

    install(monkeypatch)
    prl._hits.clear()
    with TestClient(m.app, raise_server_exceptions=False) as c:
        yield c
    prl._hits.clear()


@pytest.fixture
def surface(monkeypatch):
    """(client, fake_db) with auth injected and all Supabase traffic faked."""
    import app.main as m
    from app.core import deps as core_deps
    from app.core import public_rate_limit as prl
    from app.routers.techscape import _deps as ts_deps

    db = install(monkeypatch)
    prl._hits.clear()

    def _biz_dep(request: Request):
        return _fake_require_business(request)

    m.app.dependency_overrides[core_deps.get_current_user] = lambda: dict(USER)
    m.app.dependency_overrides[ts_deps.require_business] = _biz_dep
    m.app.dependency_overrides[core_deps.get_current_traveller] = (
        lambda: {"customer_id": CUST_ID, "business_id": BIZ}
    )
    client = TestClient(m.app, raise_server_exceptions=False)
    yield client, db
    m.app.dependency_overrides.clear()
    prl._hits.clear()


# ─────────────────────────────────────────────────────────────────────────
# SUCCESS PATHS — one per router module.
# (module, method, path, request kwargs, table seeds)
# Every case must come back 2xx; anything else is a wiring regression.
# ─────────────────────────────────────────────────────────────────────────
SEED_CALL = {
    "travel_calls": [{
        "id": CALL_ID, "business_id": BIZ, "lead_id": None,
        "provider_sid": "uuid-1", "status": "active", "mode": "ai",
        "takeover_state": "ai", "assigned_agent": None,
        "started_at": "2026-08-10T05:00:00+00:00",
    }],
}

SUCCESS_CASES = [
    ("routers.health", "GET", "/api/health", {}, {}),
    ("routers.contact", "POST", "/api/contact",
     {"json": {"name": "Smoke Tester", "email": "smoke@example.com",
               "message": "Hello — this is a smoke-test enquiry."}}, {}),
    ("routers.newsletter", "POST", "/api/newsletter/subscribe",
     {"json": {"email": "smoke@example.com"}}, {}),
    # techscape
    ("techscape.admin", "POST", "/api/techscape/v1/admin/reset-monthly-counter",
     {}, {"ts_businesses": [BUSINESS]}),
    ("techscape.ai", "POST", "/api/techscape/v1/ai/classify-intent",
     {"json": {"text": "How much does the premium plan cost?"}}, {}),
    ("techscape.analytics", "GET", "/api/techscape/v1/analytics/overview",
     {}, {}),
    ("techscape.billing", "GET", "/api/techscape/v1/billing/current",
     {}, {"ts_businesses": [BUSINESS]}),
    ("techscape.branches", "GET", "/api/techscape/v1/branches", {}, {}),
    ("techscape.businesses", "GET", "/api/techscape/v1/businesses/me", {}, {}),
    ("techscape.contacts", "GET", "/api/techscape/v1/contacts", {}, {}),
    ("techscape.demo", "POST", "/api/techscape/v1/demo/seed-travel", {}, {}),
    ("techscape.executions", "GET", "/api/techscape/v1/executions", {}, {}),
    ("techscape.gdpr", "GET", "/api/techscape/v1/gdpr/export",
     {}, {"ts_businesses": [BUSINESS]}),
    ("techscape.integrations", "GET", "/api/techscape/v1/integrations", {}, {}),
    ("techscape.templates", "GET", "/api/techscape/v1/templates", {}, {}),
    ("techscape.users", "GET", "/api/techscape/v1/users", {}, {}),
    ("techscape.webhooks", "POST", "/api/techscape/v1/webhooks/twilio/status",
     {"data": {"MessageSid": "SM123", "MessageStatus": "delivered"}}, {}),
    ("techscape.workflows", "GET", "/api/techscape/v1/workflows", {}, {}),
    # travel
    ("travel.activity", "GET", "/api/travel/v1/activity-log", {}, {}),
    ("travel.ai_config", "POST", "/api/travel/v1/ai-config/seed", {}, {}),
    ("travel.booking", "GET", "/api/travel/v1/booking/guarantees", {}, {}),
    ("travel.bookings", "GET", "/api/travel/v1/bookings", {}, {}),
    ("travel.calls", "GET", "/api/travel/v1/calls/live", {}, {}),
    ("travel.catalog", "GET", "/api/travel/v1/catalog/destinations", {}, {}),
    ("travel.customer", "GET", "/api/travel/v1/customers", {}, {}),
    ("travel.demo", "POST", "/api/travel/v1/demo/seed-gogaga", {}, {}),
    ("travel.followups", "GET", "/api/travel/v1/follow-ups", {}, {}),
    ("travel.itinerary", "GET", "/api/travel/v1/itineraries", {}, {}),
    ("travel.language", "POST", "/api/travel/v1/language/translate",
     {"json": {"text": "hello", "source_lang": "en", "target_lang": "hi"}}, {}),
    ("travel.leads", "GET", "/api/travel/v1/leads", {}, {}),
    ("travel.on_ground", "GET", "/api/travel/v1/on-ground/issues", {}, {}),
    ("travel.packages", "GET", "/api/travel/v1/packages", {}, {}),
    ("travel.payments", "GET", "/api/travel/v1/payment-links", {}, {}),
    ("travel.playbooks", "GET", "/api/travel/v1/playbooks", {}, {}),
    ("travel.reports", "GET", "/api/travel/v1/reports/daily", {}, {}),
    ("travel.takeover", "GET", f"/api/travel/v1/calls/{CALL_ID}/events",
     {}, SEED_CALL),
    ("travel.traveller", "POST", "/api/travel/v1/me/auth/request-otp",
     {"json": {"email": "guest@example.com"}}, {}),
    ("travel.usage", "GET", "/api/travel/v1/analytics/cost/rate-card", {}, {}),
    ("travel.webhooks_voice", "POST", "/api/travel/v1/webhook/plivo/voice",
     {"data": {"CallUUID": "uuid-1", "From": "+919999999999",
               "To": "+918888888888"}}, {}),
    ("travel.whatsapp", "GET", "/api/travel/v1/whatsapp/outbox", {}, {}),
    ("travel.wiki", "GET", "/api/travel/v1/wiki", {}, {}),
]


@pytest.mark.parametrize(
    "module,method,path,kwargs,tables",
    SUCCESS_CASES, ids=[c[0] for c in SUCCESS_CASES])
def test_router_success_path(surface, module, method, path, kwargs, tables):
    client, db = surface
    db.tables.update(tables)
    r = client.request(method, path, **kwargs)
    assert 200 <= r.status_code < 300, (
        f"{module}: expected 2xx from {method} {path}, "
        f"got {r.status_code}: {r.text[:400]}"
    )


def test_franchisee_ask_success(surface, monkeypatch):
    """Wiki search is monkeypatched: the real path lazily loads a 67MB
    fastembed model, which a unit suite must not do. The router, agent and
    stub-answer path all still run for real."""
    from app.services.travel import franchisee_agent as fa
    monkeypatch.setattr(fa.WikiService, "search",
                        lambda self, *a, **k: [], raising=True)
    client, _ = surface
    r = client.post("/api/travel/v1/franchisee/ask",
                    json={"question": "What is the refund policy?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"] == "stub"        # no Anthropic key in this suite
    assert body["confident"] is False     # no wiki hits -> must not invent


def test_inbound_whatsapp_success(surface, monkeypatch):
    """Dispatcher boundary is mocked (it fans out to AI agents); the router,
    auth wiring and schema validation run for real."""
    from app.routers.travel import inbound as inbound_router

    async def _fake_dispatch(self, **kwargs):
        assert str(kwargs["business_id"]) == BIZ
        return {"intent": "general", "action": "replied",
                "response_text": "Namaste! How can I help?", "lead_id": None,
                "itinerary_id": None}

    monkeypatch.setattr(inbound_router.InboundDispatcher, "dispatch",
                        _fake_dispatch, raising=True)
    client, _ = surface
    r = client.post("/api/travel/v1/inbound/whatsapp",
                    json={"from_number": "+919999999999", "text": "hi"})
    assert r.status_code == 200, r.text


def test_direct_send_email_success(surface):
    """/send happy path: cap OK, no DNC contact, SendGrid in stub mode."""
    client, db = surface
    db.tables.update({"ts_businesses": [BUSINESS]})
    r = client.post("/api/techscape/v1/send", json={
        "business_id": BIZ, "channel": "email", "to_email": "lead@example.com",
        "subject": "Hello", "content": "Smoke test body",
    })
    assert 200 <= r.status_code < 300, r.text


# ─────────────────────────────────────────────────────────────────────────
# FAILURE PATHS
# ─────────────────────────────────────────────────────────────────────────
UNAUTH_CASES = [
    ("techscape.admin", "POST", "/api/techscape/v1/admin/reset-monthly-counter"),
    ("techscape.ai", "POST", "/api/techscape/v1/ai/classify-intent"),
    ("techscape.analytics", "GET", "/api/techscape/v1/analytics/overview"),
    ("techscape.auth", "GET", "/api/techscape/v1/auth/me"),
    ("techscape.billing", "GET", "/api/techscape/v1/billing/current"),
    ("techscape.branches", "GET", "/api/techscape/v1/branches"),
    ("techscape.businesses", "GET", "/api/techscape/v1/businesses/me"),
    ("techscape.contacts", "GET", "/api/techscape/v1/contacts"),
    ("techscape.demo", "POST", "/api/techscape/v1/demo/seed-travel"),
    ("techscape.executions", "GET", "/api/techscape/v1/executions"),
    ("techscape.gdpr", "GET", "/api/techscape/v1/gdpr/export"),
    ("techscape.integrations", "GET", "/api/techscape/v1/integrations"),
    ("techscape.send", "POST", "/api/techscape/v1/send"),
    ("techscape.templates", "GET", "/api/techscape/v1/templates"),
    ("techscape.users", "GET", "/api/techscape/v1/users"),
    ("techscape.workflows", "GET", "/api/techscape/v1/workflows"),
    ("travel.activity", "GET", "/api/travel/v1/activity-log"),
    ("travel.ai_config", "GET", "/api/travel/v1/ai-config"),
    ("travel.booking", "GET", "/api/travel/v1/booking/guarantees"),
    ("travel.bookings", "GET", "/api/travel/v1/bookings"),
    ("travel.calls", "GET", "/api/travel/v1/calls/live"),
    ("travel.catalog", "GET", "/api/travel/v1/catalog/destinations"),
    ("travel.customer", "GET", "/api/travel/v1/customers"),
    ("travel.demo", "POST", "/api/travel/v1/demo/seed-gogaga"),
    ("travel.followups", "GET", "/api/travel/v1/follow-ups"),
    ("travel.franchisee", "POST", "/api/travel/v1/franchisee/ask"),
    ("travel.inbound", "POST", "/api/travel/v1/inbound/whatsapp"),
    ("travel.itinerary", "GET", "/api/travel/v1/itineraries"),
    ("travel.language", "POST", "/api/travel/v1/language/translate"),
    ("travel.leads", "GET", "/api/travel/v1/leads"),
    ("travel.on_ground", "GET", "/api/travel/v1/on-ground/issues"),
    ("travel.packages", "GET", "/api/travel/v1/packages"),
    ("travel.payments", "GET", "/api/travel/v1/payment-links"),
    # NOTE: GET /playbooks (the registry list) is deliberately public — the
    # dispatch/runs surface is the protected one.
    ("travel.playbooks", "GET", "/api/travel/v1/playbooks/runs"),
    ("travel.reports", "GET", "/api/travel/v1/reports/daily"),
    ("travel.takeover", "POST", f"/api/travel/v1/calls/{CALL_ID}/takeover/monitor"),
    ("travel.traveller", "GET", "/api/travel/v1/me/trip"),
    ("travel.usage", "GET", "/api/travel/v1/analytics/cost"),
    ("travel.whatsapp", "GET", "/api/travel/v1/whatsapp/outbox"),
    ("travel.wiki", "GET", "/api/travel/v1/wiki"),
]


@pytest.mark.parametrize("module,method,path", UNAUTH_CASES,
                         ids=[c[0] for c in UNAUTH_CASES])
def test_router_rejects_unauthenticated(plain_client, module, method, path):
    r = plain_client.request(method, path)
    assert r.status_code == 401, (
        f"{module}: {method} {path} without credentials must 401, "
        f"got {r.status_code}: {r.text[:200]}"
    )


def test_health_failure_path(plain_client):
    # health has no auth and no body; the failure it can produce is 405.
    assert plain_client.post("/api/health").status_code == 405


def test_contact_rejects_invalid_body(plain_client):
    r = plain_client.post("/api/contact", json={"email": "not-an-email"})
    assert r.status_code == 422


def test_newsletter_rejects_invalid_email(plain_client):
    r = plain_client.post("/api/newsletter/subscribe",
                          json={"email": "nope"})
    assert r.status_code == 422


def test_twilio_webhook_fails_open_only_without_secret(plain_client, monkeypatch):
    """DEBT: webhook auth fails OPEN when no secret is configured (documented
    in gogaga-backend skill). This pins the half that must never regress:
    WITH a secret configured, an unsigned POST is rejected."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "TWILIO_WEBHOOK_AUTH_TOKEN", "shh", raising=False)
    r = plain_client.post("/api/techscape/v1/webhooks/twilio/status",
                          data={"MessageSid": "SM123", "MessageStatus": "delivered"})
    assert r.status_code in (401, 403), r.text


def test_razorpay_webhook_fails_closed_without_signature(plain_client):
    r = plain_client.post("/api/travel/v1/webhook/razorpay",
                          json={"event": "payment_link.paid"})
    assert r.status_code == 403, (
        f"payments webhook must fail CLOSED (403) when unsigned, got {r.status_code}"
    )


def test_voice_webhook_rejects_unknown_provider(plain_client):
    r = plain_client.post("/api/travel/v1/webhook/exotel/voice",
                          data={"CallUUID": "x"})
    assert r.status_code == 404
