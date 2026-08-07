"""
Live suggestion service (Phase 3 T3) — MOCK/OFFLINE mode.

Section A gate decision: Phase 2B never ran → headroom_ms unknown →
MOCK/OFFLINE mode. Suggestions are generated AFTER the transcript is
written and audio is already playing — zero impact on voice latency.
Results arrive via WS (suggestion message type) 0-1 turns later.

If ANTHROPIC_API_KEY present: real Claude Haiku call per turn.
If absent: keyword-heuristic fallback (still contextually useful).

Called from webhooks_voice.py after each transcript is persisted.
Fire-and-forget via asyncio.create_task() — never awaited on the
voice-critical path. See BLOCKERS.md B-P3-02 + DEBT-01.
"""
from __future__ import annotations
import asyncio
import logging
from uuid import UUID

import httpx

from app.core.config import settings
from app.database import get_supabase_admin
from app.services.travel import call_feed

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# Keyword-based heuristic rules (fallback when no API key)
_RULES = [
    (["kids", "children", "family", "child"], "Customer mentioned family — consider suggesting a family-friendly package"),
    (["budget", "cheap", "affordable", "cost", "price", "expensive"], "Price sensitivity detected — offer the most affordable package variant"),
    (["refund", "cancel", "cancellation", "cancel"], "Customer mentioned cancellation — be ready to explain the refund policy"),
    (["maldives", "bali", "europe", "international"], "International destination interest — confirm passport/visa requirements"),
    (["honeymoon", "anniversary", "romantic", "couple"], "Romantic trip context — suggest honeymoon or couple packages"),
    (["months", "february", "march", "april", "may", "june", "july", "august",
      "september", "october", "november", "december", "january"], "Timing mentioned — confirm availability for that period"),
]


def _keyword_suggestion(transcript_text: str, context_texts: list[str]) -> str | None:
    combined = " ".join([transcript_text] + context_texts[-4:]).lower()
    for keywords, suggestion in _RULES:
        if any(kw in combined for kw in keywords):
            return suggestion
    return None


async def _claude_suggestion(
    call_id: str, transcript_text: str, context_texts: list[str], ai_config: dict
) -> str | None:
    if not settings.ANTHROPIC_API_KEY:
        return None
    persona_name = (ai_config.get("voice_persona") or {}).get("name", "Klara")
    escalation = ai_config.get("escalation_rules") or {}
    system = (
        f"You are a supervisor coaching {persona_name}, an AI travel agent. "
        f"Given the last customer utterance and recent call context, output ONE "
        f"brief next-best-action hint for a human supervisor watching the live call. "
        f"Examples: 'suggest Goa package ₹35k', 'price objection — offer EMI option', "
        f"'customer ready to book — send payment link'. "
        f"Escalation threshold: budget >{escalation.get('budget_threshold', 100000)//1000}k INR. "
        f"Output: one sentence, no preamble."
    )
    messages = [{"role": "user", "content":
        f"Recent transcript:\n{''.join(context_texts[-4:])}\n\nLatest utterance: {transcript_text}"}]
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(
                ANTHROPIC_URL,
                headers={"x-api-key": settings.ANTHROPIC_API_KEY,
                         "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001",  # fast/cheap for inline hints
                      "max_tokens": 80, "system": system, "messages": messages},
            )
            r.raise_for_status()
            data = r.json()
            return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()
    except Exception:
        logger.exception("Claude suggestion call failed for call=%s", call_id)
        return None


async def generate_and_broadcast(
    call_id: str, transcript_text: str, speaker: str, ai_config: dict
) -> None:
    """Fire-and-forget: generate a suggestion and broadcast it on the call feed."""
    if speaker != "customer":
        return  # only react to customer utterances

    db = get_supabase_admin()

    # Fetch recent transcript for context (last 6 turns)
    rows = (
        db.table("travel_transcripts").select("text_original, speaker")
        .eq("call_id", call_id)
        .order("timestamp_ms", desc=True).limit(6).execute().data or []
    )
    context_texts = [f"{r['speaker']}: {r['text_original']}" for r in reversed(rows)]

    # Try Claude, fall back to keywords
    suggestion = None
    if settings.ANTHROPIC_API_KEY:
        suggestion = await _claude_suggestion(call_id, transcript_text, context_texts, ai_config)
    if not suggestion:
        suggestion = _keyword_suggestion(transcript_text, context_texts)
    if not suggestion:
        return  # no useful hint this turn

    logger.info("suggestion generated for call=%s: %s", call_id, suggestion[:80])

    # Log event
    db.table("travel_call_events").insert({
        "call_id": call_id,
        "event_type": "suggestion_generated",
        "payload": {"text": suggestion, "mode": "claude" if settings.ANTHROPIC_API_KEY else "keyword"},
    }).execute()

    # Broadcast
    await call_feed.publish(call_id, {
        "type": "suggestion",
        "call_id": call_id,
        "text": suggestion,
        "mode": "claude" if settings.ANTHROPIC_API_KEY else "keyword",
    })


def schedule(
    call_id: str, transcript_text: str, speaker: str, ai_config: dict
) -> None:
    """Schedule suggestion generation as a fire-and-forget background task.
    Called from the voice WS handler — never blocks the voice critical path."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(
                generate_and_broadcast(call_id, transcript_text, speaker, ai_config)
            )
        else:
            logger.warning("No running event loop — suggestion skipped for call=%s", call_id)
    except Exception:
        logger.exception("Failed to schedule suggestion for call=%s", call_id)
