"""
Voice pipeline services (Phase 2) — Plivo signature verification, engine
selection helpers, and the Plivo XML response builder.

Provider auth pattern matches app/services/techscape/webhooks.py exactly
(same file kept untouched — techscape/* is out of scope; this is the
travel-scoped equivalent for Plivo): dev/stub mode accepts requests when
the signing secret is unset, so the platform stays testable without real
credentials. Once PLIVO_AUTH_TOKEN is set, verification becomes real and
mandatory.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
from typing import Optional
from xml.sax.saxutils import escape

from app.core.config import settings


# ── Plivo signature (V2) ────────────────────────────────────────────
def verify_plivo_signature(
    *, url: str, nonce: Optional[str], signature: Optional[str],
) -> bool:
    """
    Per Plivo's Signature V2 spec:
      base = url + nonce
      sig  = HMAC-SHA256(auth_token, base) -> base64
    Headers: X-Plivo-Signature-V2 (signature), X-Plivo-Signature-V2-Nonce (nonce).
    `url` must be the exact webhook URL Plivo posted to (PUBLIC_BASE_URL +
    path), including query string if any.
    """
    token = settings.PLIVO_AUTH_TOKEN
    if not token:
        return True  # stub mode — no credentials configured yet
    if not signature or not nonce:
        return False
    base = url + nonce
    digest = hmac.new(token.encode(), base.encode(), hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


def plivo_configured() -> bool:
    return bool(settings.PLIVO_AUTH_ID and settings.PLIVO_AUTH_TOKEN and settings.PLIVO_PHONE_NUMBER)


# ── Plivo XML response builder ──────────────────────────────────────
def speak_xml(text: str, *, voice: str = "WOMAN", language: str = "en-US") -> str:
    """Static <Speak> response — proves webhook plumbing without streaming."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Speak voice="{voice}" language="{language}">{escape(text)}</Speak></Response>'
    )


def stream_xml(*, stream_url: str) -> str:
    """<Stream bidirectional="true"> — hands the call audio to our WS media endpoint."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Stream bidirectional="true" keepCallAlive="true">{escape(stream_url)}</Stream></Response>'
    )


# ── STT engine selection (T4) ───────────────────────────────────────
def select_stt_engine(language: Optional[str]) -> str:
    """Deepgram is the default; Sarvam handles Telugu / code-mixed speech."""
    if (language or "").lower().startswith("te"):
        return "sarvam"
    return "deepgram"


def stt_configured(engine: str) -> bool:
    if engine == "sarvam":
        return bool(settings.SARVAM_API_KEY)
    return bool(settings.DEEPGRAM_API_KEY)


def tts_configured() -> bool:
    return bool(settings.ELEVENLABS_API_KEY)
