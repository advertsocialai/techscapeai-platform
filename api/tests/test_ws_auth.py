"""
Regression tests for the WebSocket auth channel.

The live call feed depended on `get_current_user`, which reads the
Authorization header. That authenticated the Python probe
(`websockets.connect(..., additional_headers=)`) and nothing else: a browser's
WebSocket constructor cannot set request headers, so every dashboard handshake
was rejected before `.accept()` and surfaced as a bare close code 1006 —
indistinguishable from a network blip, and retried forever.

These tests pin the three properties that fix depends on:
  * the browser-settable subprotocol channel yields the token,
  * the header channel still works (the probe must not regress),
  * the chosen subprotocol is recorded so the route can echo it, because
    RFC 6455 says a browser drops a connection whose offered subprotocol the
    server did not echo.
"""
from __future__ import annotations

import pytest

from app.core.deps import _WS_SUBPROTOCOL, _ws_token, ws_accept_subprotocol


class _FakeState:
    pass


class _FakeWebSocket:
    """Minimal stand-in — _ws_token only touches .headers, .query_params, .state."""

    def __init__(self, headers: dict | None = None, query: dict | None = None):
        self.headers = headers or {}
        self.query_params = query or {}
        self.state = _FakeState()


def test_subprotocol_carries_the_token():
    ws = _FakeWebSocket(headers={"sec-websocket-protocol": f"{_WS_SUBPROTOCOL}, tok-abc"})
    assert _ws_token(ws, None) == "tok-abc"
    # Must be recorded for the route to echo, or the browser closes on us.
    assert ws_accept_subprotocol(ws) == _WS_SUBPROTOCOL


def test_authorization_header_still_works():
    """ws_probe.py must keep authenticating unchanged."""
    ws = _FakeWebSocket()
    assert _ws_token(ws, "Bearer tok-header") == "tok-header"
    # No subprotocol was offered, so nothing may be echoed.
    assert ws_accept_subprotocol(ws) is None


def test_header_wins_over_subprotocol():
    ws = _FakeWebSocket(headers={"sec-websocket-protocol": f"{_WS_SUBPROTOCOL}, tok-sub"})
    assert _ws_token(ws, "Bearer tok-header") == "tok-header"


def test_query_param_is_the_last_resort():
    ws = _FakeWebSocket(query={"token": "tok-query"})
    assert _ws_token(ws, None) == "tok-query"
    assert ws_accept_subprotocol(ws) is None


@pytest.mark.parametrize(
    "offer",
    [
        "",                       # empty
        "bearer",                 # name with no token after it
        "graphql-ws, tok",        # someone else's subprotocol
        "  ,  ",                  # whitespace only
    ],
)
def test_malformed_subprotocol_offers_do_not_authenticate(offer):
    ws = _FakeWebSocket(headers={"sec-websocket-protocol": offer})
    assert _ws_token(ws, None) is None
    # And nothing may be echoed for an offer we did not accept.
    assert ws_accept_subprotocol(ws) is None


def test_no_credentials_at_all_yields_none():
    assert _ws_token(_FakeWebSocket(), None) is None


def test_non_bearer_authorization_falls_through_to_subprotocol():
    """A Basic/other scheme must not shadow a valid subprotocol offer."""
    ws = _FakeWebSocket(headers={"sec-websocket-protocol": f"{_WS_SUBPROTOCOL}, tok-sub"})
    assert _ws_token(ws, "Basic abc123") == "tok-sub"
