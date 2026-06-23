"""
Dependencies for the TechScape API.

Auth is dual:
  • X-API-Key header  → matches a row in ts_businesses (machine-to-machine)
  • Authorization: Bearer <jwt> → ts_users → ts_businesses (interactive UI)

Both produce the same shape: a `Principal` dict with business + (optional) user.
Routes that need elevated access can call `require_role("admin")` etc.

Per-business rate limiting and audit context are also wired here.
"""
from __future__ import annotations
import logging
from typing import Optional
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, Request, status

from app.core.config import settings
from app.core.security import decode_access_token
from app.services.techscape import BusinessService
from app.services.techscape.rate_limit import get_rate_limiter

logger = logging.getLogger(__name__)


_VALID_ROLES = {"admin", "manager", "user", "viewer"}


def _too_many() -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")


def require_business(
    request: Request,
    x_api_key:     Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_business_id: Optional[str] = Header(default=None, alias="X-Business-ID"),
) -> dict:
    """
    Resolves the calling principal. Returns:
      {**business_row, "_user": Optional[dict]}
    """
    svc = BusinessService()
    principal: Optional[dict] = None
    user: Optional[dict] = None

    # 1. JWT first (interactive UI flow)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = decode_access_token(token)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
        if claims.get("type") != "access":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
        try:
            biz_uuid = UUID(claims["biz"])
        except Exception:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad business id in token")
        principal = svc.get(biz_uuid)
        if principal:
            try:
                user_row = svc.db.table("ts_users").select("*").eq(
                    "id", claims["sub"]
                ).limit(1).execute().data
                user = user_row[0] if user_row else {"id": claims["sub"], "role": claims.get("role", "user")}
            except Exception:
                user = {"id": claims["sub"], "role": claims.get("role", "user")}

    # 2. API key fallback
    if principal is None and x_api_key:
        principal = svc.find_by_api_key(x_api_key)
        if not principal:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")

    # 3. Dev-only X-Business-ID
    if principal is None and x_business_id and settings.DEBUG:
        try:
            principal = svc.get(UUID(x_business_id))
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad X-Business-ID")

    if not principal:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")

    # 4. Active business?
    if principal.get("status") != "active":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Business status is {principal.get('status')}",
        )

    # 5. Per-business per-route rate limit
    tier = principal.get("subscription_tier") or "starter"
    allowed, _remaining = get_rate_limiter().allow(
        business_id=str(principal["id"]),
        route=request.url.path,
        tier=tier,
    )
    if not allowed:
        raise _too_many()

    principal["_user"] = user
    # stash on request.state so downstream handlers / audit can read
    request.state.principal = principal
    return principal


def require_role(*roles: str):
    """Dependency factory for RBAC."""
    bad = set(roles) - _VALID_ROLES
    if bad:
        raise ValueError(f"Unknown roles: {bad}")

    def _check(biz: dict = None):  # type: ignore[assignment]
        from fastapi import Depends
        biz = biz  # placeholder; real injection in __call__
    # FastAPI requires a regular Depends-compatible function; build it cleanly:

    def _dep(principal: dict) -> dict:
        user = principal.get("_user") or {}
        role = user.get("role") or "admin" if not principal.get("_user") else user.get("role")
        if user and role not in roles and role != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal

    # Wrap to use require_business under the hood
    from fastapi import Depends

    def _wrapped(principal: dict = Depends(require_business)) -> dict:
        return _dep(principal)

    return _wrapped
