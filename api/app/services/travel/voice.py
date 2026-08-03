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
import logging
from typing import Any, Optional
from xml.sax.saxutils import escape

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


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


# ── STT transcription (T4) ───────────────────────────────────────────
# NOTE: uses each provider's prerecorded/batch REST endpoint against the
# whole-utterance audio buffer, not a persistent streaming WS connection.
# Real low-latency production STT (the ≤1.1s mouth-to-ear target) needs
# streaming — that's flagged as a TODO in PHASE2_REPORT.md, since without
# live audio there's no way to verify streaming behavior is correct
# anyway. This batch path is what's actually testable right now: real
# HTTP call shape is implemented, but genuinely UNVERIFIED — no
# DEEPGRAM_API_KEY/SARVAM_API_KEY exists to call it with. Stub mode
# (below) is the only path that's actually been exercised.
DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
SARVAM_URL = "https://api.sarvam.ai/speech-to-text"


async def transcribe_utterance(
    *, engine: str, audio_bytes: bytes, language: Optional[str] = None,
) -> dict[str, Any]:
    """Returns {"text": str, "confidence": float|None, "engine": str, "stub": bool}."""
    if not stt_configured(engine):
        logger.warning("STT engine=%s not configured; returning stub transcript", engine)
        return {
            "text": f"[stub transcript — no {'SARVAM' if engine == 'sarvam' else 'DEEPGRAM'}_API_KEY configured]",
            "confidence": None, "engine": engine, "stub": True,
        }

    try:
        if engine == "sarvam":
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    SARVAM_URL,
                    headers={"api-subscription-key": settings.SARVAM_API_KEY},
                    files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                    data={"language_code": language or "te-IN", "model": "saarika:v2"},
                )
                r.raise_for_status()
                data = r.json()
                return {"text": data.get("transcript", ""), "confidence": None,
                        "engine": "sarvam", "stub": False}
        else:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    f"{DEEPGRAM_URL}?language={language or 'en'}&model=nova-2",
                    headers={"Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
                             "Content-Type": "audio/wav"},
                    content=audio_bytes,
                )
                r.raise_for_status()
                data = r.json()
                alt = (data.get("results", {}).get("channels", [{}])[0]
                       .get("alternatives", [{}])[0])
                return {"text": alt.get("transcript", ""), "confidence": alt.get("confidence"),
                        "engine": "deepgram", "stub": False}
    except Exception as e:
        logger.exception("STT call failed (engine=%s)", engine)
        return {"text": "", "confidence": None, "engine": engine, "stub": False, "error": str(e)[:240]}
