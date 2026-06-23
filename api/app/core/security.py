"""
Security primitives for TechScape:
  • password hashing (bcrypt via passlib)
  • API-key hashing
  • JWT issue / verify (access + refresh)
  • Fernet symmetric encryption for credentials_encrypted column
  • timing-safe HMAC helpers
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from app.core.config import settings


# ── Password hashing ───────────────────────────────────────────────
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return _pwd.verify(plain, hashed)
    except (ValueError, TypeError):
        return False


# ── API-key hashing (SHA-256, fast lookups) ────────────────────────
def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def new_api_key() -> tuple[str, str]:
    """Returns (plaintext, sha256_hash)."""
    plain = "tsk_" + secrets.token_urlsafe(40)
    return plain, hash_api_key(plain)


# ── JWT (access + refresh) ─────────────────────────────────────────
JWT_ALG = "HS256"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def issue_access_token(*, sub: str, business_id: str, role: str = "user") -> str:
    payload = {
        "sub":  sub,
        "biz":  business_id,
        "role": role,
        "type": "access",
        "iat":  _now(),
        "exp":  _now() + timedelta(minutes=settings.JWT_ACCESS_TTL_MIN),
        # nonce so two tokens issued in the same second still differ
        "jti":  secrets.token_urlsafe(8),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALG)


def issue_refresh_token(*, sub: str, business_id: str) -> str:
    payload = {
        "sub":  sub,
        "biz":  business_id,
        "type": "refresh",
        "iat":  _now(),
        "exp":  _now() + timedelta(days=settings.JWT_REFRESH_TTL_DAYS),
        "jti":  secrets.token_urlsafe(12),
    }
    return jwt.encode(payload, settings.JWT_REFRESH_SECRET, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALG])


def decode_refresh_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_REFRESH_SECRET, algorithms=[JWT_ALG])


# ── Fernet symmetric encryption ────────────────────────────────────
def _fernet() -> Fernet:
    """
    Resolve the Fernet key:
      1. settings.FERNET_KEY if non-empty (must be urlsafe-b64 32 bytes)
      2. otherwise derive deterministically from JWT_SECRET (DEV ONLY)
    """
    raw = settings.FERNET_KEY
    if raw:
        try:
            return Fernet(raw.encode() if isinstance(raw, str) else raw)
        except Exception as e:  # pragma: no cover
            raise RuntimeError(f"Invalid FERNET_KEY: {e}") from e
    digest = hashlib.sha256(settings.JWT_SECRET.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt_text(ciphertext: bytes) -> str:
    if isinstance(ciphertext, memoryview):
        ciphertext = bytes(ciphertext)
    if isinstance(ciphertext, str):
        ciphertext = ciphertext.encode()
    try:
        return _fernet().decrypt(ciphertext).decode()
    except InvalidToken as e:
        raise ValueError("invalid ciphertext") from e


# ── HMAC helpers (constant-time) ───────────────────────────────────
def hmac_sha256_hex(secret: str, data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()


def hmac_compare(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return hmac.compare_digest(a, b)
