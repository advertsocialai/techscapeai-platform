"""
Auth router for TechScape:

  • POST /auth/register-business  → creates a business + first admin user
  • POST /auth/login              → email + password → JWT access + refresh
  • POST /auth/refresh            → swap a refresh token for a new access token
  • GET  /auth/me                 → introspect current access token
  • POST /auth/api-key/rotate     → rotate the business's API key (admin)
  • POST /auth/password/forgot    → start a password reset (returns token in DEV)
  • POST /auth/password/reset     → finalise password reset
  • GET  /auth/oauth/google/url   → kick off Google OAuth flow
  • GET  /auth/oauth/google/callback → exchange code → JWT pair
"""
from __future__ import annotations
import secrets
import time
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings
from app.core.security import (
    decode_refresh_token, hash_password, issue_access_token, issue_refresh_token,
)
from app.services.techscape import BusinessService
from app.services.techscape.audit import write_audit

from ._deps import require_business

router = APIRouter()


# ── DTOs ──────────────────────────────────────────────────────────
class RegisterBusinessIn(BaseModel):
    business_name: str = Field(min_length=1, max_length=255)
    contact_email: EmailStr
    contact_phone: Optional[str] = None
    industry: str = "travel"
    website_url: Optional[str] = None
    timezone: str = "UTC"
    user_first_name: Optional[str] = None
    user_last_name:  Optional[str] = None
    user_password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_min: int


class PasswordForgotIn(BaseModel):
    email: EmailStr


class PasswordResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=200)


# ── Tiny in-memory password-reset store (dev). Production should email + DB. ──
_RESET_TTL_SEC = 30 * 60
_reset_tokens: dict[str, tuple[str, float]] = {}


def _issue_reset_token(user_id: str) -> str:
    tok = secrets.token_urlsafe(24)
    _reset_tokens[tok] = (user_id, time.monotonic() + _RESET_TTL_SEC)
    return tok


def _consume_reset_token(token: str) -> Optional[str]:
    rec = _reset_tokens.pop(token, None)
    if not rec:
        return None
    user_id, expires_at = rec
    if time.monotonic() > expires_at:
        return None
    return user_id


