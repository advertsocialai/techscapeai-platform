"""
D-3 (COMPLIANCE_CHECKLIST.md): right-to-erasure — offline proofs.

Service half: erase_customer() must touch exactly the tables enumerated in
erasure_service.py's docstring, never touch a money column, refuse (409-shaped
exception) the Gowtham-owned edge cases, and write one activity_log row.

Router half: DELETE /customers/{id}/personal-data is ADMIN-gated —
401 unauthenticated, 403 for sub-admin roles — and maps service outcomes to
404 (unknown/out-of-scope id) and 409 (active records).

Fake Supabase client throughout: no database, no network, no credentials.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.travel import erasure_service

BIZ = "b0000000-0000-0000-0000-0000000000b1"
CUSTOMER = "a0000000-0000-0000-0000-0000000000a1"
LEAD = "d0000000-0000-0000-0000-0000000000d1"
CALL = "e0000000-0000-0000-0000-0000000000e1"

PROFILE = {
    "id": CUSTOMER, "business_id": BIZ,
    "full_name": "Asha Rao", "email": "asha@example.com",
    "phone": "+919876543210",
    "preferences": {"veg": True}, "past_trips": [{"title": "Bali"}],
    "family_profile": {"kids": 1}, "notes": "prefers window seat",
    "last_intent": "Goa in December",
}


def _fake_db(select_data: dict):
    """Records every update payload per table; select chains answer canned
    rows. Same one-object-per-chain trick as the other offline suites."""
    db = MagicMock()
    updated: list[dict] = []

    def _table(name):
        t = MagicMock()
        for chain in ("select", "eq", "in_", "order", "limit"):
            getattr(t, chain).return_value = t
        t.execute.return_value = MagicMock(data=select_data.get(name, []))

        def _update(payload, _name=name):
            updated.append({"_table": _name, "_payload": payload})
            return t

        t.update.side_effect = _update
        return t

    db.table.side_effect = _table
    db._updated = updated
    return db


_HAPPY = {
    "travel_customer_profiles": [PROFILE],
    "travel_bookings": [],  # the in_("status", ...) guard query
    "travel_leads": [{"id": LEAD}],
    "travel_calls": [{"id": CALL, "status": "completed"}],
    "whatsapp_outbox": [{"id": "w1"}],
}


def _run(select_data):
    db = _fake_db(select_data)
    audit_calls = []
    with patch.object(erasure_service, "get_supabase_admin", return_value=db), \
         patch.object(erasure_service.activity_log, "record",
                      side_effect=lambda **kw: audit_calls.append(kw) or "log-1"):
        result = erasure_service.erase_customer(CUSTOMER, BIZ, actor_id="admin-1")
    return db, audit_calls, result


def test_service_enumerates_exactly_the_personal_data_tables():
    db, audit_calls, result = _run(_HAPPY)

    assert result is not None
    touched_tables = {u["_table"] for u in db._updated}
    assert touched_tables == {
        "whatsapp_outbox",
        "travel_leads",
        "travel_calls",
        "travel_transcripts",
        "travel_itineraries",
        "travel_in_trip_incidents",
        "travel_bookings",
        "follow_ups",
        "payment_links",
        "travel_customer_profiles",
    }, f"erasure surface drifted: {touched_tables}"

    # Money rows are never deleted and money COLUMNS are never touched.
    money_cols = {"amount", "currency", "grand_total_inr", "deposit_inr",
                  "balance_inr", "status", "gateway_link_id", "booking_ref"}
    for u in db._updated:
        assert not money_cols & set(u["_payload"]), \
            f"money/lifecycle column touched in {u['_table']}: {u['_payload']}"

    # payment_links is DETACHED (customer_id -> NULL), nothing else.
    pl = [u for u in db._updated if u["_table"] == "payment_links"]
    assert pl and pl[0]["_payload"] == {"customer_id": None}

    # The profile itself ends up scrubbed.
    prof = [u for u in db._updated if u["_table"] == "travel_customer_profiles"][0]
    assert prof["_payload"]["full_name"] is None
    assert prof["_payload"]["email"] is None
    assert prof["_payload"]["phone"] is None

    # NOT NULL text columns get placeholders, not NULLs.
    leads = [u for u in db._updated if u["_table"] == "travel_leads"][0]
    assert leads["_payload"]["raw_message"] == erasure_service.ERASED_TEXT
    tr = [u for u in db._updated if u["_table"] == "travel_transcripts"][0]
    assert tr["_payload"]["text_original"] == erasure_service.ERASED_TEXT

    # Exactly one audit row.
    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "customer.personal_data.erased"
    assert audit_calls[0]["entity_id"] == CUSTOMER
    assert audit_calls[0]["business_id"] == BIZ


def test_no_phone_means_whatsapp_outbox_is_unreachable_and_skipped():
    data = dict(_HAPPY, travel_customer_profiles=[{**PROFILE, "phone": None}])
    db, _, result = _run(data)
    assert result is not None
    assert "whatsapp_outbox" not in {u["_table"] for u in db._updated}


def test_active_booking_refuses_with_conflict():
    data = dict(_HAPPY, travel_bookings=[{"id": "bk1"}])  # guard query hits
    with pytest.raises(erasure_service.ActiveRecordConflict):
        _run(data)


def test_live_call_refuses_with_conflict():
    data = dict(_HAPPY, travel_calls=[{"id": CALL, "status": "active"}])
    with pytest.raises(erasure_service.ActiveRecordConflict):
        _run(data)


def test_unknown_customer_returns_none_for_404():
    db, audit_calls, result = _run(dict(_HAPPY, travel_customer_profiles=[]))
    assert result is None
    assert not db._updated, "nothing may be touched for an unknown id"
    assert not audit_calls


# ── Router half — admin gate + status mapping ──────────────────────────────
URL = f"/api/travel/v1/customers/{CUSTOMER}/personal-data"


@pytest.fixture
def client():
    import app.main as m
    yield TestClient(m.app)
    m.app.dependency_overrides.clear()


def _login_as(app, role):
    from app.core.deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "u1", "business_id": BIZ, "role": role, "status": "active",
    }


def test_endpoint_requires_auth_401(client):
    assert client.delete(URL).status_code == 401


@pytest.mark.parametrize("role", ["viewer", "agent", "user", "manager"])
def test_endpoint_rejects_sub_admin_roles_403(client, role):
    import app.main as m
    _login_as(m.app, role)
    assert client.delete(URL).status_code == 403


def test_endpoint_admin_gets_summary_and_service_is_called(client, monkeypatch):
    import app.main as m
    from app.routers.travel import customer as customer_router
    _login_as(m.app, "admin")

    seen = {}

    def _fake_erase(customer_id, business_id, *, actor_id=None):
        seen.update(customer_id=customer_id, business_id=business_id, actor_id=actor_id)
        return {"customer_id": customer_id, "tables": {"travel_leads": 1}}

    monkeypatch.setattr(customer_router.erasure_service, "erase_customer", _fake_erase)
    r = client.delete(URL)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert seen == {"customer_id": CUSTOMER, "business_id": BIZ, "actor_id": "u1"}


def test_endpoint_maps_unknown_id_to_404(client, monkeypatch):
    import app.main as m
    from app.routers.travel import customer as customer_router
    _login_as(m.app, "super_admin")
    monkeypatch.setattr(customer_router.erasure_service, "erase_customer",
                        lambda *a, **kw: None)
    assert client.delete(URL).status_code == 404


def test_endpoint_maps_active_records_to_409(client, monkeypatch):
    import app.main as m
    from app.routers.travel import customer as customer_router
    _login_as(m.app, "admin")

    def _boom(*a, **kw):
        raise erasure_service.ActiveRecordConflict("active booking")

    monkeypatch.setattr(customer_router.erasure_service, "erase_customer", _boom)
    r = client.delete(URL)
    assert r.status_code == 409
    assert "active booking" in r.json()["detail"]
