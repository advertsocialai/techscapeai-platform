"""
C-3 (COMPLIANCE_CHECKLIST.md): the consent disclosure must leave a RECORD.

The announcement itself (C-1) plays via stream_xml(); these tests prove the
NEW mechanism — the answer webhook writes a 'consent_disclosure_played' row
to travel_call_events, payload {language, wording_version}, at the moment the
XML that plays the announcement is served. No schema change was needed:
travel_call_events.event_type is an unconstrained VARCHAR(50) (migration 0005).

Wording is PENDING LEGAL REVIEW (BLK-8) — these tests pin the MECHANISM
(event written, versioned, non-fatal on failure), never the exact copy.

Offline: fake Supabase client, no network, no credentials. Plivo signature
verification passes because PLIVO_AUTH_TOKEN is unset in the fixture env
(stub mode — same assumption as the rest of this suite).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.routers.travel import webhooks_voice
from app.services.travel.voice import (
    CONSENT_ANNOUNCEMENT,
    CONSENT_ANNOUNCEMENT_LANGUAGE,
    CONSENT_WORDING_VERSION,
)

BIZ = "b0000000-0000-0000-0000-0000000000b1"
LEAD = "d0000000-0000-0000-0000-0000000000d1"
CALL_UUID = "plivo-call-uuid-1"
WEBHOOK_PATH = "/api/travel/v1/webhook/plivo/voice"


def _fake_db(select_data: dict, *, fail_insert_tables: set[str] = frozenset()):
    """Minimal supabase-py surface: select chains answer canned rows per
    table; inserts are recorded (and can be made to raise per-table)."""
    db = MagicMock()
    inserted: list[dict] = []

    def _table(name):
        t = MagicMock()
        for chain in ("select", "eq", "in_", "order", "limit"):
            getattr(t, chain).return_value = t
        t.execute.return_value = MagicMock(data=select_data.get(name, []))

        def _insert(payload, _name=name):
            if _name in fail_insert_tables:
                raise RuntimeError(f"simulated insert failure on {_name}")
            inserted.append({"_table": _name, **payload})
            ins = MagicMock()
            ins.execute.return_value = MagicMock(data=[{**payload, "id": f"{_name}-row-1"}])
            return ins

        t.insert.side_effect = _insert
        return t

    db.table.side_effect = _table
    db._inserted = inserted
    return db


@pytest.fixture
def client():
    import app.main as m
    return TestClient(m.app)


_FORM = {"CallUUID": CALL_UUID, "From": "+919876543210", "To": "+918888888888"}

# One registered number → business resolves; an existing lead → no lead insert.
_RESOLVED = {
    "business_phone_numbers": [{"business_id": BIZ}],
    "travel_leads": [{"id": LEAD}],
}


def test_consent_event_row_is_written_with_language_and_wording_version(client, monkeypatch):
    db = _fake_db(_RESOLVED)
    monkeypatch.setattr(webhooks_voice, "get_supabase_admin", lambda: db)

    r = client.post(WEBHOOK_PATH, data=_FORM)

    assert r.status_code == 200
    assert "xml" in r.headers["content-type"]
    assert CONSENT_ANNOUNCEMENT in r.text, "announcement must still be in the answer XML"

    events = [row for row in db._inserted if row["_table"] == "travel_call_events"]
    assert events, "no travel_call_events row was written — C-3 regressed"
    ev = events[0]
    assert ev["event_type"] == "consent_disclosure_played"
    assert ev["payload"] == {
        "language": CONSENT_ANNOUNCEMENT_LANGUAGE,
        "wording_version": CONSENT_WORDING_VERSION,
    }

    # The event must point at the travel_calls row created in the same request.
    calls = [row for row in db._inserted if row["_table"] == "travel_calls"]
    assert calls and ev["call_id"] == "travel_calls-row-1"


def test_event_write_failure_never_breaks_the_answer_webhook(client, monkeypatch):
    """The caller must still be answered when the audit write dies — an
    unanswered phone is strictly worse than a missing compliance marker
    (which is logged instead)."""
    db = _fake_db(_RESOLVED, fail_insert_tables={"travel_call_events"})
    monkeypatch.setattr(webhooks_voice, "get_supabase_admin", lambda: db)

    r = client.post(WEBHOOK_PATH, data=_FORM)

    assert r.status_code == 200
    assert CONSENT_ANNOUNCEMENT in r.text


def test_no_business_resolved_still_plays_announcement_without_event_row(client, monkeypatch):
    """With no call row (FK target) an event row is impossible — but the
    disclosure must still PLAY: stream_xml() includes it unconditionally."""
    db = _fake_db({"business_phone_numbers": [], "travel_leads": []})
    monkeypatch.setattr(webhooks_voice, "get_supabase_admin", lambda: db)
    monkeypatch.setattr(webhooks_voice.settings, "PLIVO_BUSINESS_ID", None, raising=False)

    r = client.post(WEBHOOK_PATH, data=_FORM)

    assert r.status_code == 200
    assert CONSENT_ANNOUNCEMENT in r.text
    assert not db._inserted, "nothing should be written without a resolved business"
