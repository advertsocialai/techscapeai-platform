"""
Money-path tests: the payment-link status machine and the Razorpay/stub
webhook, exercised through the REAL routes (TestClient + fake Supabase).

Why these specific claims are pinned:
  * the machine is forward-only — nothing can un-pay a paid link (a replayed
    or out-of-order webhook must not demote status);
  * the webhook fails CLOSED — no signature, no state change (DEBT-12 records
    that this is deliberately the opposite of the messaging webhooks);
  * a verified-but-unactionable webhook returns 200 so the gateway does not
    retry-storm, but applies nothing.

The stub gateway signs with the SAME HMAC-SHA256-hex scheme as live Razorpay
(services/payments/stub_gateway.py), so the route under test is the
production route, not a parallel test-only path.
"""
from __future__ import annotations

import json

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from fake_supabase import install
from app.services.payments.base import (
    PAYMENT_LINK_STATUSES,
    can_transition,
)
from app.services.payments.stub_gateway import StubGateway

BIZ = "b0000000-0000-0000-0000-0000000000b1"
USER_ID = "d0000000-0000-0000-0000-0000000000d1"
LINK_ID = "e0000000-0000-0000-0000-0000000000e1"

USER = {"id": USER_ID, "business_id": BIZ, "role": "admin", "status": "active",
        "email": "agent@example.com", "branch_id": None}


def _link_row(status="created", gateway_link_id="plink_stub_x"):
    return {
        "id": LINK_ID, "business_id": BIZ, "lead_id": None, "package_id": None,
        "amount": "15000.00", "currency": "INR", "gateway": "stub",
        "status": status, "gateway_link_id": gateway_link_id,
        "gateway_link_url": f"stub://pay/{gateway_link_id}",
        "expiry_at": None, "created_by": USER_ID,
    }


@pytest.fixture
def client(monkeypatch):
    import app.main as m
    from app.core import deps as core_deps

    db = install(monkeypatch)
    m.app.dependency_overrides[core_deps.get_current_user] = lambda: dict(USER)
    yield TestClient(m.app, raise_server_exceptions=False), db
    m.app.dependency_overrides.clear()


# ── The pure machine, exhaustively ────────────────────────────────────────
def test_status_machine_is_forward_only_everywhere():
    legal = {
        ("created", "sent"), ("created", "viewed"), ("created", "paid"),
        ("created", "expired"),
        ("sent", "viewed"), ("sent", "paid"), ("sent", "expired"),
        ("viewed", "paid"), ("viewed", "expired"),
    }
    for cur in PAYMENT_LINK_STATUSES:
        for tgt in PAYMENT_LINK_STATUSES:
            assert can_transition(cur, tgt) == ((cur, tgt) in legal), (cur, tgt)
    # terminal states allow nothing — money moved or link dead
    assert not any(can_transition("paid", t) for t in PAYMENT_LINK_STATUSES)
    assert not any(can_transition("expired", t) for t in PAYMENT_LINK_STATUSES)
    # unknown states are refused, not crashed on
    assert can_transition("banana", "paid") is False
    assert can_transition("created", "banana") is False


# ── Route: create ─────────────────────────────────────────────────────────
def test_create_stub_link_returns_row_with_stub_url(client):
    c, db = client
    r = c.post("/api/travel/v1/payment-links", json={
        "amount": "15000.00", "currency": "INR", "gateway": "stub",
        "description": "Deposit for Bali honeymoon",
    })
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["status"] == "created"
    assert row["gateway"] == "stub"
    assert str(row["gateway_short_url"]).startswith("stub://")
    assert db.inserted.get("payment_links"), "no row was written"


def test_create_rejects_nonpositive_amount(client):
    c, _ = client
    r = c.post("/api/travel/v1/payment-links",
               json={"amount": "0", "currency": "INR", "gateway": "stub"})
    assert r.status_code == 422


# ── Route: staff transition ───────────────────────────────────────────────
def test_transition_created_to_sent_succeeds(client):
    c, db = client
    db.tables["payment_links"] = [_link_row("created")]
    r = c.post(f"/api/travel/v1/payment-links/{LINK_ID}/transition",
               json={"status": "sent"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"


def test_transition_cannot_unpay_a_paid_link(client):
    c, db = client
    db.tables["payment_links"] = [_link_row("paid")]
    r = c.post(f"/api/travel/v1/payment-links/{LINK_ID}/transition",
               json={"status": "sent"})
    assert r.status_code == 409, r.text


def test_transition_unknown_status_is_422(client):
    c, db = client
    db.tables["payment_links"] = [_link_row("created")]
    r = c.post(f"/api/travel/v1/payment-links/{LINK_ID}/transition",
               json={"status": "refunded"})
    assert r.status_code == 422


# ── Route: gateway webhook ────────────────────────────────────────────────
def _signed_webhook(c, event, link_id="plink_stub_x", tamper=False):
    raw = json.dumps({"event": event, "payment_link_id": link_id}).encode()
    sig = StubGateway().sign(raw)
    if tamper:
        raw = raw + b" "   # body changed after signing
    return c.post("/api/travel/v1/webhook/razorpay", content=raw,
                  headers={"X-Razorpay-Signature": sig,
                           "Content-Type": "application/json"})


def test_signed_paid_webhook_marks_link_paid(client):
    c, db = client
    db.tables["payment_links"] = [_link_row("sent")]
    r = _signed_webhook(c, "payment_link.paid")
    assert r.status_code == 200, r.text
    assert r.json().get("applied") is True or r.json().get("status") == "paid"
    assert any(u.get("status") == "paid"
               for u in db.updated.get("payment_links", [])), (
        "webhook verified but never wrote status=paid")


def test_tampered_body_is_rejected_403(client):
    c, db = client
    db.tables["payment_links"] = [_link_row("sent")]
    r = _signed_webhook(c, "payment_link.paid", tamper=True)
    assert r.status_code == 403
    assert not db.updated.get("payment_links"), "tampered webhook mutated state"


def test_replayed_paid_webhook_is_200_but_applies_nothing(client):
    c, db = client
    db.tables["payment_links"] = [_link_row("paid")]
    r = _signed_webhook(c, "payment_link.paid")
    # 200 so the gateway stops retrying; applied must be False.
    assert r.status_code == 200, r.text
    assert r.json().get("applied") is False


def test_unknown_link_webhook_is_200_applied_false(client):
    c, db = client
    db.tables["payment_links"] = []
    r = _signed_webhook(c, "payment_link.paid", link_id="plink_never_issued")
    assert r.status_code == 200, r.text
    assert r.json().get("applied") is False
