"""
The voice turn loop must stay WIRED.

This suite exists because of a specific, repeated failure in this repo: a
function that is written, correct, reviewed — and never called. `run_turn()`,
`synthesize_speech()` and `log_voice_turn()` sat with ZERO call sites while
every test passed, because a missing call raises nothing. The customer spoke,
we transcribed and scored and embedded and whispered, and the AI never replied.

So these tests assert the CALL, not just the behaviour. If someone refactors the
media-stream handler and drops the turn, this goes red — which is exactly the
signal that was missing the first time.

Runs entirely credential-free: run_turn falls back to its stub heuristic without
ANTHROPIC_API_KEY, and synthesize_speech returns b"" without ELEVENLABS_API_KEY.
"""
from __future__ import annotations

import asyncio
import logging
import re
from unittest.mock import MagicMock, patch

import pytest

BUSINESS_ID = "22222222-2222-4222-8222-222222222222"
CALL_ID = "33333333-3333-4333-8333-333333333333"
LEAD_ID = "44444444-4444-4444-8444-444444444444"


def _fake_db():
    """Supabase client stub: records inserts, answers counts."""
    db = MagicMock()
    inserted: list[dict] = []

    def _table(name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.execute.return_value = MagicMock(count=2, data=[])

        def _insert(payload):
            inserted.append({"table": name, **payload})
            ins = MagicMock()
            ins.execute.return_value = MagicMock(
                data=[{**payload, "id": "row-1", "timestamp_ms": payload.get("timestamp_ms", 0)}]
            )
            return ins

        t.insert.side_effect = _insert
        return t

    db.table.side_effect = _table
    db._inserted = inserted
    return db


def test_ai_reply_is_persisted_and_published(caplog):
    """One customer utterance produces an AI transcript row AND a feed frame."""
    from app.services.travel import voice_turn_service

    published: list[tuple] = []

    async def _capture(call_id, frame):
        published.append((call_id, frame))

    db = _fake_db()
    caplog.set_level(logging.INFO)

    # ai_engine.run_turn is stubbed here rather than exercised: its own stub path
    # queries travel_packages, so letting it run would test ai_engine's DB access
    # instead of THIS module's wiring. What is under test is that a reply gets
    # persisted and published — ai_engine has its own coverage.
    async def _fake_turn(*_a, **_kw):
        return {"reply": "We have a 7-day Bali package from ₹84,000.", "tool_calls": [], "model": "stub"}

    with patch.object(voice_turn_service, "get_supabase_admin", return_value=db), \
         patch.object(voice_turn_service.ai_engine, "run_turn", _fake_turn), \
         patch.object(voice_turn_service.call_feed, "publish", _capture):
        result = asyncio.run(
            voice_turn_service.run_ai_turn(
                call_id=CALL_ID,
                business_id=BUSINESS_ID,
                lead_id=LEAD_ID,
                customer_text="I want to go to Bali in December",
                language="en",
                stt_engine="deepgram",
            )
        )

    assert result is not None, "stub turn must still produce a result"

    ai_rows = [r for r in db._inserted if r.get("speaker") == "ai"]
    assert ai_rows, "the AI reply was never written to travel_transcripts"
    assert ai_rows[0]["call_id"] == CALL_ID
    assert ai_rows[0]["text_original"].strip(), "AI reply must not be empty"

    ai_frames = [f for _, f in published if f.get("speaker") == "ai"]
    assert ai_frames, "the dashboard was never told the AI spoke"
    assert ai_frames[0]["type"] == "transcript"
    assert ai_frames[0]["is_final"] is True


def test_voice_turn_latency_line_is_emitted(caplog):
    """
    The VOICE_TURN line must match api-conventions.md EXACTLY — gogaga-verifier
    greps for this format, so a field rename silently breaks phase acceptance.
    """
    from app.services.travel import voice_turn_service

    async def _noop(call_id, frame):
        return None

    caplog.set_level(logging.INFO)
    with patch.object(voice_turn_service, "get_supabase_admin", return_value=_fake_db()), \
         patch.object(voice_turn_service.call_feed, "publish", _noop):
        asyncio.run(
            voice_turn_service.run_ai_turn(
                call_id=CALL_ID,
                business_id=BUSINESS_ID,
                lead_id=LEAD_ID,
                customer_text="What packages do you have?",
                language="te",
                stt_engine="sarvam",
            )
        )

    line = next((r.getMessage() for r in caplog.records if "VOICE_TURN" in r.getMessage()), None)
    assert line, "no VOICE_TURN latency line was logged"
    assert re.search(
        r"VOICE_TURN call_id=\S+ seq=\d+ stt_ms=\d+ llm_ttft_ms=\d+ "
        r"llm_total_ms=\d+ tts_ttfb_ms=\d+ total_ms=\d+ engine=\S+ lang=\S+",
        line,
    ), f"VOICE_TURN format drifted from api-conventions.md: {line}"
    assert "lang=te" in line and "engine=sarvam" in line


def test_seq_is_monotonic_not_hardcoded_one():
    """
    `seq` used to be hardcoded to 1, which made the documented "monotonic"
    contract a lie and any client-side gap detection actively misleading.
    """
    from app.services.travel import voice_turn_service

    db = _fake_db()  # reports 2 existing transcripts
    assert voice_turn_service._next_seq(db, CALL_ID) == 3


def test_empty_transcript_produces_no_turn():
    """Silence must not generate an AI reply or a database row."""
    from app.services.travel import voice_turn_service

    db = _fake_db()
    with patch.object(voice_turn_service, "get_supabase_admin", return_value=db):
        out = asyncio.run(
            voice_turn_service.run_ai_turn(
                call_id=CALL_ID, business_id=BUSINESS_ID,
                lead_id=LEAD_ID, customer_text="   ",
            )
        )
    assert out is None
    assert not db._inserted, "an empty utterance wrote to the database"


def test_media_stream_actually_calls_the_turn_loop():
    """
    THE REGRESSION GUARD. Asserts the wiring, not the behaviour — this is the
    test that would have caught three functions having zero call sites.
    """
    import inspect
    from app.routers.travel import webhooks_voice

    src = inspect.getsource(webhooks_voice)
    assert "voice_turn_service" in src, (
        "webhooks_voice no longer references voice_turn_service — the AI has "
        "stopped replying during calls. This is the exact defect this file exists "
        "to prevent; re-wire it rather than deleting this test."
    )
    assert "voice_turn_service.schedule(" in src, (
        "voice_turn_service is imported but never invoked — an import is not a "
        "call site."
    )
