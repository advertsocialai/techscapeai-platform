"""JWT issue/decode/blacklist + Plivo HMAC signature verification.

Pure crypto — no DB, no network, no real credentials. Mirrors the manual
checks run during the 2026-08-07 sprint (see SPRINT_REPORT.md) as a
regression-proof test instead of a one-off terminal command.
"""
from __future__ import annotations
import base64
import hashlib
import hmac

import jwt as pyjwt
import pytest


def test_access_token_roundtrip():
    from app.core import security as sec

    token = sec.issue_access_token(
        sub="11111111-1111-1111-1111-111111111111",
        business_id="22222222-2222-2222-2222-222222222222",
        role="agent",
    )
    claims = sec.decode_access_token(token)
    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"
    assert claims["biz"] == "22222222-2222-2222-2222-222222222222"
    assert claims["role"] == "agent"
    assert claims["type"] == "access"


def test_tampered_token_rejected():
    from app.core import security as sec

    token = sec.issue_access_token(sub="x", business_id="y", role="viewer")
    with pytest.raises(pyjwt.InvalidTokenError):
        sec.decode_access_token(token + "tampered")


def test_refresh_token_rejected_by_access_secret():
    """Access and refresh tokens are signed with different secrets —
    a refresh token must never validate as an access token."""
    from app.core import security as sec

    refresh = sec.issue_refresh_token(sub="x", business_id="y")
    with pytest.raises(pyjwt.InvalidTokenError):
        sec.decode_access_token(refresh)


def test_jti_blacklist_lifecycle():
    from app.core import security as sec

    token = sec.issue_access_token(sub="x", business_id="y", role="agent")
    claims = sec.decode_access_token(token)
    jti = claims["jti"]

    assert sec.is_jti_blacklisted(jti) is False
    sec.blacklist_jti(jti, ttl_seconds=900)
    assert sec.is_jti_blacklisted(jti) is True


def test_plivo_signature_valid_and_tampered():
    from app.core.config import settings
    from app.services.travel.voice import verify_plivo_signature

    settings.PLIVO_AUTH_TOKEN = "test-token-abc123"
    try:
        url = "https://example.ngrok.io/api/travel/v1/webhook/plivo/voice"
        nonce = "nonce123"
        base = url + nonce
        digest = hmac.new(
            settings.PLIVO_AUTH_TOKEN.encode(), base.encode(), hashlib.sha256
        ).digest()
        valid_sig = base64.b64encode(digest).decode()

        assert verify_plivo_signature(url=url, nonce=nonce, signature=valid_sig) is True
        assert verify_plivo_signature(url=url, nonce=nonce, signature=valid_sig[:-1] + "X") is False
        assert verify_plivo_signature(url=url, nonce=nonce, signature=None) is False
        assert verify_plivo_signature(url=url, nonce=None, signature=valid_sig) is False
        assert verify_plivo_signature(url=url + "x", nonce=nonce, signature=valid_sig) is False
    finally:
        settings.PLIVO_AUTH_TOKEN = ""  # restore stub mode for other tests


def test_plivo_signature_stub_mode_accepts_when_unconfigured():
    from app.core.config import settings
    from app.services.travel.voice import verify_plivo_signature

    assert settings.PLIVO_AUTH_TOKEN == ""
    assert verify_plivo_signature(url="https://x", nonce=None, signature=None) is True
