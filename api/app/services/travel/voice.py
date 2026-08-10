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
import asyncio
import base64
import hashlib
import hmac
import logging
from typing import Any, Awaitable, Callable, Optional
from xml.sax.saxutils import escape

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Retry helper (T9) — shared by every external provider call in this
# module. Retries transient failures (5xx, network errors — never 4xx,
# those are our bug/bad-input, not the provider's) with short backoff,
# then gives up and returns None so the CALLER degrades gracefully
# (empty audio, stub-shaped transcript, etc.) instead of ever raising
# up into the WS handler and killing the call.
async def _call_with_retry(
    fn: Callable[[], Awaitable[httpx.Response]], *, attempts: int = 3, backoff_sec: float = 0.5,
) -> Optional[httpx.Response]:
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            r = await fn()
            if r.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"{r.status_code} from provider", request=r.request, response=r
                )
            r.raise_for_status()  # 4xx — not retryable, but still handled by the caller
            return r
        except Exception as e:
            last_exc = e
            logger.warning("provider call failed (attempt %d/%d): %s", attempt, attempts, e)
            if attempt < attempts:
                await asyncio.sleep(backoff_sec * attempt)
    logger.error("provider call failed after %d attempts: %s", attempts, last_exc)
    return None


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


# India call-recording disclosure. COMPLIANCE_CHECKLIST.md C-1: calls are
# transcribed and (once Plivo creds exist) recorded, and NOTHING in the flow
# disclosed that. TRAI/DoT practice and the DPDP notice principle both require
# the caller to be told before processing starts, so the announcement plays
# BEFORE the stream opens — a caller who hangs up on hearing it is never
# transcribed at all. Wording is deliberately plain; legal review of the exact
# text is Gowtham's (BLK-8) — its PRESENCE is not optional.
# PENDING LEGAL REVIEW (BLK-8) — mechanism final, wording placeholder.
# The MECHANISM (announcement plays before the stream opens; a
# 'consent_disclosure_played' event row is written to travel_call_events by
# the answer webhook, payload {language, wording_version}) is done and stays.
# Only the TEXT below and its translations (C-2: Telugu/Hindi versions are
# still missing — this plays in English regardless of ai_config.languages)
# are awaiting Gowtham/legal sign-off. When the wording changes, bump
# CONSENT_WORDING_VERSION so old call events remain attributable to the
# exact text that was actually played.
CONSENT_ANNOUNCEMENT = (
    "This call may be recorded and transcribed for quality and service purposes."
)
# Version tag persisted with every consent event (travel_call_events.payload).
# "draft-1" = the pre-legal-review engineering copy above.
CONSENT_WORDING_VERSION = "draft-1"
# The announcement currently plays in English only (C-2 gap, BLK-8).
CONSENT_ANNOUNCEMENT_LANGUAGE = "en"


def stream_xml(*, stream_url: str, announce_consent: bool = True) -> str:
    """<Speak> disclosure, then <Stream bidirectional> to our WS media endpoint."""
    speak = f"<Speak>{escape(CONSENT_ANNOUNCEMENT)}</Speak>" if announce_consent else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response>{speak}<Stream bidirectional="true" keepCallAlive="true">{escape(stream_url)}</Stream></Response>'
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

    async with httpx.AsyncClient(timeout=20) as client:
        if engine == "sarvam":
            r = await _call_with_retry(lambda: client.post(
                SARVAM_URL,
                headers={"api-subscription-key": settings.SARVAM_API_KEY},
                files={"file": ("audio.wav", audio_bytes, "audio/wav")},
                data={"language_code": language or "te-IN", "model": "saarika:v2"},
            ))
            if r is None:
                return {"text": "", "confidence": None, "engine": engine, "stub": False,
                        "error": "provider unavailable after retries"}
            data = r.json()
            return {"text": data.get("transcript", ""), "confidence": None,
                    "engine": "sarvam", "stub": False}
        else:
            r = await _call_with_retry(lambda: client.post(
                f"{DEEPGRAM_URL}?language={language or 'en'}&model=nova-2",
                headers={"Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
                         "Content-Type": "audio/wav"},
                content=audio_bytes,
            ))
            if r is None:
                return {"text": "", "confidence": None, "engine": engine, "stub": False,
                        "error": "provider unavailable after retries"}
            data = r.json()
            alt = (data.get("results", {}).get("channels", [{}])[0]
                   .get("alternatives", [{}])[0])
            return {"text": alt.get("transcript", ""), "confidence": alt.get("confidence"),
                    "engine": "deepgram", "stub": False}


# ── TTS (T6) ──────────────────────────────────────────────────────────
# NOTE: ElevenLabs' real streaming endpoint yields audio chunks as they're
# generated (needed for the sentence-level / barge-in design). Genuinely
# UNVERIFIED — no ELEVENLABS_API_KEY exists to call it with, and there is
# no meaningful proxy for "does barge-in interrupt mid-sentence in real
# time" without a live call. See PHASE2_REPORT.md Blocked Items — this
# function is written to the real API shape but not exercised.
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs' default "Rachel" voice


async def synthesize_speech(text: str, *, voice_id: str = DEFAULT_VOICE_ID) -> bytes:
    """Returns raw audio bytes for one sentence. Caller is responsible for
    sentence-level chunking (split on '.', '!', '?') so playback can start
    before the whole reply is generated — that's the latency-critical part
    and it's exactly the part that can't be verified without a live call."""
    if not tts_configured():
        logger.warning("ELEVENLABS_API_KEY not set; returning empty stub audio")
        return b""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await _call_with_retry(lambda: client.post(
            ELEVENLABS_URL.format(voice_id=voice_id),
            headers={"xi-api-key": settings.ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_turbo_v2_5",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        ))
        return r.content if r is not None else b""  # graceful: silence, not a crash


# ── VOICE_TURN latency log (per api-conventions.md — exact format) ────
def log_voice_turn(
    *, call_id: str, seq: int, stt_ms: int, llm_ttft_ms: int, llm_total_ms: int,
    tts_ttfb_ms: int, total_ms: int, engine: str, lang: str,
) -> None:
    logger.info(
        "VOICE_TURN call_id=%s seq=%d stt_ms=%d llm_ttft_ms=%d llm_total_ms=%d "
        "tts_ttfb_ms=%d total_ms=%d engine=%s lang=%s",
        call_id, seq, stt_ms, llm_ttft_ms, llm_total_ms, tts_ttfb_ms, total_ms, engine, lang,
    )
    # Observability hook: feed the latency-budget alert rule (alerting.py
    # rule 2 — median total_ms vs the 1.1s SLO). Local import + broad except:
    # telemetry must never be able to break a live call.
    try:
        from app.core import alerting
        alerting.observe_voice_turn(total_ms=total_ms)
    except Exception:  # pragma: no cover
        logger.exception("voice-turn alerting hook failed")
