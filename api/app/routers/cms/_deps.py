"""
Admin gate for CMS write endpoints — simple bearer token (CMS_ADMIN_TOKEN).
Swap for JWT verification (app.core.security) if/when admin logins exist.
"""
from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_cms_admin(authorization: str = Header(default="")) -> None:
    token = getattr(settings, "CMS_ADMIN_TOKEN", "") or ""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CMS admin token not configured",
        )
    if authorization != f"Bearer {token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