# ── Routes ────────────────────────────────────────────────────────
@router.post("/register-business", status_code=status.HTTP_201_CREATED)
def register_business(payload: RegisterBusinessIn, request: Request):
    svc = BusinessService()

    if svc.find_user_by_email(str(payload.contact_email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "User already exists")

    biz_data = {
        "name":          payload.business_name,
        "contact_email": str(payload.contact_email),
        "contact_phone": payload.contact_phone,
        "industry":      payload.industry,
        "website_url":   payload.website_url,
        "timezone":      payload.timezone,
    }
    biz = svc.create(biz_data)
    user = svc.create_user(
        business_id=UUID(biz["id"]),
        email=str(payload.contact_email),
        password=payload.user_password,
        first_name=payload.user_first_name,
        last_name=payload.user_last_name,
        role="admin",
    )
    write_audit(
        business_id=biz["id"], user_id=user["id"], action="business.registered",
        resource_type="business", resource_id=biz["id"],
        ip_address=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )
    return {
        "business": {k: v for k, v in biz.items() if k != "api_key_hash"},
        "user":     {k: v for k, v in user.items() if k != "password_hash"},
        "api_key":  biz["api_key"],  # plain shown once
    }


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, request: Request):
    svc  = BusinessService()
    user = svc.authenticate(email=str(payload.email), password=payload.password)
    if not user:
        write_audit(
            action="auth.login.failed", details={"email": str(payload.email)},
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    access  = issue_access_token(sub=user["id"], business_id=user["business_id"], role=user.get("role", "user"))
    refresh = issue_refresh_token(sub=user["id"], business_id=user["business_id"])
    write_audit(
        business_id=user["business_id"], user_id=user["id"], action="auth.login",
        ip_address=_client_ip(request), user_agent=request.headers.get("user-agent"),
    )
    return TokenOut(
        access_token=access, refresh_token=refresh,
        expires_in_min=settings.JWT_ACCESS_TTL_MIN,
    )


@router.post("/refresh", response_model=TokenOut)
def refresh(payload: RefreshIn):
    try:
        claims = decode_refresh_token(payload.refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")

    svc = BusinessService()
    user_row = svc.db.table("ts_users").select("*").eq("id", claims["sub"]).limit(1).execute().data
    if not user_row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    user = user_row[0]

    access  = issue_access_token(sub=user["id"], business_id=user["business_id"], role=user.get("role", "user"))
    refresh = issue_refresh_token(sub=user["id"], business_id=user["business_id"])
    return TokenOut(
        access_token=access, refresh_token=refresh,
        expires_in_min=settings.JWT_ACCESS_TTL_MIN,
    )


@router.get("/me")
def me(principal: dict = Depends(require_business)):
    safe = {k: v for k, v in principal.items() if k not in ("api_key_hash", "_user")}
    safe["user"] = (principal.get("_user") or {}) and {
        k: v for k, v in (principal.get("_user") or {}).items() if k != "password_hash"
    }
    return safe


@router.post("/api-key/rotate")
def rotate_api_key(principal: dict = Depends(require_business)):
    user = principal.get("_user") or {}
    if user and user.get("role") not in ("admin", None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    out = BusinessService().rotate_api_key(UUID(principal["id"]))
    write_audit(business_id=principal["id"], user_id=user.get("id"),
                action="auth.api_key.rotated", resource_type="business",
                resource_id=principal["id"])
    return out


@router.post("/password/forgot")
def password_forgot(payload: PasswordForgotIn):
    svc = BusinessService()
    user = svc.find_user_by_email(str(payload.email))
    # do not leak whether the email exists
    token = _issue_reset_token(user["id"]) if user else None
    if settings.DEBUG and token:
        return {"ok": True, "reset_token": token}
    return {"ok": True}


@router.post("/password/reset")
def password_reset(payload: PasswordResetIn, request: Request):
    user_id = _consume_reset_token(payload.token)
    if not user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")
    BusinessService().set_password(UUID(user_id), payload.new_password)
    write_audit(user_id=user_id, action="auth.password.reset",
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"))
    return {"ok": True}


# ── Google OAuth (auth-code flow) ─────────────────────────────────
GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USER_URL  = "https://openidconnect.googleapis.com/v1/userinfo"


@router.get("/oauth/google/url")
def google_oauth_url(redirect_uri: Optional[str] = None):
    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Google OAuth not configured")
    redirect_uri = redirect_uri or f"{settings.OAUTH_REDIRECT_BASE}/auth/google/callback"
    state = secrets.token_urlsafe(16)
    qs = urlencode({
        "client_id":     settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "access_type":   "online",
        "prompt":        "select_account",
    })
    return {"url": f"{GOOGLE_AUTH_URL}?{qs}", "state": state}


@router.get("/oauth/google/callback", response_model=TokenOut)
async def google_oauth_callback(code: str = Query(...),
                                redirect_uri: Optional[str] = None):
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google OAuth not configured")

    redirect_uri = redirect_uri or f"{settings.OAUTH_REDIRECT_BASE}/auth/google/callback"

    async with httpx.AsyncClient(timeout=15) as client:
        tok = await client.post(GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        })
        if tok.status_code != 200:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google token exchange failed")
        access_g = tok.json().get("access_token")
        if not access_g:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google token exchange failed")

        ui = await client.get(GOOGLE_USER_URL,
                              headers={"Authorization": f"Bearer {access_g}"})
        if ui.status_code != 200:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google userinfo failed")

    info = ui.json()
    email = (info.get("email") or "").lower()
    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google account has no email")

    svc = BusinessService()
    user = svc.find_user_by_email(email)
    if not user:
        # auto-provision a single-user business
        biz = svc.create({
            "name":          email.split("@")[0],
            "contact_email": email,
            "industry":      "travel",
        })
        user = svc.create_user(
            business_id=UUID(biz["id"]),
            email=email,
            password=secrets.token_urlsafe(24),  # placeholder; user logs in via Google
            first_name=info.get("given_name"),
            last_name=info.get("family_name"),
            role="admin",
        )

    access_t  = issue_access_token(sub=user["id"], business_id=user["business_id"], role=user.get("role", "user"))
    refresh_t = issue_refresh_token(sub=user["id"], business_id=user["business_id"])
    return TokenOut(access_token=access_t, refresh_token=refresh_t,
                    expires_in_min=settings.JWT_ACCESS_TTL_MIN)


# ── helpers ───────────────────────────────────────────────────────
def _client_ip(request: Request) -> Optional[str]:
    h = request.headers
    return h.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None)
