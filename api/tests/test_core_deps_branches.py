"""
Branch coverage for app/core/deps.py — the RBAC/auth dependency layer.

These are the branches the router-surface suite cannot reach (it overrides
these dependencies to inject a principal). Here they run for real, against
tests/fake_supabase.py, covering:

  * get_current_user: missing/garbage/wrong-type/revoked tokens, deleted
    users, inactive users, and the happy path;
  * require_role: hierarchy (manager accepts admin, rejects agent/viewer);
  * get_current_traveller: type-claim isolation in BOTH directions;
  * _ws_token: header > subprotocol > query-param precedence.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from fake_supabase import install
from app.core import deps as core_deps
from app.core import security

BIZ = "b0000000-0000-0000-0000-0000000000b1"
USER_ID = "d0000000-0000-0000-0000-0000000000d1"
CUST_ID = "c0000000-0000-0000-0000-0000000000c1"


def _user_row(role="manager", status="active"):
    return {"id": USER_ID, "business_id": BIZ, "role": role, "status": status,
            "email": "u@example.com"}


def _bearer(token: str) -> str:
    return f"Bearer {token}"


def _access(role="manager") -> str:
    return security.issue_access_token(sub=USER_ID, business_id=BIZ, role=role)


# ── get_current_user ──────────────────────────────────────────────────────
def test_missing_header_is_401():
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_user(authorization=None)
    assert e.value.status_code == 401


def test_non_bearer_header_is_401():
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_user(authorization="Basic abc123")
    assert e.value.status_code == 401


def test_garbage_token_is_401(monkeypatch):
    install(monkeypatch)
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_user(authorization=_bearer("not.a.jwt"))
    assert e.value.status_code == 401
    assert e.value.detail == "Invalid token"


def test_expired_token_is_401(monkeypatch):
    install(monkeypatch)
    from datetime import timedelta
    monkeypatch.setattr(
        security, "_now",
        lambda: __import__("datetime").datetime.now(
            tz=__import__("datetime").timezone.utc) - timedelta(hours=2),
    )
    stale = _access()
    monkeypatch.undo()
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_user(authorization=_bearer(stale))
    assert e.value.status_code == 401
    assert e.value.detail == "Token expired"


def test_refresh_token_rejected_on_access_path(monkeypatch):
    install(monkeypatch)
    refresh = security.issue_refresh_token(sub=USER_ID, business_id=BIZ)
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_user(authorization=_bearer(refresh))
    # Signed with a DIFFERENT secret — must die as invalid, and certainly 401.
    assert e.value.status_code == 401


def test_revoked_jti_is_401(monkeypatch):
    install(monkeypatch, {"ts_users": [_user_row()]})
    token = _access()
    claims = security.decode_access_token(token)
    security.blacklist_jti(claims["jti"], ttl_seconds=60)
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_user(authorization=_bearer(token))
    assert e.value.status_code == 401
    assert "revoked" in e.value.detail.lower()


def test_deleted_user_is_401(monkeypatch):
    install(monkeypatch, {"ts_users": []})   # token valid, row gone
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_user(authorization=_bearer(_access()))
    assert e.value.status_code == 401
    assert "no longer exists" in e.value.detail


def test_inactive_user_is_403(monkeypatch):
    install(monkeypatch, {"ts_users": [_user_row(status="inactive")]})
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_user(authorization=_bearer(_access()))
    assert e.value.status_code == 403


def test_active_user_resolves(monkeypatch):
    install(monkeypatch, {"ts_users": [_user_row()]})
    user = core_deps.get_current_user(authorization=_bearer(_access()))
    assert user["id"] == USER_ID
    assert user["role"] == "manager"


# ── require_role ──────────────────────────────────────────────────────────
def test_require_role_rejects_unknown_role_names():
    with pytest.raises(ValueError):
        core_deps.require_role("root")


def test_require_role_is_a_hierarchy_not_exact_match():
    dep = core_deps.require_role("manager")
    inner = dep.__wrapped__ if hasattr(dep, "__wrapped__") else dep
    # role above the floor passes
    assert inner(user=_user_row(role="admin"))["role"] == "admin"
    assert inner(user=_user_row(role="super_admin"))["role"] == "super_admin"
    assert inner(user=_user_row(role="manager"))["role"] == "manager"
    # role below the floor is 403
    for low in ("agent", "user", "viewer"):
        with pytest.raises(HTTPException) as e:
            inner(user=_user_row(role=low))
        assert e.value.status_code == 403
    # unknown role ranks 0 -> 403, never a crash
    with pytest.raises(HTTPException):
        inner(user=_user_row(role="mystery"))


# ── get_current_traveller — token-family isolation ────────────────────────
def test_traveller_token_resolves():
    tok = security.issue_traveller_token(customer_id=CUST_ID, business_id=BIZ)
    out = core_deps.get_current_traveller(authorization=_bearer(tok))
    assert out == {"customer_id": CUST_ID, "business_id": BIZ}


def test_agency_token_rejected_on_traveller_path():
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_traveller(authorization=_bearer(_access()))
    assert e.value.status_code == 401
    assert e.value.detail == "Wrong token type"   # same wording as other 401s


def test_traveller_token_rejected_on_agency_path(monkeypatch):
    install(monkeypatch, {"ts_users": [_user_row()]})
    tok = security.issue_traveller_token(customer_id=CUST_ID, business_id=BIZ)
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_user(authorization=_bearer(tok))
    assert e.value.status_code == 401


def test_traveller_missing_header_is_401():
    with pytest.raises(HTTPException) as e:
        core_deps.get_current_traveller(authorization=None)
    assert e.value.status_code == 401


# ── _ws_token extraction precedence ───────────────────────────────────────
class _FakeWS:
    def __init__(self, headers=None, query=None):
        self.headers = headers or {}
        self.query_params = query or {}
        self.state = type("S", (), {})()


def test_ws_token_prefers_authorization_header():
    ws = _FakeWS(headers={"sec-websocket-protocol": "bearer, sub-token"},
                 query={"token": "query-token"})
    assert core_deps._ws_token(ws, "Bearer header-token") == "header-token"


def test_ws_token_reads_subprotocol_offer_and_marks_echo():
    ws = _FakeWS(headers={"sec-websocket-protocol": "bearer, the-token"})
    assert core_deps._ws_token(ws, None) == "the-token"
    # RFC 6455: server must echo the offered subprotocol back on accept.
    assert core_deps.ws_accept_subprotocol(ws) == "bearer"


def test_ws_token_falls_back_to_query_param():
    ws = _FakeWS(query={"token": "query-token"})
    assert core_deps._ws_token(ws, None) == "query-token"
    assert core_deps.ws_accept_subprotocol(ws) is None


def test_ws_token_none_when_nothing_offered():
    assert core_deps._ws_token(_FakeWS(), None) is None
