"""
End-to-end handshake test for /ws/calls/{call_id} through the real ASGI app.

test_ws_auth.py unit-tests the token extraction. This file proves the thing that
actually broke: that a BROWSER-SHAPED handshake — a `Sec-WebSocket-Protocol`
offer and no Authorization header — is accepted by the real route, and that the
server echoes the subprotocol back. RFC 6455 makes the echo load-bearing: a
browser silently drops any connection whose offered subprotocol the server did
not echo, so an un-echoed accept looks like success server-side and like a
mystery disconnect client-side.

Supabase and the DB are stubbed. This test is about the handshake, not the data.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import issue_access_token

CALL_ID = str(uuid.uuid4())
BUSINESS_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())

_USER_ROW = {
    "id": USER_ID,
    "business_id": BUSINESS_ID,
    "email": "agent@fixture.test",
    "role": "manager",
    "status": "active",
}


@pytest.fixture
def client():
    import app.main as m

    return TestClient(m.app)


@pytest.fixture
def token():
    return issue_access_token(sub=USER_ID, business_id=BUSINESS_ID, role="manager")


class _Recorder:
    """Stands in for call_feed.subscribe_call: accept, then block until closed."""

    def __init__(self):
        self.called = False

    async def __call__(self, key, websocket):
        self.called = True
        # Receiving is how the real implementation detects disconnect.
        await websocket.receive_text()


def _patches(recorder, *, call_found=True):
    """Stub out everything below the handshake: user lookup, RBAC scope, feed.

    CallService.__init__ builds a Supabase client eagerly, so the factory has to
    be patched too — patching only get_call_scoped still constructs the client
    and fails before the method is ever reached.
    """
    return (
        patch("app.core.deps._user_from_token", return_value=_USER_ROW),
        patch("app.services.travel.call_service.get_supabase_admin", return_value=object()),
        patch(
            "app.routers.travel.calls.CallService.get_call_scoped",
            return_value={"id": CALL_ID, "business_id": BUSINESS_ID} if call_found else None,
        ),
        patch("app.services.travel.call_feed.subscribe_call", recorder),
        patch("app.services.travel.call_feed.unregister", lambda *a, **k: None),
    )


def test_browser_shaped_handshake_is_accepted_and_echoes_subprotocol(client, token):
    """The regression this whole change exists for.

    No Authorization header — exactly what a browser can send — and the
    connection must open rather than be rejected before .accept().
    """
    recorder = _Recorder()
    p1, p2, p3, p4, p5 = _patches(recorder)
    with p1, p2, p3, p4, p5:
        with client.websocket_connect(
            f"/ws/calls/{CALL_ID}", subprotocols=["bearer", token]
        ) as ws:
            # The echo. Without it a real browser drops the connection.
            assert ws.accepted_subprotocol == "bearer"
            ws.send_text("ping")  # release the recorder's receive
    assert recorder.called, "handshake opened but never reached the call feed"


def test_header_handshake_still_works(client, token):
    """ws_probe.py must not regress."""
    recorder = _Recorder()
    p1, p2, p3, p4, p5 = _patches(recorder)
    with p1, p2, p3, p4, p5:
        with client.websocket_connect(
            f"/ws/calls/{CALL_ID}", headers={"Authorization": f"Bearer {token}"}
        ) as ws:
            # No subprotocol was offered, so none may be echoed.
            assert ws.accepted_subprotocol is None
            ws.send_text("ping")
    assert recorder.called


def test_handshake_without_any_credentials_is_rejected(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/calls/{CALL_ID}"):
            pass
    assert exc.value.code == 1008


def test_handshake_with_a_garbage_token_is_rejected(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"/ws/calls/{CALL_ID}", subprotocols=["bearer", "not-a-jwt"]
        ):
            pass
    assert exc.value.code == 1008


def test_out_of_scope_call_closes_4404_not_1008(client, token):
    """A call belonging to another tenant must be indistinguishable from a
    missing one — 4404 either way, never a different code that would confirm
    the call exists."""
    from starlette.websockets import WebSocketDisconnect

    p1, p2, p3, p4, p5 = _patches(_Recorder(), call_found=False)
    with p1, p2, p3, p4, p5:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                f"/ws/calls/{CALL_ID}", subprotocols=["bearer", token]
            ):
                pass
    assert exc.value.code == 4404
