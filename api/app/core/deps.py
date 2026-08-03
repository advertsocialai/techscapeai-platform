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
from fastapi import Depends, Header, HTTPException, status

from app.core.security import decode_access_token, is_jti_blacklisted
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

    token = authorization.split(" ", 1)[1].strip()
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
