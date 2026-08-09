"""
Core RBAC dependencies (Phase 1).

get_current_user resolves the calling user strictly from a Bearer JWT —
no API-key fallback (that dual-auth business flow stays in
routers/techscape/_deps.py:require_business). require_role() enforces a
role hierarchy on top of it.

Role hierarchy uses the REAL ts_users.role CHECK-constraint values.
As of migration 0002 the CHECK allows both the legacy set
(admin/manager/user/viewer) AND the product-spec set
(super_admin/agent — added; manager/viewer already overlap by name).
Mapping (legacy == spec, same rank):
    admin   (highest) == super_admin
    manager           == admin      (branch-level admin, spec calls this
                                      "admin" but it is STORED as "manager"
                                      to avoid colliding with legacy "admin",
                                      which already means the top rank)
    user              == agent
    viewer  (lowest)  == viewer
require_role("manager") therefore also accepts "admin"/"super_admin"
(higher rank) — hierarchy, not exact match. New rows created going
forward (users.py) should use super_admin/manager/agent/viewer as the
role value — never bare "admin" or "user" for new users, since those
legacy strings are reserved for pre-migration rows and already carry
the legacy rank.
"""
from __future__ import annotations
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, WebSocket, WebSocketException, status

from app.core.security import (
    TRAVELLER_TOKEN_TYPE,
    decode_access_token,
    is_jti_blacklisted,
)
from app.services.techscape import BusinessService

_ROLE_RANK: dict[str, int] = {
    "viewer": 1,
    "user": 2, "agent": 2,
    "manager": 3,
    "admin": 4, "super_admin": 4,
}


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    return _user_from_token(authorization.split(" ", 1)[1].strip())


def _user_from_token(token: str) -> dict:
    try:
        claims = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    if claims.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    if is_jti_blacklisted(claims.get("jti")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has been revoked")

    rows = (
        BusinessService().db.table("ts_users").select("*")
        .eq("id", claims["sub"]).limit(1).execute().data
    )
    if not rows:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")

    user = rows[0]
    if user.get("status") != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"User status is {user.get('status')}")
    return user


# ── WebSocket authentication ──────────────────────────────────────────────
# WHY THIS EXISTS (do not "simplify" it back to get_current_user)
# ---------------------------------------------------------------
# The live call feed originally depended on get_current_user, which reads the
# Authorization header. That works for the Python probe in
# gogaga-verifier/scripts/ws_probe.py (`websockets.connect(..., additional_headers=)`)
# but it CANNOT work from a browser: the WebSocket constructor exposes no way to
# set request headers, and there is no fetch-style escape hatch. The dashboard's
# live call screen therefore could never have connected — every handshake was
# rejected before .accept(), surfacing in the browser as a bare close code 1006
# that looks like a network blip and retries forever.
#
# The browser-safe channel is the subprotocol header, which IS settable:
#     new WebSocket(url, ['bearer', accessToken])
# It is preferred over the more common `?token=` query string because query
# strings are written to access logs, proxy logs and browser history, and an
# access token in a log file outlives its own expiry as a stolen credential.
# A query param is still accepted as a last resort (some corporate proxies strip
# unknown subprotocols) but is deliberately last in the order below.
#
# RFC 6455: if the client offers subprotocols the server MUST echo exactly one
# back on accept, or the browser closes the connection immediately. The chosen
# value is stashed on websocket.state for the route to pass to .accept().
_WS_SUBPROTOCOL = "bearer"


def _ws_token(websocket: WebSocket, authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()

    # Sec-WebSocket-Protocol arrives as a comma-separated offer list:
    #   "bearer, eyJhbGciOi..."
    offered = websocket.headers.get("sec-websocket-protocol")
    if offered:
        parts = [p.strip() for p in offered.split(",") if p.strip()]
        if len(parts) >= 2 and parts[0] == _WS_SUBPROTOCOL:
            websocket.state.ws_subprotocol = _WS_SUBPROTOCOL
            return parts[1]

    return websocket.query_params.get("token") or None


async def get_current_user_ws(
    websocket: WebSocket,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """get_current_user for WebSocket routes, accepting browser-settable auth.

    Raises WebSocketException rather than HTTPException: a WebSocket scope has
    no way to send an HTTP response, so raising HTTPException here would make
    Starlette attempt one and fail confusingly instead of closing cleanly.
    1008 is the RFC 6455 "policy violation" code.
    """
    token = _ws_token(websocket, authorization)
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
    try:
        return _user_from_token(token)
    except HTTPException as exc:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason=str(exc.detail)
        ) from exc


def ws_accept_subprotocol(websocket: WebSocket) -> Optional[str]:
    """The subprotocol to echo on .accept(), or None when the client offered none."""
    return getattr(websocket.state, "ws_subprotocol", None)


def require_role(*roles: str):
    """Dependency factory — hierarchy, not exact match.

    require_role("manager") accepts "manager" and "admin" (anything
    ranked >= the lowest role passed in).
    """
    bad = set(roles) - set(_ROLE_RANK)
    if bad:
        raise ValueError(f"Unknown roles: {bad}")
    min_rank = min(_ROLE_RANK[r] for r in roles)

    def _dep(user: dict = Depends(get_current_user)) -> dict:
        rank = _ROLE_RANK.get(user.get("role"), 0)
        if rank < min_rank:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _dep


# ── Traveller authentication ──────────────────────────────────────────────
# A TRAVELLER IS NOT A ts_users ROW. They are a travel_customer_profiles row:
# no password, no role, no branch, and no access to anything except their own
# booking. Keeping them out of ts_users is deliberate — putting travellers in
# the agency user table would place them one join away from every Team screen,
# access matrix and role check in the product.
#
# The two token families cannot cross (see security.issue_traveller_token):
# get_current_user above already rejects any token whose type != "access", so
# a traveller token reaches no agency endpoint; and this dependency requires
# type == TRAVELLER_TOKEN_TYPE, so an agency token reaches no /me endpoint.
def get_current_traveller(authorization: Optional[str] = Header(default=None)) -> dict:
    """
    Returns {"customer_id": ..., "business_id": ...} for a valid traveller token.

    Every /me endpoint MUST scope its query by BOTH values. business_id alone is
    not enough — that is the agency's scope, and using it by itself would show a
    traveller every other customer's booking in the same agency. customer_id
    alone is not enough either: ids are not secrets, and a stale token from a
    deleted tenant must not resolve.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    if claims.get("type") != TRAVELLER_TOKEN_TYPE:
        # An agency access token lands here. Same 401, same wording — the
        # response must not tell a caller which kind of token it needs.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    if is_jti_blacklisted(claims.get("jti")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has been revoked")

    customer_id, business_id = claims.get("sub"), claims.get("biz")
    if not customer_id or not business_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    return {"customer_id": customer_id, "business_id": business_id}
