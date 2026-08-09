"""
The voice turn loop — the thing that makes the AI actually speak.

WHY THIS FILE EXISTS
--------------------
`ai_engine.run_turn()`, `voice.synthesize_speech()` and `voice.log_voice_turn()`
were all written, correct, tested by inspection — and had **zero call sites**.
The repo's own dead-code finder listed all three:

    api/app/services/travel/ai_engine.py:170  run_turn()          (49 lines)
    api/app/services/travel/voice.py:185      synthesize_speech() (16 lines)
    api/app/services/travel/voice.py:204      log_voice_turn()    (9 lines)

The consequence was not subtle: **during a call, the customer spoke, we
transcribed them, scored their sentiment, embedded the text, generated a
whisper suggestion for the agent — and the AI never replied.** Everything
downstream of the transcript was live; the conversation itself was not.

Nothing failed, which is exactly why it survived. A missing call raises no
error and breaks no test — the feature is simply absent.

WHAT THIS DOES
--------------
One customer utterance in, one AI turn out:

    transcript → run_turn()          → the reply text
               → travel_transcripts  → persisted as speaker='ai'
               → call_feed.publish() → the dashboard sees the AI speak
               → synthesize_speech() → audio bytes
               → log_voice_turn()    → the grep-able VOICE_TURN latency line

CREDENTIAL-FREE BY DESIGN
-------------------------
Every external hop already degrades on its own:
  * no ANTHROPIC_API_KEY  → run_turn() uses its `_stub_turn` heuristic
  * no ELEVENLABS_API_KEY → synthesize_speech() returns b"" (silence, not a crash)
So the loop runs end-to-end with no credentials at all. What it CANNOT do
without Plivo is play the audio back down the call — that needs an MPC leg
(B-P2-01/B-P2B-01). The bytes are produced and measured; they are just not
transmitted. That gap is stated in the log line rather than hidden, because a
turn loop that silently drops its own audio is worse than one that says so.

FIRE-AND-FORGET, like its siblings
----------------------------------
`schedule()` matches suggestion_service / sentiment_service / post_call_service:
the media-stream WebSocket must never block on a 30-second model call, or the
socket stalls and Plivo drops the stream mid-sentence.

⚠️ When real audio playback lands this has to become ORDERED. Two overlapping
turns writing to the same call would interleave replies. Today only one
utterance is in flight at a time (the stream handler awaits transcription
before scheduling), so ordering holds by construction — but it holds by
accident, not by design, and the next person to touch this needs to know that.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional
from uuid import UUID

from app.database import get_supabase_admin
from app.services.travel import ai_engine, call_feed
from app.services.travel.voice import log_voice_turn, synthesize_speech

logger = logging.getLogger(__name__)


def _next_seq(db, call_id: str) -> int:
    """
    Real monotonic sequence for this call.

    `seq` was hardcoded to 1 at its only emit site, which made it a lie:
    api-conventions.md documents it as monotonic and warns clients not to build
    gap detection on it *because* it isn't. Counting the rows that already exist
    makes the documented contract true, so the field stops being a trap.

    Not concurrency-safe on its own — two simultaneous turns could read the same
    count. Acceptable while one utterance is in flight at a time (see the module
    docstring); a real sequence column is the fix when that stops being true.
    """
    try:
        res = (
            db.table("travel_transcripts")
            .select("id", count="exact")
            .eq("call_id", call_id)
            .execute()
        )
        return int(res.count or 0) + 1
    except Exception:
        logger.warning("seq lookup failed for call=%s; falling back to 1", call_id)
        return 1


async def run_ai_turn(
    *,
    call_id: str,
    business_id: str,
    lead_id: Optional[str],
    customer_text: str,
    language: str = "en",
    stt_engine: str = "unknown",
    stt_ms: int = 0,
    ai_config: Optional[dict[str, Any]] = None,
    history: Optional[list[dict]] = None,
) -> Optional[dict[str, Any]]:
    """Returns the turn result, or None if the turn could not be produced."""
    if not customer_text.strip():
        return None

    db = get_supabase_admin()
    turn_started = time.monotonic()

    # ── 1. The model turn ────────────────────────────────────────────────
    llm_started = time.monotonic()
    try:
        result = await ai_engine.run_turn(
            customer_text,
            lead_id=UUID(lead_id) if lead_id else UUID(int=0),
            business_id=UUID(business_id),
            history=history,
            ai_config=ai_config,
        )
    except Exception:
        # A failed AI turn must never kill the call. The customer keeps talking,
        # the human agent still sees the transcript, and the dashboard still
        # works — it just doesn't get an AI reply for this utterance.
        logger.exception("voice turn: run_turn failed for call=%s", call_id)
        return None
    llm_total_ms = int((time.monotonic() - llm_started) * 1000)

    reply = (result or {}).get("reply", "").strip()
    if not reply:
        logger.info("voice turn: empty reply for call=%s — nothing to say", call_id)
        return result

    # ── 2. Persist the AI side of the conversation ───────────────────────
    seq = _next_seq(db, call_id)
    try:
        ai_row = (
            db.table("travel_transcripts")
            .insert(
                {
                    "call_id": call_id,
                    "speaker": "ai",
                    "text_original": reply,
                    "timestamp_ms": int(time.time() * 1000),
                }
            )
            .execute()
            .data[0]
        )
    except Exception:
        logger.exception("voice turn: could not persist AI reply for call=%s", call_id)
        return result

    # ── 3. Tell the dashboard the AI spoke ───────────────────────────────
    # Same frame shape as the customer transcript — the live-call screen already
    # renders speaker='ai', it had simply never received one.
    await call_feed.publish(
        call_id,
        {
            "type": "transcript",
            "call_id": call_id,
            "seq": seq,
            "speaker": "ai",
            "text_original": reply,
            "text_translated": None,
            "language": language,
            "timestamp_ms": ai_row["timestamp_ms"],
            "is_final": True,
        },
    )

    # ── 4. Speak it ──────────────────────────────────────────────────────
    tts_started = time.monotonic()
    audio = await synthesize_speech(reply)
    tts_ttfb_ms = int((time.monotonic() - tts_started) * 1000)

    if not audio:
        # Expected without ELEVENLABS_API_KEY. Logged at INFO, not WARNING —
        # it is the configured behaviour of stub mode, not a fault.
        logger.info("voice turn: no audio produced (TTS unconfigured) call=%s", call_id)

    # ── 5. The latency line gogaga-verifier greps for ────────────────────
    log_voice_turn(
        call_id=call_id,
        seq=seq,
        stt_ms=stt_ms,
        # llm_ttft is not separable without response streaming; reported equal to
        # llm_total rather than invented. A fabricated time-to-first-token would
        # make the latency budget look better than it is.
        llm_ttft_ms=llm_total_ms,
        llm_total_ms=llm_total_ms,
        tts_ttfb_ms=tts_ttfb_ms,
        total_ms=int((time.monotonic() - turn_started) * 1000),
        engine=stt_engine,
        lang=language,
    )

    if audio:
        # 📞 Produced and measured, but NOT transmitted: playing it back needs a
        # Plivo MPC leg that does not exist yet (B-P2-01 / B-P2B-01). Saying so
        # in the log is the point — a loop that silently discards its own audio
        # looks identical to one that works.
        logger.info(
            "voice turn: %d bytes of audio ready but NOT played — no MPC leg "
            "(B-P2B-01) call=%s",
            len(audio),
            call_id,
        )

    return result


def schedule(**kwargs: Any) -> None:
    """Fire-and-forget wrapper — the media-stream socket must not block."""
    try:
        asyncio.create_task(run_ai_turn(**kwargs))
    except RuntimeError:
        # No running loop (sync context, e.g. a test). Run it inline rather than
        # dropping the turn silently.
        asyncio.run(run_ai_turn(**kwargs))
