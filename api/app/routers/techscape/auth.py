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
import re
import secrets
import time
import traceback
import logging
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.config import settings
from app.core.security import (
    blacklist_jti, decode_access_token, decode_refresh_token,
    hash_password, issue_access_token, issue_refresh_token,
)
from app.services.techscape import BusinessService
from app.services.techscape.audit import write_audit

from ._deps import require_business

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Password strength ───────────────────────────────────────────────
_PASSWORD_RULES: tuple[tuple[str, str], ...] = (
    (r"[A-Z]", "one uppercase letter"),
    (r"[a-z]", "one lowercase letter"),
    (r"\d", "one number"),
    (r"[^A-Za-z0-9]", "one special character"),
)


def _validate_password_strength(v: str) -> str:
    missing = [msg for pattern, msg in _PASSWORD_RULES if not re.search(pattern, v)]
    if missing:
        raise ValueError(f"Password must contain at least {', '.join(missing)}")
    return v


# ── DTOs ──────────────────────────────────────────────────────────
class RegisterBusinessIn(BaseModel):
    model_config = {"extra": "ignore"}

    business_name: str = Field(min_length=1, max_length=255)
    contact_email: EmailStr
    contact_phone: Optional[str] = None
    industry: str = "travel"
    website_url: Optional[str] = None
    timezone: str = "UTC"
    user_first_name: Optional[str] = None
    user_last_name:  Optional[str] = None
    user_password: str = Field(min_length=8, max_length=200)
    terms_accepted_at: Optional[str] = None
    terms_version: Optional[str] = None
    marketing_opt_in: Optional[bool] = False

    _validate_user_password = field_validator("user_password")(_validate_password_strength)


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

    _validate_new_password = field_validator("new_password")(_validate_password_strength)


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
    if not _consume_verified_email(str(payload.contact_email)):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Email not verified — call /otp/send then /otp/verify first",
        )
    svc = BusinessService()
    try:
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
            "api_key":  biz["api_key"],
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/logout")
def logout(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        return {"ok": True}  # already unusable — nothing to revoke
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if claims.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    remaining = claims["exp"] - time.time()
    blacklist_jti(claims.get("jti"), remaining)
    write_audit(
        business_id=claims.get("biz"), user_id=claims.get("sub"), action="auth.logout",
    )
    return {"ok": True}


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
    token = _issue_reset_token(user["id"]) if user else None

    if token and settings.RESEND_API_KEY:
        reset_link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
        try:
            resp = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": f"Klara <{settings.FROM_EMAIL}>",
                    "to": [str(payload.email)],
                    "subject": "Reset your Klara password",
                    "html": (
                        "<p>We received a request to reset your password.</p>"
                        f'<p><a href="{reset_link}">Click here to reset your password</a></p>'
                        "<p>This link expires in 30 minutes. If you didn't request this, "
                        "you can safely ignore this email.</p>"
                    ),
                },
                timeout=10,
            )
            resp.raise_for_status()
        except Exception:
            traceback.print_exc()

    # Never reveal whether the email exists — same response either way.
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


_OTP_TTL_SEC = 5 * 60
_otp_tokens: dict[str, tuple[str, float]] = {}

_VERIFIED_EMAIL_TTL_SEC = 15 * 60
_verified_emails: dict[str, float] = {}


def _consume_verified_email(email: str) -> bool:
    expires_at = _verified_emails.pop(email, None)
    if expires_at is None:
        return False
    if time.monotonic() > expires_at:
        return False
    return True


def _issue_otp(email: str) -> str:
    code = str(secrets.randbelow(900000) + 100000)
    _otp_tokens[email] = (code, time.monotonic() + _OTP_TTL_SEC)
    return code


def _verify_otp(email: str, code: str) -> bool:
    rec = _otp_tokens.get(email)
    if not rec:
        return False
    stored_code, expires_at = rec
    if time.monotonic() > expires_at:
        _otp_tokens.pop(email, None)
        return False
    if stored_code != code:
        return False
    _otp_tokens.pop(email, None)
    return True


class OtpSendIn(BaseModel):
    email: EmailStr


class OtpVerifyIn(BaseModel):
    email: EmailStr
    code: str


@router.post("/otp/send")
def otp_send(payload: OtpSendIn):
    code = _issue_otp(str(payload.email))

    if settings.RESEND_API_KEY:
        try:
            resp = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": f"Klara <{settings.FROM_EMAIL}>",
                    "to": [str(payload.email)],
                    "subject": "Your Klara verification code",
                    "html": f"<p>Your verification code is: <strong>{code}</strong></p><p>This code expires in 5 minutes.</p>",
                },
                timeout=10,
            )
            resp.raise_for_status()
        except Exception:
            traceback.print_exc()

    if settings.DEBUG:
        return {"ok": True, "code": code}
    return {"ok": True}


@router.post("/otp/verify")
def otp_verify(payload: OtpVerifyIn):
    valid = _verify_otp(str(payload.email), payload.code)
    if not valid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Invalid or expired OTP"
        )
    _verified_emails[str(payload.email)] = time.monotonic() + _VERIFIED_EMAIL_TTL_SEC
    return {"ok": True, "verified": True}


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
        biz = svc.create({
            "name":          email.split("@")[0],
            "contact_email": email,
            "industry":      "travel",
        })
        user = svc.create_user(
            business_id=UUID(biz["id"]),
            email=email,
            password=secrets.token_urlsafe(24),
            first_name=info.get("given_name"),
            last_name=info.get("family_name"),
            role="admin",
        )

    access_t  = issue_access_token(sub=user["id"], business_id=user["business_id"], role=user.get("role", "user"))
    refresh_t = issue_refresh_token(sub=user["id"], business_id=user["business_id"])
    return TokenOut(access_token=access_t, refresh_token=refresh_t,
                    expires_in_min=settings.JWT_ACCESS_TTL_MIN)


def _client_ip(request: Request) -> Optional[str]:
    h = request.headers
    return h.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None)